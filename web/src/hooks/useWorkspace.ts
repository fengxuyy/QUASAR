import { useState, useCallback, useEffect, useRef } from 'react';
import { withAuthUrl } from '../utils/apiAuth';

export interface FileNode {
  name: string;
  path: string;
  isDirectory: boolean;
  size?: number;
  mtime?: string;
  children?: FileNode[];
  childrenLoaded?: boolean;
}

export interface ArchiveRun {
  id: string;
  displayId: string;
  title: string;
  timestamp: string;
}

/** Hidden from the workspace tree (not useful research content). */
const HIDDEN_WORKSPACE_NAMES = new Set([
  'lost+found', // ext4 volume recovery dir from mkfs
  // Host/precache markers if a volume is ever mis-mounted into /workspace
  'docker-root',
  'image_tag',
  'quasar_docker_root_ready',
]);

function filterHiddenWorkspaceNodes(nodes: FileNode[]): FileNode[] {
  return nodes
    .filter(node => !HIDDEN_WORKSPACE_NAMES.has(node.name.toLowerCase()))
    .map(node =>
      node.children?.length
        ? { ...node, children: filterHiddenWorkspaceNodes(node.children) }
        : node,
    );
}

export function useWorkspace({ enabled = true, fastPoll = false }: { enabled?: boolean; fastPoll?: boolean } = {}) {
  const [files, setFiles] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [archives, setArchives] = useState<ArchiveRun[]>([]);
  const [selectedArchive, setSelectedArchive] = useState<string | null>(null);

  const isInitialLoad = useRef(true);
  const filesRef = useRef<FileNode[]>([]);
  const lastArchiveRef = useRef<string | null>(null);
  filesRef.current = files;

  const buildFilesUrl = useCallback((dirPath = '') => {
    const pathQuery = dirPath ? `&path=${encodeURIComponent(dirPath)}` : '';
    return selectedArchive
      ? `/api/archive/files?runId=${encodeURIComponent(selectedArchive)}&depth=0${pathQuery}`
      : `/api/files?depth=0${pathQuery}`;
  }, [selectedArchive]);

  // Fetch available archives
  const fetchArchives = useCallback(async () => {
    try {
      const response = await fetch('/api/history');
      if (!response.ok) throw new Error('Failed to fetch archives');
      const data = await response.json();
      setArchives(data);
    } catch (e) {
      console.error('Failed to fetch archives:', e);
    }
  }, []);

  /**
   * Root listing is depth=0. Periodic refresh must not drop already-expanded
   * folders' children or the tree "flashes" every poll (user opens docs/lammps,
   * then setFiles(rootOnly) collapses/reloads the same view).
   */
  const mergePreservingLoadedChildren = useCallback((prev: FileNode[], next: FileNode[]): FileNode[] => {
    if (!prev.length) return next;

    const prevByPath = new Map<string, FileNode>();
    const index = (nodes: FileNode[]) => {
      for (const node of nodes) {
        prevByPath.set(node.path, node);
        if (node.children?.length) index(node.children);
      }
    };
    index(prev);

    const merge = (nodes: FileNode[]): FileNode[] =>
      nodes.map(node => {
        const prior = prevByPath.get(node.path);
        if (node.isDirectory && prior?.childrenLoaded && prior.children) {
          // Keep expanded subtree; re-merge if the refresh also returned children.
          const nextChildren = node.children?.length
            ? merge(node.children)
            : prior.children;
          return {
            ...node,
            children: nextChildren,
            childrenLoaded: true,
          };
        }
        if (node.children?.length) {
          return {
            ...node,
            children: merge(node.children),
            childrenLoaded: prior?.childrenLoaded ?? node.childrenLoaded,
          };
        }
        return node;
      });

    return merge(next);
  }, []);

  /** Full loaded-tree identity — used to skip no-op poll updates and avoid re-render flash. */
  const treeListingKey = useCallback((nodes: FileNode[]): string => {
    const parts: string[] = [];
    const walk = (items: FileNode[]) => {
      for (const n of items) {
        parts.push(`${n.path}\0${n.isDirectory ? 'd' : 'f'}\0${n.size ?? ''}\0${n.mtime ?? ''}\0${n.childrenLoaded ? '1' : '0'}`);
        if (n.children?.length) {
          walk(n.children);
        }
      }
    };
    walk(nodes);
    return parts.join('\n');
  }, []);

  const collectLoadedDirPaths = useCallback((nodes: FileNode[], limit = 30): string[] => {
    const paths: string[] = [];
    const walk = (items: FileNode[]) => {
      for (const node of items) {
        if (paths.length >= limit) return;
        if (node.isDirectory && node.childrenLoaded) {
          paths.push(node.path);
          if (node.children?.length) {
            walk(node.children);
          }
        }
      }
    };
    walk(nodes);
    return paths;
  }, []);

  const fetchDirectoryChildren = useCallback(async (dirPath: string): Promise<FileNode[]> => {
    const response = await fetch(buildFilesUrl(dirPath));
    if (!response.ok) throw new Error('Failed to fetch directory');
    return filterHiddenWorkspaceNodes(await response.json() as FileNode[]);
  }, [buildFilesUrl]);

  const applyRefreshedChildren = useCallback((
    nodes: FileNode[],
    refreshedMap: Map<string, FileNode[]>,
  ): FileNode[] => {
    return nodes.map(node => {
      if (!node.isDirectory) return node;
      const updated = refreshedMap.get(node.path);
      if (updated !== undefined) {
        const merged = mergePreservingLoadedChildren(node.children || [], updated);
        return {
          ...node,
          children: applyRefreshedChildren(merged, refreshedMap),
          childrenLoaded: true,
        };
      }
      if (node.children?.length) {
        return {
          ...node,
          children: applyRefreshedChildren(node.children, refreshedMap),
        };
      }
      return node;
    });
  }, [mergePreservingLoadedChildren]);

  const fetchFiles = useCallback(async () => {
    if (isInitialLoad.current) {
      setLoading(true);
    }
    try {
      const url = buildFilesUrl();
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch files');
      const data = filterHiddenWorkspaceNodes(await response.json() as FileNode[]);

      // Also refresh any already-expanded/loaded directories in the live workspace
      // so newly downloaded folders (e.g. docs/ase, docs/pymatgen, docs/q-e/SSSP)
      // appear automatically without collapsing or flashing the tree.
      const refreshedMap = new Map<string, FileNode[]>();
      if (!isInitialLoad.current && !selectedArchive) {
        const rootDirPaths = new Set(data.filter(n => n.isDirectory).map(n => n.path));
        const loadedDirs = collectLoadedDirPaths(filesRef.current).filter(dirPath => {
          const topSegment = dirPath.split('/')[0];
          return rootDirPaths.has(topSegment);
        });
        if (loadedDirs.length > 0) {
          await Promise.all(
            loadedDirs.map(async dirPath => {
              try {
                const children = await fetchDirectoryChildren(dirPath);
                refreshedMap.set(dirPath, children);
              } catch {
                // Ignore transient errors (e.g. temp clone dir renamed mid-poll)
              }
            }),
          );
        }
      }

      setFiles(prev => {
        if (isInitialLoad.current) return data;
        let next = mergePreservingLoadedChildren(prev, data);
        if (refreshedMap.size > 0) {
          next = applyRefreshedChildren(next, refreshedMap);
        }
        if (treeListingKey(prev) === treeListingKey(next)) {
          return prev;
        }
        return next;
      });
      isInitialLoad.current = false;
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [
    applyRefreshedChildren,
    buildFilesUrl,
    collectLoadedDirPaths,
    fetchDirectoryChildren,
    mergePreservingLoadedChildren,
    selectedArchive,
    treeListingKey,
  ]);

  const replaceChildren = useCallback((nodes: FileNode[], dirPath: string, children: FileNode[]): FileNode[] => {
    return nodes.map(node => {
      if (node.path === dirPath) {
        // Preserve any already-loaded nested expansions under this directory.
        const merged = mergePreservingLoadedChildren(node.children || [], children);
        return { ...node, children: merged, childrenLoaded: true };
      }
      if (node.children) {
        return { ...node, children: replaceChildren(node.children, dirPath, children) };
      }
      return node;
    });
  }, [mergePreservingLoadedChildren]);

  const loadDirectoryChildren = useCallback(async (dirPath: string): Promise<FileNode[]> => {
    const children = await fetchDirectoryChildren(dirPath);
    setFiles(prev => replaceChildren(prev, dirPath, children));
    return children;
  }, [fetchDirectoryChildren, replaceChildren]);

  const getFileContent = useCallback(async (
    path: string,
    maxSize?: number,
    offset?: number
  ): Promise<{ content: string; totalSize: number; truncated: boolean; offset?: number; nextOffset?: number }> => {
    try {
      let url = selectedArchive
        ? `/api/archive/files/content?runId=${encodeURIComponent(selectedArchive)}&path=${encodeURIComponent(path)}`
        : `/api/files/content?path=${encodeURIComponent(path)}`;
      if (maxSize && maxSize > 0) {
        url += `&maxSize=${maxSize}`;
      }
      if (offset && offset > 0) {
        url += `&offset=${offset}`;
      }
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch file content');
      const data = await response.json();
      return {
        content: data.content as string,
        totalSize: data.totalSize ?? (data.content?.length || 0),
        truncated: data.truncated ?? false,
        offset: data.offset,
        nextOffset: data.nextOffset,
      };
    } catch (e) {
      console.error(e);
      throw e;
    }
  }, [selectedArchive]);

  const getFileRawUrl = useCallback((path: string) => {
    const rawUrl = selectedArchive
      ? `/api/archive/files/raw?runId=${encodeURIComponent(selectedArchive)}&path=${encodeURIComponent(path)}`
      : `/api/files/raw?path=${encodeURIComponent(path)}`;
    return withAuthUrl(rawUrl);
  }, [selectedArchive]);

  // Fetch archives on mount
  useEffect(() => {
    if (!enabled) return;
    fetchArchives();
  }, [enabled, fetchArchives]);

  // Fetch files when archive selection or polling cadence changes
  useEffect(() => {
    if (!enabled) return;
    if (lastArchiveRef.current !== selectedArchive || filesRef.current.length === 0) {
      isInitialLoad.current = true;
      lastArchiveRef.current = selectedArchive;
    }
    void fetchFiles();
    // Poll live workspace (faster while docs/RAG download or an agent run is active).
    // No-op when tree listing is unchanged so expanded folders do not re-render/flash.
    if (!selectedArchive) {
      const tick = () => {
        if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
        void fetchFiles();
      };
      const interval = setInterval(tick, fastPoll ? 3000 : 15000);
      return () => clearInterval(interval);
    }
  }, [enabled, fastPoll, fetchFiles, selectedArchive]);

  return {
    files,
    loading,
    error,
    refreshFiles: fetchFiles,
    refreshArchives: fetchArchives,
    loadDirectoryChildren,
    getFileContent,
    getFileRawUrl,
    archives,
    selectedArchive,
    setSelectedArchive,
    uploadFiles: async (fileList: FileList) => {
      if (selectedArchive) {
        throw new Error('Cannot upload files to an archived run');
      }

      const formData = new FormData();
      const relativePaths: string[] = [];
      
      Array.from(fileList).forEach(file => {
        // Use webkitRelativePath for folder uploads, or just name for single files
        const path = file.webkitRelativePath || file.name;
        relativePaths.push(path);
        formData.append('files', file); 
      });

      formData.append('relativePaths', JSON.stringify(relativePaths));

      try {
        const response = await fetch('/api/upload', {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          throw new Error('Upload failed');
        }

        const result = await response.json();
        // Refresh files after successful upload
        fetchFiles();
        return result;
      } catch (e) {
        console.error('Upload error:', e);
        throw e;
      }
    },
    deleteFile: async (path: string) => {
      try {
        const response = await fetch('/api/files/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path }),
        });
        if (!response.ok) throw new Error('Delete failed');
        fetchFiles();
      } catch (e) {
        console.error('Delete error:', e);
        throw e;
      }
    },
    renameFile: async (oldPath: string, newPath: string) => {
      try {
        const response = await fetch('/api/files/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ oldPath, newPath }),
        });
        if (!response.ok) throw new Error('Rename failed');
        fetchFiles();
      } catch (e) {
        console.error('Rename error:', e);
        throw e;
      }
    },
    saveFileContent: async (filePath: string, content: string) => {
      if (selectedArchive) {
        throw new Error('Cannot save files to an archived run');
      }
      try {
        const response = await fetch('/api/files/write', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: filePath, content }),
        });
        if (!response.ok) {
          const err = await response.json();
          throw new Error(err.error || 'Save failed');
        }
        fetchFiles();
      } catch (e) {
        console.error('Save error:', e);
        throw e;
      }
    },
    createNewFile: async (filePath: string, content: string = '') => {
      if (selectedArchive) {
        throw new Error('Cannot create files in an archived run');
      }
      try {
        const response = await fetch('/api/files/write', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: filePath, content }),
        });
        if (!response.ok) {
          const err = await response.json();
          throw new Error(err.error || 'Create failed');
        }
        fetchFiles();
      } catch (e) {
        console.error('Create file error:', e);
        throw e;
      }
    }
  };
}
