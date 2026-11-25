import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronRight, ChevronDown, Folder, Upload, FolderPlus, Loader2, Trash2, Edit3, FilePlus } from 'lucide-react';
import { clsx } from 'clsx';
import type { FileNode, ArchiveRun } from '../../hooks/useWorkspace';
import { FileTypeIcon } from './FileTypeIcon';

interface FileTreeProps {
  files: FileNode[];
  onFileSelect: (file: FileNode) => void;
  onFileOpen?: (file: FileNode) => void;
  loadChildren?: (path: string) => Promise<FileNode[]>;
  selectedPath?: string;
  loading: boolean;
  archives: ArchiveRun[];
  selectedArchive: string | null;
  onArchiveSelect: (archiveId: string | null) => void;
  uploadFiles: (files: FileList) => Promise<any>;
  deleteFile: (path: string) => Promise<void>;
  renameFile: (oldPath: string, newPath: string) => Promise<void>;
  createNewFile?: (path: string, content?: string) => Promise<void>;
  navKey?: number;
}

const CLICK_DELAY_MS = 250;

const formatArchiveLabel = (archiveId: string): string => {
  const newMatch = archiveId.match(/^quasar_run_(\d{8})_(\d{6})_[0-9a-f]{6}(?:_\d+)?$/);
  if (newMatch) {
    const date = newMatch[1];
    const time = newMatch[2];
    return `Run ${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)} ${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`;
  }
  return archiveId;
};

