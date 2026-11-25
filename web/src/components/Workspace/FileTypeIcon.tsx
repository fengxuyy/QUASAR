import React from 'react';
import { 
  File, 
  FileCode, 
  FileJson, 
  FileText, 
  FileImage, 
  FileSpreadsheet,
  FileType,
  Box,
  Code,
  Palette,
  Settings,
  Database
} from 'lucide-react';
import { clsx } from 'clsx';

interface FileTypeIconProps {
  filename: string;
  size?: number;
  className?: string;
  isSelected?: boolean;
}

export const FileTypeIcon: React.FC<FileTypeIconProps> = ({ 
  filename, 
  size = 16, 
  className,
  isSelected = false 
}) => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  
  // Define icon colors by file type
  const getIconConfig = () => {
    switch (ext) {
      // Python
      case 'py':
      case 'pyw':
      case 'pyx':
        return { 
          icon: FileCode, 
          color: isSelected ? 'text-blue-600' : 'text-yellow-500'
        };
      
      // JavaScript/TypeScript
      case 'js':
      case 'jsx':
        return { 
          icon: FileCode, 
          color: isSelected ? 'text-blue-600' : 'text-yellow-400'
        };
      case 'ts':
      case 'tsx':
        return { 
          icon: FileCode, 
          color: isSelected ? 'text-blue-600' : 'text-blue-500'
        };
      
      // JSON
      case 'json':
      case 'jsonl':
        return { 
          icon: FileJson, 
          color: isSelected ? 'text-blue-600' : 'text-amber-500'
        };
      
      // HTML
      case 'html':
      case 'htm':
        return { 
          icon: Code, 
          color: isSelected ? 'text-blue-600' : 'text-orange-500'
        };
      
      // CSS
      case 'css':
      case 'scss':
      case 'sass':
      case 'less':
        return { 
          icon: Palette, 
          color: isSelected ? 'text-blue-600' : 'text-purple-500'
        };
      
      // Markdown
      case 'md':
      case 'mdx':
        return { 
          icon: FileText, 
          color: isSelected ? 'text-blue-600' : 'text-slate-500'
        };
      
      // YAML
      case 'yaml':
      case 'yml':
        return { 
          icon: Settings, 
          color: isSelected ? 'text-blue-600' : 'text-red-400'
        };
      
      // Images
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
      case 'webp':
      case 'svg':
      case 'ico':
      case 'bmp':
        return { 
          icon: FileImage, 
          color: isSelected ? 'text-blue-600' : 'text-pink-500'
        };
      
      // Spreadsheets/CSV
      case 'csv':
      case 'xlsx':
      case 'xls':
        return { 
          icon: FileSpreadsheet, 
          color: isSelected ? 'text-blue-600' : 'text-green-500'
        };
      
      // CIF (Crystal)
      case 'cif':
        return { 
          icon: Box, 
          color: isSelected ? 'text-blue-600' : 'text-cyan-500'
        };
      
      // XML
      case 'xml':
        return { 
          icon: Code, 
          color: isSelected ? 'text-blue-600' : 'text-orange-400'
        };
      
      // SQL/Database
      case 'sql':
      case 'sqlite':
      case 'db':
        return { 
          icon: Database, 
          color: isSelected ? 'text-blue-600' : 'text-blue-400'
        };
      
      // Shell scripts
      case 'sh':
      case 'bash':
      case 'zsh':
        return { 
          icon: FileCode, 
          color: isSelected ? 'text-blue-600' : 'text-green-600'
        };
      
      // Text files
      case 'txt':
      case 'log':
        return { 
          icon: FileText, 
          color: isSelected ? 'text-blue-600' : 'text-slate-400'
        };
      
      // PDF
      case 'pdf':
        return { 
          icon: FileType, 
          color: isSelected ? 'text-blue-600' : 'text-red-500'
        };
      
      // Default
      default:
        return { 
          icon: File, 
          color: isSelected ? 'text-blue-500' : 'text-slate-400'
        };
    }
  };

  const { icon: Icon, color } = getIconConfig();
  
  return <Icon size={size} className={clsx(color, className)} />;
};
