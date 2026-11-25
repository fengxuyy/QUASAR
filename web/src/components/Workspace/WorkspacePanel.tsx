import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useWorkspace } from '../../hooks/useWorkspace';
import type { FileNode } from '../../hooks/useWorkspace';
import { FileTree } from './FileTree';
import { X, Loader2, Download, Code, Box, Edit2, Save, XCircle, File, ChevronLeft } from 'lucide-react';
import { MarkdownRenderer } from '../UI/MarkdownRenderer';
import { VirtualizedCodeViewer } from './VirtualizedCodeViewer';
import { isImageFile, isCifFile, isSpreadsheetFile, isPdfFile, isMarkdownFile, isXmlFile, isHtmlFile, isBinaryFile } from '../../utils/fileHelpers';
import { CrystalStructureViewer } from './CrystalStructureViewer';
import { SpreadsheetViewer } from './SpreadsheetViewer';
import { XmlViewer } from './XmlViewer';
import { HtmlViewer } from './HtmlViewer';
import { FileTypeIcon } from './FileTypeIcon';
import { useIsMobileLayout } from '../../hooks/useMediaQuery';

export interface WorkspacePanelProps {
  initialArchive?: string | null;
  onArchiveChange?: () => void;
  initialFilePath?: string | null;
  onFilePathChange?: () => void;
  onFileRedirectNotFound?: (filePath: string) => void;
  navKey?: number;
  refreshKey?: number;
  isActive?: boolean;
}

// Initial load size for text files (500KB) - the rest can be loaded on demand
const INITIAL_LOAD_SIZE = 500000; // 500KB of text
const LOAD_MORE_SIZE = 1000000; // 1MB chunks after the initial preview
const MAX_SAFE_TEXT_LOAD = 5000000; // Keep browser-side text previews bounded
const MARKDOWN_RENDER_LIMIT = 120000;

interface OpenTab {
  file: FileNode;
  content: string | null;
  loading: boolean;
  isTruncated: boolean;
  originalSize: number;
  nextOffset?: number;
  isEditMode: boolean;
  editContent: string;
  viewMode: 'content' | 'structure';
}

// Preview state: single file shown without being pinned in tabs (replaced on next single-click)
interface PreviewState {
  file: FileNode;
  content: string | null;
  loading: boolean;
  isTruncated: boolean;
  originalSize: number;
  nextOffset?: number;
  viewMode: 'content' | 'structure';
}

