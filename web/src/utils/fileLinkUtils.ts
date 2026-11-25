/**
 * Utility functions for parsing and rendering file links in status messages.
 */

export interface StatusSegment {
  type: 'text' | 'file' | 'italic';
  content: string;
  filePath?: string; // Full path for file segments
}

export interface WorkspaceLinkTarget {
  archiveId: string | null;
  filePath: string;
}

const ARCHIVE_ROOT_NAME = 'quasar_archive';

// Whitelist of common file extensions to reduce false positives
const FILE_EXTENSIONS = ['py', 'sh', 'cif', 'csv', 'txt', 'json', 'md', 'xyz', 'qc', 'bash', 'zsh', 'log', 'out', 'in', 'c', 'cpp', 'h', 'hpp', 'js', 'ts', 'tsx', 'html', 'css', 'yaml', 'yml', 'toml', 'xml', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tif', 'tiff', 'pdb', 'mol', 'sdf', 'inp', 'fchk', 'cube', 'def', 'data', 'vasp', 'poscar', 'contcar', 'outcar', 'incar', 'kpoints', 'potcar', 'gjf', 'com', 'g09', 'g16'];

/**
 * Patterns to match file references in status messages.
 * Matches patterns like:
 * - Executed 'script.py'
 * - Executing `results/script.py`
 * - Read subdir/analysis.py
 *
 * Uses a whitelist of extensions and ensures the match is either:
 * 1. Wrapped in quotes or backticks (allows path separators, e.g. 'results/data.csv')
 * 2. Preceded by a space or start of line (when not wrapped, also allows path separators)
 */
const FILE_REFERENCE_PATTERN = new RegExp(
  `(['\`])([\\w./-]+\\.(?:${FILE_EXTENSIONS.join('|')}))\\1|` + // Case 1: Wrapped in quotes/backticks
  `(?<=\\s|^)([\\w./-]+\\.(?:${FILE_EXTENSIONS.join('|')}))(?=\\s|$|[,;:)])`, // Case 2: Unwrapped with boundaries
  'g'
);

const DIRECTORY_PATH_PATTERN = '(?:workspace/?|[\\w](?:[\\w./-]*[\\w])?/?)';

const LISTED_PATTERN = new RegExp(
  `^((?:Listing|Listed)\\s+)(${DIRECTORY_PATH_PATTERN})(\\s*\\(.*\\))?$`
);

/**
 * Multi-directory list_directory status: "Listed task_3, task_4" or nested paths.
 * Single-dir glob forms like "Listed dir (*.py)" must not be split on commas inside (...).
 */
function tryParseListedCommaSeparatedPaths(status: string): StatusSegment[] | null {
  const prefixMatch = status.match(/^((?:Listing|Listed)\s+)(.+)$/);
  if (!prefixMatch) return null;
  const rest = prefixMatch[2];
  if (!rest.includes(',')) return null;

  const firstComma = rest.indexOf(',');
  const openParen = rest.indexOf('(');
  if (openParen !== -1 && firstComma > openParen) {
    return null;
  }

  const parts = rest
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length < 2) return null;

  const segments: StatusSegment[] = [{ type: 'text', content: prefixMatch[1] }];
  for (let i = 0; i < parts.length; i++) {
    const filePath = normalizeWorkspacePath(parts[i]);
    if (!isNavigablePath(filePath)) {
      return null;
    }
    if (i > 0) {
      segments.push({ type: 'text', content: ', ' });
    }
    segments.push({
      type: 'file',
      content: getPathDisplayName(parts[i]),
      filePath,
    });
  }
  return segments;
}

/**
 * Pattern to match "Read X" or "Read X file not found" where X might be a folder
 * (doesn't have a file extension). This allows folders/paths to be hyperlinked.
 * Captures: 1=prefix ("Read "), 2=name (may include path separators), 3=optional suffix
 */
const READ_FOLDER_PATTERN = new RegExp(
  `^(Read(?:ing)?\\s+)(${DIRECTORY_PATH_PATTERN})(\\s+(?:file not found|L\\d+.*)?)?$`
);


/**
 * Pattern to match "Executed X..." where X is inline code (not a file with extension)
 * Matches the code content after "Executed " or "Executing " that doesn't have a file extension
 * Supports optional wrapping in quotes/backticks and optional trailing ellipses or [Trial]
 */