const FileTreeItem: React.FC<{
  node: FileNode;
  depth: number;
  onFileSelect: (file: FileNode) => void;
  onFileOpen?: (file: FileNode) => void;
  loadChildren?: (path: string) => Promise<FileNode[]>;
  selectedPath?: string;
  onDelete: (path: string) => void;
  onRename: (path: string, newName: string) => void;
  onCreateFile?: (parentPath: string, name: string) => void;
  onCreateFolder?: (parentPath: string, name: string) => void;
  onMove?: (sourcePath: string, targetPath: string) => void;
  isReadOnly?: boolean;
  navKey?: number;
}> = ({ node, depth, onFileSelect, onFileOpen, loadChildren, selectedPath, onDelete, onRename, onCreateFile, onCreateFolder, onMove, isReadOnly, navKey }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoadingChildren, setIsLoadingChildren] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(node.name);
  const [isCreatingNew, setIsCreatingNew] = useState<'file' | 'folder' | null>(null);
  const [newItemName, setNewItemName] = useState('');
  const isSelected = selectedPath === node.path;
  const [isDragOver, setIsDragOver] = useState(false);
  const clickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const childrenAlreadyLoaded = Boolean(node.childrenLoaded || node.children !== undefined);

  const ensureChildrenLoaded = useCallback(async () => {
    // children already present ⇒ treat as loaded (avoids re-fetch flash on poll re-render)
    if (!node.isDirectory || !loadChildren || childrenAlreadyLoaded) return;
    setIsLoadingChildren(true);
    try {
      await loadChildren(node.path);
    } finally {
      setIsLoadingChildren(false);
    }
  }, [childrenAlreadyLoaded, loadChildren, node.isDirectory, node.path]);

  // Auto-expand folder if it's selected or has a selected child.
  useEffect(() => {
    if (!node.isDirectory || !selectedPath) return;
    if (selectedPath === node.path || selectedPath.startsWith(node.path + '/')) {
      setIsOpen(true);
      // Only kick a load when this folder still has no children; once loaded,
      // poll re-renders must not re-trigger ensureChildrenLoaded.
      if (!childrenAlreadyLoaded) {
        void ensureChildrenLoaded();
      }
    }
  }, [childrenAlreadyLoaded, ensureChildrenLoaded, selectedPath, node.path, node.isDirectory, navKey]);

  const handleDragStart = (e: React.DragEvent) => {
    if (isReadOnly) return;
    e.dataTransfer.setData('text/plain', node.path);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    if (isReadOnly || !node.isDirectory) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    if (isReadOnly || !node.isDirectory) return;
    e.preventDefault();
    setIsDragOver(false);

    const sourcePath = e.dataTransfer.getData('text/plain');
    if (sourcePath && sourcePath !== node.path && onMove) {
      // Don't allow dropping onto itself or children
      if (!node.path.startsWith(sourcePath + '/')) {
        onMove(sourcePath, node.path);
      }
    }
  };

  const handleClick = () => {
    if (isEditing) return;
    if (node.isDirectory) {
      const nextOpen = !isOpen;
      setIsOpen(nextOpen);
      onFileSelect(node);
      if (nextOpen) {
        void ensureChildrenLoaded();
      }
      return;
    }
    // Single-click: delay then preview (so double-click can cancel and open instead)
    if (clickTimeoutRef.current) clearTimeout(clickTimeoutRef.current);
    clickTimeoutRef.current = setTimeout(() => {
      clickTimeoutRef.current = null;
      onFileSelect(node);
    }, CLICK_DELAY_MS);
  };

  const handleDoubleClick = () => {
    if (isEditing || node.isDirectory) return;
    if (clickTimeoutRef.current) {
      clearTimeout(clickTimeoutRef.current);
      clickTimeoutRef.current = null;
    }
    onFileOpen?.(node);
  };

  const handleRename = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (editName && editName !== node.name) {
        onRename(node.path, editName);
      }
      setIsEditing(false);
    } else if (e.key === 'Escape') {
      setEditName(node.name);
      setIsEditing(false);
    }
  };

  const handleCreateNew = () => {
    if (!newItemName.trim()) return;
    if (isCreatingNew === 'file' && onCreateFile) {
      onCreateFile(node.path, newItemName.trim());
    } else if (isCreatingNew === 'folder' && onCreateFolder) {
      onCreateFolder(node.path, newItemName.trim());
    }
    setNewItemName('');
    setIsCreatingNew(null);
    setIsOpen(true); // Open folder to show new item
  };

  return (
    <div>
      <div
        draggable={!isReadOnly}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={clsx(
          "flex items-center gap-2 py-1.5 px-2 rounded-lg cursor-pointer transition-colors text-sm group relative",
          isSelected ? "bg-blue-100/50 text-blue-700" : "hover:bg-slate-100 text-slate-600",
          isDragOver && node.isDirectory && "bg-blue-200/50 ring-2 ring-blue-400/50"
        )}
        style={{ paddingLeft: `${depth * 1.5 + 0.5}rem` }}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
      >
        {node.isDirectory ? (
          <>
            {isLoadingChildren ? <Loader2 size={14} className="text-blue-400 animate-spin" /> : isOpen ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
            <Folder size={16} className={clsx(isOpen ? "text-blue-500" : "text-slate-400")} />
          </>
        ) : (
          <>
            <div className="w-3.5" />
            <FileTypeIcon filename={node.name} size={16} isSelected={isSelected} />
          </>
        )}

        {isEditing ? (
          <input
            autoFocus
            type="text"
            className="flex-1 bg-white border border-blue-400 rounded px-1 -my-0.5 outline-none"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onKeyDown={handleRename}
            onBlur={() => setIsEditing(false)}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <>
            <span className="truncate flex-1">{node.name}</span>
            {!isReadOnly && (
              <div className="hidden group-hover:flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                {/* Create file/folder buttons - only for directories */}
                {node.isDirectory && onCreateFile && (
                  <button
	                  onClick={(e) => {
	                    e.stopPropagation();
	                    setIsCreatingNew('file');
	                    setIsOpen(true);
	                    void ensureChildrenLoaded();
	                  }}
                    className="p-1 hover:bg-slate-200 rounded text-slate-400 hover:text-green-500"
                    title="New File"
                  >
                    <FilePlus size={14} />
                  </button>
                )}
                {node.isDirectory && onCreateFolder && (
                  <button
	                  onClick={(e) => {
	                    e.stopPropagation();
	                    setIsCreatingNew('folder');
	                    setIsOpen(true);
	                    void ensureChildrenLoaded();
	                  }}
                    className="p-1 hover:bg-slate-200 rounded text-slate-400 hover:text-blue-500"
                    title="New Folder"
                  >
                    <FolderPlus size={14} />
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsEditing(true);
                  }}
                  className="p-1 hover:bg-slate-200 rounded text-slate-400 hover:text-blue-500"
                  title="Rename"
                >
                  <Edit3 size={14} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm(`Delete ${node.isDirectory ? 'folder' : 'file'} "${node.name}"?`)) {
                      onDelete(node.path);
                    }
                  }}
                  className="p-1 hover:bg-slate-200 rounded text-slate-400 hover:text-red-500"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {node.isDirectory && isOpen && (
        <div>
          {/* Inline input for creating new file/folder */}
          {isCreatingNew && (
            <div
              className="flex items-center gap-2 py-1.5 px-2"
              style={{ paddingLeft: `${(depth + 1) * 1.5 + 0.5}rem` }}
            >
              <div className="w-3.5" />
              {isCreatingNew === 'folder' ? (
                <FolderPlus size={16} className="text-blue-400" />
              ) : (
                <FilePlus size={16} className="text-green-400" />
              )}
              <input
                autoFocus
                type="text"
                placeholder={isCreatingNew === 'folder' ? 'folder name' : 'filename.txt'}
                value={newItemName}
                onChange={(e) => setNewItemName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateNew();
                  if (e.key === 'Escape') {
                    setIsCreatingNew(null);
                    setNewItemName('');
                  }
                }}
                onBlur={() => {
                  if (!newItemName.trim()) {
                    setIsCreatingNew(null);
                  }
                }}
                className="flex-1 bg-white border border-blue-400 rounded px-2 py-0.5 text-sm outline-none focus:ring-2 focus:ring-blue-200"
	              />
	            </div>
	          )}
	          {isLoadingChildren && (
	            <div
	              className="flex items-center gap-2 py-1.5 px-2 text-xs text-slate-400"
	              style={{ paddingLeft: `${(depth + 1) * 1.5 + 0.5}rem` }}
	            >
	              <Loader2 size={12} className="animate-spin" />
	              Loading
	            </div>
	          )}
	          {node.children?.map(child => (
	            <FileTreeItem
	              key={child.path}
              node={child}
              depth={depth + 1}
	              onFileSelect={onFileSelect}
	              onFileOpen={onFileOpen}
	              loadChildren={loadChildren}
	              selectedPath={selectedPath}
              onDelete={onDelete}
              onRename={onRename}
              onCreateFile={onCreateFile}
              onCreateFolder={onCreateFolder}
              onMove={onMove}
              isReadOnly={isReadOnly}
              navKey={navKey}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const FileTree: React.FC<FileTreeProps> = ({
  files,
  onFileSelect,
  onFileOpen,
  loadChildren,
  selectedPath,
  loading,
  archives,
  selectedArchive,
  onArchiveSelect,
  uploadFiles,
  deleteFile,
  renameFile,
  createNewFile,
  navKey
}) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const [isCreatingRoot, setIsCreatingRoot] = useState<'file' | 'folder' | null>(null);
  const [rootItemName, setRootItemName] = useState('');
  const [isRootDragOver, setIsRootDragOver] = useState(false);

  const handleRename = (path: string, newName: string) => {
    const parentPath = path.includes('/') ? path.substring(0, path.lastIndexOf('/')) : '';
    const newPath = parentPath ? `${parentPath}/${newName}` : newName;
    renameFile(path, newPath);
  };

  const handleCreateFile = async (parentPath: string, name: string) => {
    if (!createNewFile) return;
    const fullPath = parentPath ? `${parentPath}/${name}` : name;
    try {
      await createNewFile(fullPath);
    } catch (e) {
      console.error('Failed to create file:', e);
    }
  };

  const handleCreateFolder = async (parentPath: string, name: string) => {
    if (!createNewFile) return;
    // Create folder by creating a placeholder file inside it, then delete it
    // Or just create an empty file with the folder path - the API will create parent dirs
    const fullPath = parentPath ? `${parentPath}/${name}/.gitkeep` : `${name}/.gitkeep`;
    try {
      await createNewFile(fullPath);
    } catch (e) {
      console.error('Failed to create folder:', e);
    }
  };

  const handleMoveFile = async (sourcePath: string, targetDirPath: string) => {
    if (selectedArchive || !renameFile) return;

    // Calculate new path: source file name stays same, only parent dir changes
    const fileName = sourcePath.split('/').pop() || '';
    const newPath = targetDirPath ? `${targetDirPath}/${fileName}` : fileName;

    // Basic check: don't move if source and target are same
    if (sourcePath === newPath) return;

    try {
      await renameFile(sourcePath, newPath);
    } catch (e) {
      console.error('Failed to move file:', e);
    }
  };

  const handleCreateRootItem = async () => {
    if (!rootItemName.trim()) return;
    if (isCreatingRoot === 'file') {
      await handleCreateFile('', rootItemName.trim());
    } else {
      await handleCreateFolder('', rootItemName.trim());
    }
    setRootItemName('');
    setIsCreatingRoot(null);
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setIsUploading(true);
    try {
      await uploadFiles(files);
      // Clear inputs
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (folderInputRef.current) folderInputRef.current.value = '';
    } catch (e) {
      console.error('Upload failed:', e);
    } finally {
      setIsUploading(false);
    }
  };

  const handleRootDragOver = (e: React.DragEvent) => {
    if (selectedArchive) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setIsRootDragOver(true);
  };

  const handleRootDragLeave = (e: React.DragEvent) => {
    // Only set to false if we're actually leaving the container
    const rect = e.currentTarget.getBoundingClientRect();
    if (
      e.clientX <= rect.left ||
      e.clientX >= rect.right ||
      e.clientY <= rect.top ||
      e.clientY >= rect.bottom
    ) {
      setIsRootDragOver(false);
    }
  };

  const handleRootDrop = (e: React.DragEvent) => {
    if (selectedArchive) return;
    e.preventDefault();
    setIsRootDragOver(false);

    const sourcePath = e.dataTransfer.getData('text/plain');
    if (sourcePath) {
      // If dropping in root, the targetDirPath is empty string
      // Check if item is already in root
      if (sourcePath.includes('/')) {
        handleMoveFile(sourcePath, '');
      }
    }
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentLabel = selectedArchive
    ? archives.find(a => a.id === selectedArchive)?.displayId || formatArchiveLabel(selectedArchive)
    : 'Current';

  return (
    <div className="flex flex-col h-full bg-white/40 backdrop-blur-md border-r border-slate-200/50">
      <div className="p-3 border-b border-slate-200/50">
        <div className="relative w-full" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className={clsx(
              "w-full flex items-center justify-between font-semibold text-slate-700 rounded-xl px-4 py-2.5 transition-all duration-200",
              "hover:bg-gradient-to-r hover:from-blue-50 hover:to-indigo-50 hover:text-blue-700",
              "active:scale-[0.99]",
              dropdownOpen && "bg-gradient-to-r from-blue-50 to-indigo-50 text-blue-700 shadow-sm"
            )}
          >
            <span className="text-left">{currentLabel}</span>
            <ChevronDown
              size={18}
              className={clsx(
                "text-slate-400 transition-transform duration-200 flex-shrink-0",
                dropdownOpen && "rotate-180 text-blue-500"
              )}
            />
          </button>

          {dropdownOpen && (
            <div className="absolute top-full left-0 right-0 mt-2 bg-white/95 backdrop-blur-xl rounded-2xl shadow-2xl border border-white/50 py-2 z-50 overflow-hidden">
              <button
                onClick={() => {
                  onArchiveSelect(null);
                  setDropdownOpen(false);
                }}
                className={clsx(
                  "w-full text-left px-4 py-3 transition-all duration-150 flex items-center justify-between group",
                  !selectedArchive ? "bg-gradient-to-r from-blue-50 to-indigo-50 text-blue-700" : "hover:bg-slate-50"
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={clsx("w-2 h-2 rounded-full", !selectedArchive ? "bg-blue-500" : "bg-emerald-400")} />
                  <span className="font-medium">Current</span>
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-600 font-medium">Live</span>
              </button>

              {archives.map(archive => (
                <button
                  key={archive.id}
                  onClick={() => {
                    onArchiveSelect(archive.id);
                    setDropdownOpen(false);
                  }}
                  className={clsx(
                    "w-full text-left px-4 py-2.5 transition-all duration-150 group",
                    selectedArchive === archive.id ? "bg-gradient-to-r from-blue-50 to-indigo-50 text-blue-700" : "hover:bg-slate-50"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div className={clsx("w-2 h-2 rounded-full", selectedArchive === archive.id ? "bg-blue-500" : "bg-slate-300 group-hover:bg-slate-400")} />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm">{archive.displayId}</div>
                      <div className="text-xs text-slate-400 truncate">{archive.title}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {!selectedArchive && (
          <div className="grid grid-cols-4 gap-1 mt-3 p-1.5 bg-slate-100/40 rounded-xl border border-slate-200/60 backdrop-blur-sm">
             <input type="file" ref={fileInputRef} className="hidden" multiple onChange={(e) => handleUpload(e.target.files)} />
             <input type="file" ref={folderInputRef} className="hidden" {...{ webkitdirectory: "", directory: "" } as any} onChange={(e) => handleUpload(e.target.files)} />

            <button
              onClick={() => setIsCreatingRoot('file')}
              className="flex flex-col items-center justify-center gap-1 p-2 bg-white rounded-lg border border-slate-200 text-slate-500 hover:border-green-300 hover:text-green-600 hover:bg-green-50/50 transition-all duration-200 group"
              title="New File"
            >
              <FilePlus size={16} className="text-green-500 group-hover:scale-110 transition-transform" />
              <span className="text-[9px] font-bold uppercase tracking-tight">New File</span>
            </button>
            <button
              onClick={() => setIsCreatingRoot('folder')}
              className="flex flex-col items-center justify-center gap-1 p-2 bg-white rounded-lg border border-slate-200 text-slate-500 hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50/50 transition-all duration-200 group"
              title="New Folder"
            >
              <FolderPlus size={16} className="text-blue-500 group-hover:scale-110 transition-transform" />
              <span className="text-[9px] font-bold uppercase tracking-tight">New Folder</span>
            </button>

            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="flex flex-col items-center justify-center gap-1 p-2 bg-white rounded-lg border border-slate-200 text-slate-500 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50/50 transition-all duration-200 group disabled:opacity-50"
              title="Upload Files"
            >
              {isUploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} className="text-indigo-500 group-hover:scale-110 transition-transform" />}
              <span className="text-[9px] font-bold uppercase tracking-tight">Upload File</span>
            </button>
            <button
              onClick={() => folderInputRef.current?.click()}
              disabled={isUploading}
              className="flex flex-col items-center justify-center gap-1 p-2 bg-white rounded-lg border border-slate-200 text-slate-500 hover:border-violet-300 hover:text-violet-600 hover:bg-violet-50/50 transition-all duration-200 group disabled:opacity-50"
              title="Upload Folder"
            >
              {isUploading ? <Loader2 size={16} className="animate-spin" /> : <FolderPlus size={16} className="text-violet-500 group-hover:scale-110 transition-transform" />}
              <span className="text-[9px] font-bold uppercase tracking-tight">Upload Folder</span>
            </button>
          </div>
        )}
      </div>

      {/* Loading bar when workspace/files are loading (e.g. after switching Current / archived run) */}
      {loading && (
        <div className="flex-shrink-0 h-1 bg-slate-200/60 overflow-hidden" role="progressbar" aria-label="Loading workspace files">
          <div className="h-full w-1/3 min-w-[80px] bg-gradient-to-r from-transparent via-blue-500 to-transparent animate-loading-bar" />
        </div>
      )}

      <div
        onDragOver={handleRootDragOver}
        onDragLeave={handleRootDragLeave}
        onDrop={handleRootDrop}
        className={clsx(
          "flex-1 overflow-y-auto p-2 scrollbar-glass transition-colors duration-200",
          isRootDragOver && "bg-blue-50/50 ring-2 ring-inset ring-blue-400/30"
        )}
      >
        {/* Inline input for root creation */}
        {isCreatingRoot && (
          <div className="flex items-center gap-2 py-1.5 px-2 mb-1">
            <div className="w-3.5" />
            {isCreatingRoot === 'folder' ? (
              <FolderPlus size={16} className="text-blue-400" />
            ) : (
              <FilePlus size={16} className="text-green-400" />
            )}
            <input
              autoFocus
              type="text"
              placeholder={isCreatingRoot === 'folder' ? 'folder name' : 'filename.txt'}
              value={rootItemName}
              onChange={(e) => setRootItemName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateRootItem();
                if (e.key === 'Escape') {
                  setIsCreatingRoot(null);
                  setRootItemName('');
                }
              }}
              onBlur={() => {
                if (!rootItemName.trim()) {
                  setIsCreatingRoot(null);
                }
              }}
              className="flex-1 bg-white border border-blue-400 rounded px-2 py-0.5 text-sm outline-none focus:ring-2 focus:ring-blue-200"
            />
          </div>
        )}
        {files.length === 0 && !loading && !isCreatingRoot && (
          <div className="p-4 text-center text-slate-400 text-sm italic">
            No files in workspace
          </div>
        )}
        {files.map(file => (
          <FileTreeItem
            key={file.path}
            node={file}
            depth={0}
            onFileSelect={onFileSelect}
            onFileOpen={onFileOpen}
            loadChildren={loadChildren}
            selectedPath={selectedPath}
            onDelete={deleteFile}
            onRename={handleRename}
            onMove={handleMoveFile}
            onCreateFile={createNewFile ? handleCreateFile : undefined}
            onCreateFolder={createNewFile ? handleCreateFolder : undefined}
            isReadOnly={!!selectedArchive}
            navKey={navKey}
          />
        ))}
      </div>
    </div>
  );
};
