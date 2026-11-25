import React, { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, FileCode2, AlertCircle, Folder, FileText } from 'lucide-react';

interface XmlViewerProps {
  content: string;
  fileName?: string;
}

interface XmlNode {
  type: 'element' | 'text' | 'comment' | 'cdata';
  name?: string;
  attributes?: Record<string, string>;
  children?: XmlNode[];
  value?: string;
}

// Parse XML string into tree structure
const parseXml = (xmlString: string): XmlNode | null => {
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlString, 'application/xml');
    
    // Check for parsing errors
    const parserError = doc.querySelector('parsererror');
    if (parserError) {
      throw new Error(parserError.textContent || 'XML parsing error');
    }
    
    const convertNode = (node: Node): XmlNode | null => {
      if (node.nodeType === Node.ELEMENT_NODE) {
        const element = node as Element;
        const attributes: Record<string, string> = {};
        
        for (const attr of element.attributes) {
          attributes[attr.name] = attr.value;
        }
        
        const children: XmlNode[] = [];
        for (const child of node.childNodes) {
          const converted = convertNode(child);
          if (converted) {
            children.push(converted);
          }
        }
        
        return {
          type: 'element',
          name: element.tagName,
          attributes: Object.keys(attributes).length > 0 ? attributes : undefined,
          children: children.length > 0 ? children : undefined,
        };
      } else if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent?.trim();
        if (text) {
          return { type: 'text', value: text };
        }
      } else if (node.nodeType === Node.COMMENT_NODE) {
        return { type: 'comment', value: node.textContent || '' };
      } else if (node.nodeType === Node.CDATA_SECTION_NODE) {
        return { type: 'cdata', value: node.textContent || '' };
      }
      return null;
    };
    
    return convertNode(doc.documentElement);
  } catch (e) {
    console.error('XML parsing error:', e);
    return null;
  }
};

interface XmlElementProps {
  node: XmlNode;
  depth: number;
  defaultExpanded?: boolean;
}

const XmlElement: React.FC<XmlElementProps> = ({ node, depth, defaultExpanded = true }) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded && depth < 3);
  
  const hasChildren = node.children && node.children.length > 0;
  const hasOnlyTextChild = node.children?.length === 1 && node.children[0].type === 'text';
  const textValue = hasOnlyTextChild ? node.children![0].value : null;
  const indent = depth * 20;

  // Skip rendering text nodes directly - they'll be shown inline with their parent
  if (node.type === 'text') {
    return null;
  }
  
  // Skip comments in the clean view
  if (node.type === 'comment') {
    return null;
  }
  
  // Skip CDATA in the clean view (or show as text)
  if (node.type === 'cdata') {
    return null;
  }

  const hasExpandableChildren = hasChildren && !hasOnlyTextChild;

  return (
    <div className="select-text">
      <div 
        style={{ paddingLeft: indent }}
        className={`flex items-center py-1.5 hover:bg-blue-50/50 rounded-lg transition-colors group ${hasExpandableChildren ? 'cursor-pointer' : ''}`}
        onClick={() => hasExpandableChildren && setIsExpanded(!isExpanded)}
      >
        {/* Icon */}
        <div className="w-5 h-5 flex-shrink-0 flex items-center justify-center mr-2">
          {hasExpandableChildren ? (
            <span className="text-slate-400 group-hover:text-blue-500 transition-colors">
              {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </span>
          ) : hasOnlyTextChild ? (
            <FileText size={14} className="text-emerald-500" />
          ) : (
            <Folder size={14} className="text-amber-500" />
          )}
        </div>
        
        {/* Node name */}
        <span className={`font-medium ${hasExpandableChildren ? 'text-blue-600' : 'text-slate-700'}`}>
          {node.name}
        </span>
        
        {/* Attributes as badges */}
        {node.attributes && Object.entries(node.attributes).map(([key, value]) => (
          <span key={key} className="ml-2 px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full text-xs">
            {key}="{value}"
          </span>
        ))}
        
        {/* Inline text value */}
        {textValue && (
          <span className="ml-3 text-slate-600 font-mono text-sm bg-slate-100 px-2 py-0.5 rounded">
            {textValue}
          </span>
        )}
        
        {/* Child count indicator when collapsed */}
        {hasExpandableChildren && !isExpanded && (
          <span className="ml-2 text-xs text-slate-400">
            ({node.children!.filter(c => c.type === 'element').length} items)
          </span>
        )}
      </div>
      
      {/* Children */}
      {hasExpandableChildren && isExpanded && (
        <div className="border-l-2 border-slate-200 ml-2.5">
          {node.children!.map((child, idx) => (
            <XmlElement 
              key={idx} 
              node={child} 
              depth={depth + 1} 
              defaultExpanded={depth < 2}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const XmlViewer: React.FC<XmlViewerProps> = ({ content, fileName }) => {
  const { tree, error } = useMemo(() => {
    if (!content) {
      return { tree: null, error: 'No content to display' };
    }
    
    const parsed = parseXml(content);
    if (!parsed) {
      return { tree: null, error: 'Failed to parse XML. The file may be malformed.' };
    }
    
    return { tree: parsed, error: null };
  }, [content]);

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-red-500 p-8 text-center">
        <AlertCircle size={32} />
        <div>
          <p className="font-semibold mb-2">Error parsing XML</p>
          <p className="text-sm opacity-80">{error}</p>
        </div>
      </div>
    );
  }
  
  if (!tree) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400">
        No XML content
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full font-sans">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <FileCode2 size={20} className="text-orange-500" />
        <span className="font-medium text-slate-700">
          {fileName || 'XML Document'}
        </span>
      </div>
      
      {/* XML Tree */}
      <div className="flex-1 overflow-auto scrollbar-glass border border-slate-200 rounded-2xl bg-white shadow-inner p-4">
        <XmlElement node={tree} depth={0} defaultExpanded={true} />
      </div>
    </div>
  );
};