const EXECUTED_INLINE_PATTERN = /^(Executed\s+|Executing\s+)(['`])?(.+?)\2?(\.{3})?(\s*\[Trial\])?$/;

/**
 * Pattern to match "Queried RAG X in Y" where X is the query content
 */
const QUERIED_RAG_PATTERN = /^(Queried RAG\s+)(.+?)(\s+in\s+\w+)?(\s*\[Trial\])?$/;

/**
 * Pattern to match "Grepped files X" or "Searched files X" where X is the grep pattern
 */
const GREPPED_FILES_PATTERN = /^(Grepped files\s+|Searched files\s+)(.+?)(\s+in\s+[\w.-]+)?\s*(\(\d+ matches.*?\))?$/;

/**
 * Pattern to match "Searched X" where X is the web search query
 */
const SEARCHED_PATTERN = /^(Searched\s+)(.+?)\s*(\(\d+ results.*?\))?$/;

/**
 * Parse a status message and extract file references as segments.
 * Returns an array of segments where file names and directories are marked for linking
 * and code/queries are marked for italicization.
 * 
 * @param status - The status message to parse (e.g., "Executed 'script.py'")
 * @returns Array of segments with type 'text', 'file', or 'italic'
 */
export function parseStatusWithFileLinks(status: string): StatusSegment[] {
  if (!status) return [];
  
  // Don't create hyperlinks for "not found" errors - file doesn't exist so can't navigate
  // Matches patterns like "cu_scf_k8.out not found" or "file not found"
  if (status.toLowerCase().includes('not found')) {
    return [{ type: 'text', content: status }];
  }
  
  // Check for "Listing/Listed X" pattern (directory listing)
  const listedMatch = status.match(LISTED_PATTERN);
  if (listedMatch) {
    const dirName = listedMatch[2];
    const filePath = normalizeWorkspacePath(dirName);

    if (!isNavigablePath(filePath)) {
      return [{ type: 'text', content: status }];
    }
    
    const segments: StatusSegment[] = [
      { type: 'text', content: listedMatch[1] },
      { type: 'file', content: getPathDisplayName(dirName), filePath }
    ];
    if (listedMatch[3]) {
      segments.push({ type: 'text', content: listedMatch[3] });
    }
    return segments;
  }

  const listedMulti = tryParseListedCommaSeparatedPaths(status);
  if (listedMulti) {
    return listedMulti;
  }
  
  // Check for "Read X" pattern where X might be a folder (no file extension)
  // This handles cases like "Read run_example" or "Read run_example file not found"
  const readFolderMatch = status.match(READ_FOLDER_PATTERN);
  if (readFolderMatch) {
    const name = readFolderMatch[2];
    // Check if it doesn't have a recognized file extension (likely a folder)
    const hasFileExtension = FILE_EXTENSIONS.some(ext => name.toLowerCase().endsWith(`.${ext}`));
    
    if (!hasFileExtension) {
      const normalizedPath = normalizeWorkspacePath(name);
      if (!isNavigablePath(normalizedPath)) {
        return [{ type: 'text', content: status }];
      }

      const segments: StatusSegment[] = [
        { type: 'text', content: readFolderMatch[1] },
        { type: 'file', content: getPathDisplayName(name), filePath: normalizedPath }
      ];
      if (readFolderMatch[3]) {
        segments.push({ type: 'text', content: readFolderMatch[3] });
      }
      return segments;
    }
  }
  
  // Check for "Executed/Executing inline_code..." pattern (not a file)
  const executedMatch = status.match(EXECUTED_INLINE_PATTERN);
  if (executedMatch) {
    const content = executedMatch[3];
    // Improved extension check: look for sequence of non-space chars ending in .ext
    // This avoids matching "pymatgen.core" as a file if "core" isn't an extension
    const hasFileExtension = FILE_EXTENSIONS.some(ext => {
      const escapedExt = ext.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const extRegex = new RegExp(`\\.\\b${escapedExt}\\b(?:\\s|$)`);
      return extRegex.test(content);
    });
    
    if (!hasFileExtension && content.length > 0) {
      const segments: StatusSegment[] = [
        { type: 'text', content: executedMatch[1] },
        { type: 'italic', content: content }
      ];
      if (executedMatch[4]) {
        segments.push({ type: 'text', content: executedMatch[4] });
      }
      if (executedMatch[5]) {
        segments.push({ type: 'text', content: executedMatch[5] });
      }
      return segments;
    }
  }
  
  // Check for "Queried RAG X in Y" pattern
  const ragMatch = status.match(QUERIED_RAG_PATTERN);
  if (ragMatch) {
    const segments: StatusSegment[] = [
      { type: 'text', content: ragMatch[1] },
      { type: 'italic', content: ragMatch[2] }
    ];
    if (ragMatch[3]) {
      segments.push({ type: 'text', content: ragMatch[3] });
    }
    if (ragMatch[4]) {
      segments.push({ type: 'text', content: ragMatch[4] });
    }
    return segments;
  }
  
  // Check for "Grepped files X" or "Searched files X" pattern
  const greppedFilesMatch = status.match(GREPPED_FILES_PATTERN);
  if (greppedFilesMatch) {
    const segments: StatusSegment[] = [
      { type: 'text', content: greppedFilesMatch[1] },
      { type: 'italic', content: greppedFilesMatch[2] }
    ];
    if (greppedFilesMatch[3]) {
      segments.push({ type: 'text', content: greppedFilesMatch[3] });
    }
    if (greppedFilesMatch[4]) {
      segments.push({ type: 'text', content: " " + greppedFilesMatch[4] });
    }
    return segments;
  }
  
  // Check for "Searched X" pattern
  const searchedMatch = status.match(SEARCHED_PATTERN);
  if (searchedMatch) {
    const segments: StatusSegment[] = [
      { type: 'text', content: searchedMatch[1] },
      { type: 'italic', content: searchedMatch[2] }
    ];
    if (searchedMatch[3]) {
      segments.push({ type: 'text', content: " " + searchedMatch[3] });
    }
    return segments;
  }
  
  const segments: StatusSegment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  
  // Reset regex state
  FILE_REFERENCE_PATTERN.lastIndex = 0;
  
  while ((match = FILE_REFERENCE_PATTERN.exec(status)) !== null) {
    // Add text before the match
    if (match.index > lastIndex) {
      segments.push({
        type: 'text',
        content: status.slice(lastIndex, match.index)
      });
    }
    
    // Group 2 is the file name for wrapped matches, Group 3 is for unwrapped matches
    const fileName = match[2] || match[3] || match[0];
    const filePath = normalizeWorkspacePath(fileName);
    segments.push({
      type: 'file',
      content: getPathDisplayName(fileName),
      filePath
    });
    
    lastIndex = match.index + match[0].length;
  }
  
  // Add remaining text after last match
  if (lastIndex < status.length) {
    segments.push({
      type: 'text',
      content: status.slice(lastIndex)
    });
  }
  
  // If no matches found, return the whole status as text
  if (segments.length === 0) {
    segments.push({
      type: 'text',
      content: status
    });
  }
  
  return segments;
}

/**
 * Check if a status message contains file references.
 */
export function hasFileReferences(status: string): boolean {
  if (!status) return false;
  FILE_REFERENCE_PATTERN.lastIndex = 0;
  return FILE_REFERENCE_PATTERN.test(status);
}

export function resolveWorkspaceLinkTarget(path: string, archiveId?: string | null): WorkspaceLinkTarget {
  const normalizedPath = normalizeWorkspacePath(path);
  const archiveMatch = normalizedPath.match(/^quasar_archive\/([^/]+)(?:\/(.*))?$/);

  if (archiveMatch) {
    const nestedPath = archiveMatch[2] ? normalizeWorkspacePath(archiveMatch[2]) : '.';
    return {
      archiveId: archiveMatch[1],
      filePath: nestedPath,
    };
  }

  return {
    archiveId: archiveId ?? null,
    filePath: normalizedPath,
  };
}

function normalizeWorkspacePath(path: string): string {
  const trimmedPath = path.trim();

  if (!trimmedPath || trimmedPath === '.' || trimmedPath === 'workspace') {
    return '.';
  }

  return trimmedPath.replace(/^\.?\/+/, '').replace(/\/+$/, '');
}

function getPathDisplayName(path: string): string {
  const normalizedPath = normalizeWorkspacePath(path);

  if (normalizedPath === '.') {
    return 'workspace';
  }

  const segments = normalizedPath.split('/');
  return segments[segments.length - 1] || normalizedPath;
}

function isNavigablePath(path: string): boolean {
  return normalizeWorkspacePath(path) !== ARCHIVE_ROOT_NAME;
}