export const WorkspacePanel: React.FC<WorkspacePanelProps> = ({ 
  initialArchive, 
  onArchiveChange,
  initialFilePath,
  onFilePathChange,
  onFileRedirectNotFound,
  navKey,
  refreshKey,
  isActive = true
}) => {
  const { 
    files, 
    loading, 
    refreshFiles,
    refreshArchives,
    loadDirectoryChildren,
    getFileContent, 
    getFileRawUrl,
    archives, 
    selectedArchive,
    setSelectedArchive,
    uploadFiles,
    deleteFile,
    renameFile,
    saveFileContent,
    createNewFile
  } = useWorkspace({ enabled: isActive });

  // Trigger manual refresh when refreshKey changes
  useEffect(() => {
    if (isActive && refreshKey !== undefined && refreshKey > 0) {
      refreshFiles();
      refreshArchives();
    }
  }, [isActive, refreshKey, refreshFiles, refreshArchives]);

  // Multi-tab state (pinned files - double-click to open)
  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [activeTabIndex, setActiveTabIndex] = useState<number>(-1);
  // Preview state (single-click: show file without pinning; replaced when another file is single-clicked)
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [focusedPath, setFocusedPath] = useState<string | null>(null);
  const [isStructureExpanded, setIsStructureExpanded] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Resizable sidebar state
  const [sidebarWidth, setSidebarWidth] = useState(300);
  const isResizing = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const tabsContainerRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobileLayout();
  // On phones: tree and content are mutually exclusive (list → detail)
  const [mobileShowTree, setMobileShowTree] = useState(true);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isResizing.current || !containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = moveEvent.clientX - containerRect.left;
      setSidebarWidth(Math.min(800, Math.max(280, newWidth)));
    };

    const handleMouseUp = () => {
      isResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, []);

  // Derived state: prefer active tab; otherwise show preview (single-click) if any
  const activeTab = activeTabIndex >= 0 && activeTabIndex < openTabs.length ? openTabs[activeTabIndex] : null;
  const selectedFile = activeTab?.file ?? preview?.file ?? null;
  const fileContent = activeTab?.content ?? preview?.content ?? null;
  const contentLoading = activeTab?.loading ?? preview?.loading ?? false;
  const isFileTruncated = activeTab?.isTruncated ?? preview?.isTruncated ?? false;
  const originalFileSize = activeTab?.originalSize ?? preview?.originalSize ?? 0;
  const isEditMode = activeTab?.isEditMode ?? false;
  const editContent = activeTab?.editContent ?? '';
  const viewMode = (activeTab?.viewMode ?? preview?.viewMode) ?? 'structure';
  const isPreview = !activeTab && preview !== null;
  const selectedFilePath = selectedFile?.path;

  // Update focused path when active tab changes
  useEffect(() => {
    if (selectedFile) setFocusedPath(selectedFile.path);
  }, [selectedFile]);

  // Mobile: open detail view when a file is selected
  useEffect(() => {
    if (isMobile && selectedFile && !selectedFile.isDirectory) {
      setMobileShowTree(false);
    }
  }, [isMobile, selectedFilePath, selectedFile]);

  // Reset to tree when leaving mobile layout
  useEffect(() => {
    if (!isMobile) setMobileShowTree(true);
  }, [isMobile]);

  // Set initial archive when passed from props (e.g., from History page)
  useEffect(() => {
    if (initialArchive && initialArchive !== selectedArchive) {
      setSelectedArchive(initialArchive);
    }
  }, [initialArchive, selectedArchive, setSelectedArchive, onArchiveChange]);

  // Acknowledge archive navigation only after the requested archive is selected and loaded.
  useEffect(() => {
    if (initialArchive && initialArchive === selectedArchive && !loading) {
      if (onArchiveChange) onArchiveChange();
    }
  }, [initialArchive, selectedArchive, loading, onArchiveChange]);

  // Reset all tabs and preview when archive changes
  useEffect(() => {
    setOpenTabs([]);
    setActiveTabIndex(-1);
    setPreview(null);
  }, [selectedArchive]);

  // Helper: update a specific tab's properties
  const updateTab = useCallback((index: number, updates: Partial<OpenTab>) => {
    setOpenTabs(prev => prev.map((tab, i) => i === index ? { ...tab, ...updates } : tab));
  }, []);

  const resolveImageUrl = useCallback((src: string, basePath?: string) => {
    if (!basePath) return getFileRawUrl(src);
    const parts = basePath.split('/');
    parts.pop();
    const dir = parts.join('/');
    const cleanSrc = src.replace(/^\.\//, '');
    const relativePath = dir ? `${dir}/${cleanSrc}` : cleanSrc;
    return getFileRawUrl(relativePath);
  }, [getFileRawUrl]);

  const appendMoreContent = useCallback(async (tabIndex: number) => {
    const tab = openTabs[tabIndex];
    if (!tab || !tab.isTruncated) return;
    try {
      updateTab(tabIndex, { loading: true });
      const loaded = tab.content?.length || 0;
      const nextOffset = tab.nextOffset ?? loaded;
      const result = await getFileContent(
        tab.file.path,
        Math.min(LOAD_MORE_SIZE, MAX_SAFE_TEXT_LOAD - loaded),
        nextOffset
      );
      updateTab(tabIndex, {
        content: `${tab.content || ''}${result.content}`,
        loading: false,
        isTruncated: result.truncated,
        originalSize: result.totalSize,
        nextOffset: result.nextOffset,
      });
    } catch (e) {
      updateTab(tabIndex, { loading: false });
      console.error('Failed to load full file:', e);
    }
  }, [openTabs, getFileContent, updateTab]);

  // Single-click: preview file (replace current preview; do not add tab)
  const handleFilePreview = useCallback(async (file: FileNode) => {
    setFocusedPath(file.path);
    if (file.isDirectory) return;

    const shouldLoad = !isBinaryFile(file.name) && !isSpreadsheetFile(file.name);
    setPreview({
      file,
      content: null,
      loading: shouldLoad,
      isTruncated: false,
      originalSize: 0,
      viewMode: 'structure',
    });

    if (shouldLoad) {
      try {
        const result = await getFileContent(file.path, INITIAL_LOAD_SIZE);
        setPreview(prev => prev && prev.file.path === file.path ? {
          ...prev,
          content: result.content,
          loading: false,
          isTruncated: result.truncated,
          originalSize: result.totalSize,
          nextOffset: result.nextOffset,
        } : prev);
      } catch (e) {
        setPreview(prev => prev && prev.file.path === file.path ? { ...prev, content: "Error loading file content.", loading: false } : prev);
      }
    } else {
      setPreview(prev => prev && prev.file.path === file.path ? { ...prev, loading: false } : prev);
    }
  }, [getFileContent]);

  // Double-click: pin file (add to tabs or switch to existing tab)
  const handleFileOpen = useCallback(async (file: FileNode) => {
    setFocusedPath(file.path);
    if (file.isDirectory) return;

    const existingIndex = openTabs.findIndex(tab => tab.file.path === file.path);
    if (existingIndex >= 0) {
      setActiveTabIndex(existingIndex);
      if (preview?.file.path === file.path) setPreview(null);
      return;
    }

    let content: string | null = null;
    let isTruncated = false;
    let originalSize = 0;
    let nextOffset: number | undefined;
    const shouldLoad = !isBinaryFile(file.name) && !isSpreadsheetFile(file.name);

    if (shouldLoad) {
      try {
        const result = await getFileContent(file.path, INITIAL_LOAD_SIZE);
        content = result.content;
        isTruncated = result.truncated;
        originalSize = result.totalSize;
        nextOffset = result.nextOffset;
      } catch (e) {
        content = "Error loading file content.";
      }
    }

    const newTab: OpenTab = {
      file,
      content,
      loading: false,
      isTruncated,
      originalSize,
      nextOffset,
      isEditMode: false,
      editContent: '',
      viewMode: 'structure',
    };

    setOpenTabs(prev => {
      const duplicate = prev.findIndex(tab => tab.file.path === file.path);
      if (duplicate >= 0) {
        setActiveTabIndex(duplicate);
        return prev;
      }
      const newTabs = [...prev, newTab];
      setActiveTabIndex(newTabs.length - 1);
      return newTabs;
    });
    if (preview?.file.path === file.path) setPreview(null);
  }, [openTabs, preview?.file.path, getFileContent]);

  // Effect to handle external file selection (e.g., from execution log hyperlinks)
  // Placed after handleFileOpen so TypeScript can see the declaration.
  useEffect(() => {
    if (loading) {
      return;
    }

    // When both archive and file are provided (e.g. log hyperlink from history trace),
    // wait until the target archive is actually selected before resolving file paths.
    if (initialArchive && initialArchive !== selectedArchive) {
      return;
    }

    if (initialFilePath && (files.length > 0 || initialFilePath === '.')) {
      if (initialFilePath === '.') {
        // Don't close tabs, just clear selection
        setFocusedPath(null);
        if (onFilePathChange) onFilePathChange();
        return;
      }

      const findFile = (nodes: FileNode[], targetPath: string): FileNode | null => {
        // Normalize: strip leading "./" or "/" so paths like "./results/a.py" and "results/a.py" both match
        const normalizedTarget = targetPath.replace(/^\.?\/+/, '');

        let exactMatch: FileNode | null = null;
        const fuzzyMatches: FileNode[] = [];

        const search = (nodeList: FileNode[]) => {
          for (const node of nodeList) {
            if (node.path === normalizedTarget) {
              exactMatch = node;
              return; // Exact match found — no need to search further
            }
            // Fuzzy: match by bare name or path suffix (e.g. target "a.py" matches "results/a.py")
            if (
              node.name === normalizedTarget ||
              node.path.endsWith('/' + normalizedTarget)
            ) {
              fuzzyMatches.push(node);
            }
            if (node.children) {
              search(node.children);
              if (exactMatch) return;
            }
          }
        };

        search(nodes);

        if (exactMatch) return exactMatch;
        // Only use a fuzzy match when it is unambiguous (exactly one candidate)
        return fuzzyMatches.length === 1 ? fuzzyMatches[0] : null;
      };

      /**
       * Resolve a file by fetching its parent directory listing directly
       * from the server API.  This avoids calling loadDirectoryChildren
       * (which triggers setFiles → re-render → effect cleanup → cancelled)
       * and the resulting race condition.
       * Handles both nested files (results/out.csv) and top-level files
       * that may have been created after the last tree refresh.
       * Falls back to a name-based search when the file isn't at the
       * expected path (e.g. bare "script.py" is actually at "task_1/script.py").
       */
      const resolveFileFromServer = async (
        targetPath: string,
      ): Promise<FileNode | null> => {
        const normalizedTarget = targetPath.replace(/^\.?\/+/, '');
        if (!normalizedTarget) return null;

        const lastSlash = normalizedTarget.lastIndexOf('/');
        const parentPath = lastSlash === -1 ? '' : normalizedTarget.substring(0, lastSlash);
        const fileName = lastSlash === -1 ? normalizedTarget : normalizedTarget.substring(lastSlash + 1);

        // 1. Primary lookup: fetch the expected parent directory
        try {
          const pathQuery = parentPath ? `&path=${encodeURIComponent(parentPath)}` : '';
          const url = selectedArchive
            ? `/api/archive/files?runId=${encodeURIComponent(selectedArchive)}&depth=0${pathQuery}`
            : `/api/files?depth=0${pathQuery}`;

          const response = await fetch(url);
          if (response.ok) {
            const children: FileNode[] = await response.json();
            const found = children.find((n) => n.path === normalizedTarget);
            if (found) return found;
          }
        } catch {
          // fall through to name-based search
        }

        // 2. Fallback: search the workspace tree by filename (depth=3)
        //    Handles cases where the status message has a bare filename but the
        //    file lives inside a subdirectory (e.g. "preprocess_si.py" → "task_1/preprocess_si.py").
        try {
          const url = selectedArchive
            ? `/api/archive/files?runId=${encodeURIComponent(selectedArchive)}&depth=3`
            : '/api/files?depth=3';

          const response = await fetch(url);
          if (!response.ok) return null;
          const tree: FileNode[] = await response.json();

          // Collect all files that match by name
          const matches: FileNode[] = [];
          const searchTree = (nodes: FileNode[]) => {
            for (const node of nodes) {
              if (node.name === fileName && !node.isDirectory) {
                matches.push(node);
              }
              if (node.children) {
                searchTree(node.children);
              }
            }
          };
          searchTree(tree);

          // Only use the result when unambiguous (exactly one match)
          if (matches.length === 1) return matches[0];
        } catch {
          // give up
        }

        return null;
      };

      // Use an async IIFE so the effect can await server-side resolution
      let cancelled = false;
      (async () => {
        // 1. Try the already-loaded tree first (instant)
        let fileToSelect = findFile(files, initialFilePath);

        // 2. If not found and path is nested, ask the server directly
        if (!fileToSelect) {
          fileToSelect = await resolveFileFromServer(initialFilePath);
        }

        if (cancelled) return;

        if (fileToSelect) {
          setFocusedPath(fileToSelect.path);
          if (!fileToSelect.isDirectory) {
            handleFilePreview(fileToSelect);
          }
          if (onFilePathChange) onFilePathChange();

          // 3. Expand ancestor directories in the tree (fire-and-forget)
          //    so the sidebar shows the file in its proper location.
          //    Use the resolved path (fileToSelect.path) — it may differ from
          //    initialFilePath when a bare filename resolves to a subdirectory.
          const resolvedPath = fileToSelect.path;
          if (resolvedPath.includes('/')) {
            const segments = resolvedPath.split('/');
            (async () => {
              for (let i = 0; i < segments.length - 1; i++) {
                const dirPath = segments.slice(0, i + 1).join('/');
                try {
                  await loadDirectoryChildren(dirPath);
                } catch {
                  break;
                }
              }
            })();
          }
        } else {
          if (onFileRedirectNotFound) onFileRedirectNotFound(initialFilePath);
          if (onFilePathChange) onFilePathChange();
        }
      })();

      return () => { cancelled = true; };
    }
  }, [
    initialArchive,
    selectedArchive,
    initialFilePath,
    loading,
    files,
    onFilePathChange,
    onFileRedirectNotFound,
    navKey,
    handleFilePreview,
    loadDirectoryChildren
  ]);

  const closeTab = (index: number, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation();
    }
    setOpenTabs(prev => {
      const newTabs = prev.filter((_, i) => i !== index);
      // Adjust active tab index
      if (newTabs.length === 0) {
        setActiveTabIndex(-1);
      } else if (index === activeTabIndex) {
        // Closed the active tab - switch to the one before, or first
        setActiveTabIndex(Math.min(index, newTabs.length - 1));
      } else if (index < activeTabIndex) {
        // Closed a tab before the active one - shift index down
        setActiveTabIndex(activeTabIndex - 1);
      }
      return newTabs;
    });
  };

  const handleStartEdit = () => {
    if (activeTabIndex >= 0 && fileContent !== null) {
      updateTab(activeTabIndex, { isEditMode: true, editContent: fileContent });
    }
  };

  const handleCancelEdit = () => {
    if (activeTabIndex >= 0) {
      updateTab(activeTabIndex, { isEditMode: false, editContent: '' });
    }
  };

  const handleSave = async () => {
    if (!selectedFile || activeTabIndex < 0) return;
    setIsSaving(true);
    try {
      await saveFileContent(selectedFile.path, editContent);
      updateTab(activeTabIndex, { content: editContent, isEditMode: false });
    } catch (e) {
      console.error('Save failed:', e);
    } finally {
      setIsSaving(false);
    }
  };

  const downloadFile = () => {
    if (!selectedFile) return;
    const a = document.createElement('a');
    a.download = selectedFile.name;
    let objectUrl: string | null = null;
    if (fileContent !== null) {
      const blob = new Blob([fileContent], { type: 'text/plain' });
      objectUrl = URL.createObjectURL(blob);
      a.href = objectUrl;
    } else {
      a.href = getFileRawUrl(selectedFile.path);
    }
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  };

  const setViewMode = (mode: 'content' | 'structure') => {
    if (activeTabIndex >= 0) {
      updateTab(activeTabIndex, { viewMode: mode });
    } else if (preview) {
      setPreview(prev => prev ? { ...prev, viewMode: mode } : null);
    }
  };

  const loadSpreadsheetTextPreview = useCallback(() => {
    if (!selectedFilePath) {
      return Promise.resolve({ content: '', totalSize: 0, truncated: false });
    }
    return getFileContent(selectedFilePath, INITIAL_LOAD_SIZE);
  }, [getFileContent, selectedFilePath]);

  const loadFullContentForPreview = useCallback(async () => {
    if (!preview || !preview.isTruncated) return;
    try {
      setPreview(prev => prev ? { ...prev, loading: true } : null);
      const loaded = preview.content?.length || 0;
      const nextOffset = preview.nextOffset ?? loaded;
      const result = await getFileContent(
        preview.file.path,
        Math.min(LOAD_MORE_SIZE, MAX_SAFE_TEXT_LOAD - loaded),
        nextOffset
      );
      setPreview(prev => prev ? {
        ...prev,
        content: `${prev.content || ''}${result.content}`,
        loading: false,
        isTruncated: result.truncated,
        originalSize: result.totalSize,
        nextOffset: result.nextOffset,
      } : null);
    } catch (e) {
      setPreview(prev => prev ? { ...prev, loading: false } : null);
    }
  }, [preview, getFileContent]);

  const showTreePane = !isStructureExpanded && (!isMobile || mobileShowTree);
  const showContentPane = !isMobile || !mobileShowTree || isStructureExpanded;

  return (
    <div ref={containerRef} className="flex h-full w-full flex-col overflow-hidden rounded-none border-0 border-slate-200/80 bg-white/75 shadow-sm backdrop-blur-2xl animate-fade-in sm:rounded-2xl sm:border">
      {/* Workspace Top Header Bar */}
      <div className="flex flex-shrink-0 items-center justify-between gap-2 border-b border-slate-200/60 bg-white/50 px-3 py-2.5 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          {isMobile && !mobileShowTree && selectedFile && !selectedFile.isDirectory && (
            <button
              type="button"
              onClick={() => setMobileShowTree(true)}
              className="inline-flex min-h-[36px] min-w-[36px] shrink-0 items-center justify-center rounded-lg border border-slate-200/80 bg-white/80 text-slate-600 shadow-sm active:bg-slate-50"
              aria-label="Back to file tree"
            >
              <ChevronLeft size={18} />
            </button>
          )}
          <span className="truncate text-xs font-bold text-slate-800">
            {isMobile && !mobileShowTree && selectedFile
              ? selectedFile.name
              : 'Workspace Filesystem'}
          </span>
          <span className="hidden text-slate-300 sm:inline">/</span>
          <span className="hidden truncate text-xs font-medium text-slate-500 sm:inline">
            Active project directory & visualizer
          </span>
        </div>
      </div>

      <div className="flex min-h-0 w-full flex-1 overflow-hidden">
        {/* Left Panel: File Tree - full-width on mobile list view */}
        {showTreePane && (
        <>
          <div
            className={isMobile ? 'min-w-0 w-full flex-1' : undefined}
            style={
              isMobile
                ? undefined
                : { width: sidebarWidth, minWidth: 280, maxWidth: 800, flexShrink: 0 }
            }
          >
            <FileTree 
              files={files} 
              onFileSelect={handleFilePreview} 
              onFileOpen={handleFileOpen}
              loadChildren={loadDirectoryChildren}
              selectedPath={focusedPath || selectedFile?.path}
              loading={loading}
              archives={archives}
              selectedArchive={selectedArchive}
              onArchiveSelect={setSelectedArchive}
              uploadFiles={uploadFiles}
              deleteFile={deleteFile}
              renameFile={renameFile}
              createNewFile={createNewFile}
              navKey={navKey}
            />
          </div>
          {/* Resize Handle — desktop only */}
          {!isMobile && (
            <div
              onMouseDown={handleMouseDown}
              className="group relative flex-shrink-0 cursor-col-resize"
              style={{ width: 6 }}
            >
              <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-[2px] bg-slate-200/60 group-hover:bg-blue-400 group-active:bg-blue-500 transition-colors duration-150" />
            </div>
          )}
        </>
      )}

      {/* Right Panel: Tab Bar + File Content */}
      {showContentPane && (
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-white/10 backdrop-blur-[2px]">
        {/* Tab Bar */}
        {openTabs.length > 0 && !isStructureExpanded && (
          <div className="flex min-h-[40px] items-center border-b border-slate-200/50 bg-white/20">
            <div 
              ref={tabsContainerRef}
              className="flex flex-1 items-center overflow-x-auto scrollbar-glass"
              style={{ scrollbarWidth: 'thin' }}
            >
              {openTabs.map((tab, index) => (
                <button
                  key={tab.file.path}
                  onClick={() => setActiveTabIndex(index)}
                  className={`group/tab flex min-w-0 max-w-[200px] items-center gap-1.5 whitespace-nowrap border-r border-slate-200/30 px-3 py-2 text-sm font-medium transition-all duration-150 ${
                    index === activeTabIndex
                      ? 'border-b-2 border-b-blue-500 bg-white/40 text-blue-600'
                      : 'text-slate-500 hover:bg-white/20 hover:text-slate-700'
                  }`}
                >
                  <FileTypeIcon filename={tab.file.name} size={14} isSelected={index === activeTabIndex} />
                  <span className="truncate">{tab.file.name}</span>
                  <span
                    onClick={(e) => closeTab(index, e)}
                    className="ml-1 flex-shrink-0 rounded p-0.5 text-slate-400 opacity-100 hover:bg-slate-200/60 hover:text-slate-600 sm:opacity-0 sm:group-hover/tab:opacity-100 transition-opacity"
                  >
                    <X size={12} />
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {selectedFile && !selectedFile.isDirectory ? (
          <>
            {/* Header - hidden when structure is expanded */}
            {!isStructureExpanded && (
              <div className="flex flex-col gap-2 border-b border-slate-200/50 bg-white/20 p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
                <div className="flex min-w-0 items-center gap-2">
                  <FileTypeIcon filename={selectedFile.name} size={18} isSelected />
                  <span className="truncate font-medium text-slate-700 text-sm sm:text-base" title={selectedFile.path}>
                    {isMobile ? selectedFile.name : selectedFile.path}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                  {/* Edit/Save buttons - only show for editable text files, and only in content mode for structure files */}
                  {!selectedArchive && !isBinaryFile(selectedFile.name) && !isImageFile(selectedFile.name) && !isPdfFile(selectedFile.name) && !isSpreadsheetFile(selectedFile.name) && !(isCifFile(selectedFile.name) && viewMode === 'structure') && (
                    isEditMode ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={handleSave}
                          disabled={isSaving}
                          className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-green-500 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-green-600 disabled:opacity-50"
                          title="Save"
                        >
                          {isSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                          Save
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-200"
                          title="Cancel"
                        >
                          <XCircle size={14} />
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={handleStartEdit}
                        className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-600 transition-colors hover:bg-blue-100"
                        title="Edit"
                      >
                        <Edit2 size={14} />
                        Edit
                      </button>
                    )
                  )}

                  {/* Toggle buttons for CIF files */}
                  {isCifFile(selectedFile.name) && (
                    <div className="flex items-center bg-white/30 rounded-lg p-0.5">
                      <button
                        onClick={() => setViewMode('content')}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                          viewMode === 'content'
                            ? 'bg-white text-blue-600 shadow-sm'
                            : 'text-slate-500 hover:text-slate-700'
                        }`}
                      >
                        <Code size={14} />
                        Content
                      </button>
                      <button
                        onClick={() => setViewMode('structure')}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                          viewMode === 'structure'
                            ? 'bg-white text-blue-600 shadow-sm'
                            : 'text-slate-500 hover:text-slate-700'
                        }`}
                      >
                        <Box size={14} />
                        Structure
                      </button>
                    </div>
                  )}
                  
                  <button 
                    onClick={downloadFile}
                    className="p-1.5 rounded-lg hover:bg-white/50 transition-colors text-slate-500"
                    title="Download"
                  >
                    <Download size={18} />
                  </button>
                  <button 
                    onClick={() => isPreview ? setPreview(null) : (activeTabIndex >= 0 && closeTab(activeTabIndex))}
                    className="p-1.5 rounded-lg hover:bg-white/50 transition-colors text-slate-500"
                    title={isPreview ? 'Close preview' : 'Close tab'}
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>
            )}
            
            <div className="flex-1 overflow-auto scrollbar-glass p-6 font-mono text-sm text-slate-700 selection:bg-blue-100">
              {contentLoading ? (
                <div className="h-full flex flex-col items-center justify-center gap-3">
                  <Loader2 size={32} className="animate-spin text-blue-500" />
                  <span className="text-slate-400">Loading file content</span>
                </div>
              ) : isImageFile(selectedFile.name) ? (
                <div className="h-full flex items-center justify-center">
                  <img 
                    src={getFileRawUrl(selectedFile.path)} 
                    alt={selectedFile.name}
                    className="max-w-full max-h-full rounded-xl shadow-lg border border-white/50 object-contain"
                  />
                </div>
              ) : isCifFile(selectedFile.name) && viewMode === 'structure' ? (
                <div className="h-full">
                  {fileContent ? (
                    <CrystalStructureViewer 
                      cifContent={fileContent} 
                      fileName={selectedFile.name}
                      isExpanded={isStructureExpanded}
                      onToggleExpand={() => setIsStructureExpanded(!isStructureExpanded)}
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-slate-400">
                      No CIF content available
                    </div>
                  )}
                </div>
              ) : isSpreadsheetFile(selectedFile.name) ? (
                <div className="h-full">
                  <SpreadsheetViewer 
                    filePath={selectedFile.path} 
                    fileUrl={getFileRawUrl(selectedFile.path)} 
                    fileSize={selectedFile.size}
                    loadTextPreview={loadSpreadsheetTextPreview}
                  />
                </div>
              ) : isPdfFile(selectedFile.name) ? (
                <div className="h-full bg-slate-100 rounded-xl overflow-hidden">
                  <iframe 
                    src={getFileRawUrl(selectedFile.path)} 
                    className="w-full h-full border-0"
                    title={selectedFile.name}
                  />
                </div>
              ) : isHtmlFile(selectedFile.name) && fileContent ? (
                <div className="h-full">
                  <HtmlViewer 
                    content={fileContent} 
                    fileName={selectedFile.name}
                    fileUrl={getFileRawUrl(selectedFile.path)}
                  />
                </div>
              ) : isXmlFile(selectedFile.name) && fileContent ? (
                <div className="h-full">
                  <XmlViewer 
                    content={fileContent} 
                    fileName={selectedFile.name}
                  />
                </div>
              ) : isBinaryFile(selectedFile.name) ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-400">
                  <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                    <File size={32} className="text-slate-300" />
                  </div>
                  <h4 className="font-semibold text-slate-500 mb-1">Binary File</h4>
                  <p className="text-sm">This file cannot be displayed as text.</p>
                  <button 
                    onClick={() => {
                      const a = document.createElement('a');
                      a.href = getFileRawUrl(selectedFile.path);
                      a.download = selectedFile.name;
                      document.body.appendChild(a);
                      a.click();
                      document.body.removeChild(a);
                    }}
                    className="mt-4 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                  >
                    Download File
                  </button>
                </div>
              ) : (
                <div className="h-full flex flex-col">
                  {isFileTruncated && (
                    <div className="flex items-center justify-between px-4 py-2 bg-amber-50 border-b border-amber-200 text-amber-700 text-sm">
                      <span>
                        Showing first {(fileContent?.length ? (fileContent.length / 1024).toFixed(0) : '?')}KB of {(originalFileSize / 1024).toFixed(0)}KB
                        {fileContent ? ` (${fileContent.split('\n').length.toLocaleString()} lines loaded)` : ''}
                      </span>
                      <div className="flex items-center gap-2">
                        <button 
                          onClick={() => isPreview ? loadFullContentForPreview() : (activeTabIndex >= 0 && appendMoreContent(activeTabIndex))}
                          disabled={(fileContent?.length || 0) >= MAX_SAFE_TEXT_LOAD}
                          className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors text-sm"
                        >
                          {(fileContent?.length || 0) >= MAX_SAFE_TEXT_LOAD ? 'Preview Limit Reached' : 'Load More'}
                        </button>
                        <button 
                          onClick={() => {
                            const a = document.createElement('a');
                            a.href = getFileRawUrl(selectedFile.path);
                            a.download = selectedFile.name;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                          }}
                          className="px-3 py-1 bg-amber-500 text-white rounded hover:bg-amber-600 transition-colors text-sm"
                        >
                          Download
                        </button>
                      </div>
                    </div>
                  )}
                  <div className="flex-1 overflow-hidden">
                    {isEditMode ? (
                      <textarea
                        value={editContent}
                        onChange={(e) => activeTabIndex >= 0 && updateTab(activeTabIndex, { editContent: e.target.value })}
                        className="w-full h-full min-h-[400px] p-4 font-mono text-sm bg-slate-50 border-0 outline-none resize-none focus:ring-2 focus:ring-blue-200 rounded-lg"
                        placeholder="Enter file content"
                        spellCheck={false}
                      />
                    ) : isMarkdownFile(selectedFile.name) && !isFileTruncated && (fileContent?.length || 0) <= MARKDOWN_RENDER_LIMIT ? (
                      <div className="overflow-auto h-full">
                        <MarkdownRenderer 
                          content={fileContent || "_File is empty_"} 
                          basePath={selectedFile.path}
                          resolveImageUrl={resolveImageUrl}
                        />
                      </div>
                    ) : (
                      <div className="h-full flex flex-col">
                        {isMarkdownFile(selectedFile.name) && (
                          <div className="flex-shrink-0 px-4 py-2 bg-blue-50 border-b border-blue-100 text-blue-700 text-xs font-sans">
                            Large Markdown preview is shown as virtualized text for responsiveness.
                          </div>
                        )}
                        <VirtualizedCodeViewer
                          content={fileContent || ''}
                          filename={selectedFile.name}
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-400 p-8 text-center animate-fade-in">
            <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
               <File size={32} className="text-slate-300" />
            </div>
            <h4 className="font-semibold text-slate-500 mb-1">No File Selected</h4>
            <p className="text-sm">Select a file from the workspace to view its contents.</p>
          </div>
        )}
      </div>
      )}
    </div>
    </div>
  );
};
