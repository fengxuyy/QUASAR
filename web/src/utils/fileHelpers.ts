export const getLanguageFromFilename = (filename: string): string => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const langMap: Record<string, string> = {
    'py': 'python',
    'js': 'javascript',
    'ts': 'typescript',
    'tsx': 'typescript',
    'jsx': 'javascript',
    'html': 'html',
    'css': 'css',
    'json': 'json',
    'md': 'markdown',
    'sh': 'bash',
    'bash': 'bash',
    'yml': 'yaml',
    'yaml': 'yaml',
    'cif': 'text',
    'txt': 'text',
    'log': 'text',
    'csv': 'text',
    'xml': 'xml',
    'sql': 'sql',
    'dockerfile': 'dockerfile'
  };
  return langMap[ext] || '';
};

export const isImageFile = (filename: string): boolean => {
  return /\.(jpg|jpeg|png|gif|webp|svg)$/i.test(filename);
};

export const isCifFile = (filename: string): boolean => {
  return /\.cif$/i.test(filename);
};

export const isSpreadsheetFile = (filename: string): boolean => {
  return /\.(csv|xlsx|xls)$/i.test(filename);
};

export const isPdfFile = (filename: string): boolean => {
  return /\.pdf$/i.test(filename);
};

export const isMarkdownFile = (filename: string): boolean => {
  return /\.md$/i.test(filename);
};

export const isXmlFile = (filename: string): boolean => {
  return /\.xml$/i.test(filename);
};

export const isHtmlFile = (filename: string): boolean => {
  return /\.(html|htm)$/i.test(filename);
};

export const isBinaryFile = (filename: string): boolean => {
  // Common binary file extensions
  const binaryExtensions = [
    // Images
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'ico', 'bmp', 'tiff', 'tif', 'psd', 'raw', 'heic', 'heif',
    // Videos
    'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v', 'mpeg', 'mpg', '3gp',
    // Audio
    'mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'aiff',
    // Archives
    'zip', 'rar', 'tar', 'gz', '7z', 'bz2', 'xz', 'lz', 'lzma',
    // Documents (binary)
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp',
    // Executables
    'exe', 'dll', 'so', 'dylib', 'bin', 'msi', 'dmg', 'app', 'deb', 'rpm',
    // Fonts
    'ttf', 'otf', 'woff', 'woff2', 'eot',
    // Database
    'db', 'sqlite', 'sqlite3', 'mdb',
    // Scientific/specialized
    'npz', 'npy', 'hdf5', 'h5', 'mat', 'pkl', 'pickle', 'parquet', 'feather',
    'traj', 'trajectory', 'nc', 'netcdf', 'dcd', 'xtc', 'trr', 'gro', 'pdb.gz',
    // Other
    'class', 'jar', 'war', 'pyc', 'pyo', 'o', 'a', 'lib', 'obj', 'wasm'
  ];
  
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return binaryExtensions.includes(ext);
};

