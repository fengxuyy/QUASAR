import React, { useState, useEffect } from 'react';
import Papa from 'papaparse';
import * as XLSX from 'xlsx';
import { Loader2, Table as TableIcon, FileSpreadsheet } from 'lucide-react';

interface SpreadsheetViewerProps {
  filePath: string;
  fileUrl: string;
  fileSize?: number;
  loadTextPreview?: () => Promise<{ content: string; totalSize: number; truncated: boolean }>;
}

const MAX_CSV_PREVIEW_BYTES = 500000;
const MAX_RENDER_ROWS = 500;
const MAX_RENDER_COLUMNS = 80;
const MAX_XLSX_PARSE_BYTES = 12 * 1024 * 1024;

export const SpreadsheetViewer: React.FC<SpreadsheetViewerProps> = ({ filePath, fileUrl, fileSize, loadTextPreview }) => {
  const [data, setData] = useState<any[][]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sheets, setSheets] = useState<string[]>([]);
  const [activeSheet, setActiveSheet] = useState<string>('');
  const [isPreview, setIsPreview] = useState(false);
  const [sourceColumns, setSourceColumns] = useState(0);

  useEffect(() => {
    const loadFile = async () => {
      setLoading(true);
      setError(null);
      setData([]);
      setHeaders([]);
      setSheets([]);
      setActiveSheet('');
      setIsPreview(false);
      setSourceColumns(0);
      try {
        const ext = filePath.split('.').pop()?.toLowerCase();

        if (ext === 'csv') {
          const preview = loadTextPreview
            ? await loadTextPreview()
            : await fetch(fileUrl).then(async response => {
                if (!response.ok) throw new Error('Failed to fetch file');
                const text = await response.text();
                return {
                  content: text.slice(0, MAX_CSV_PREVIEW_BYTES),
                  totalSize: text.length,
                  truncated: text.length > MAX_CSV_PREVIEW_BYTES,
                };
              });
          const text = preview.content;
          setIsPreview(preview.truncated);
          Papa.parse(text, {
            preview: MAX_RENDER_ROWS + 1,
            skipEmptyLines: true,
            complete: (results) => {
              const rows = results.data as any[][];
              if (rows.length > 0) {
                const rawHeaders = rows[0].map(h => String(h || ''));
                const bodyRows = rows.slice(1, MAX_RENDER_ROWS + 1);
                setSourceColumns(rawHeaders.length);
                setHeaders(rawHeaders.slice(0, MAX_RENDER_COLUMNS));
                setData(bodyRows.map(row => row.slice(0, MAX_RENDER_COLUMNS)));
              }
              setLoading(false);
            },
            error: (err: Error) => {
              setError(err.message);
              setLoading(false);
            }
          });
        } else if (ext === 'xlsx' || ext === 'xls') {
          if (fileSize && fileSize > MAX_XLSX_PARSE_BYTES) {
            setError(`Spreadsheet is too large to preview safely (${(fileSize / 1024 / 1024).toFixed(1)} MB). Download it to inspect the full workbook.`);
            setLoading(false);
            return;
          }
          const response = await fetch(fileUrl);
          if (!response.ok) throw new Error('Failed to fetch file');
          const arrayBuffer = await response.arrayBuffer();
          const workbook = XLSX.read(arrayBuffer, { sheetRows: MAX_RENDER_ROWS + 1 });
          setSheets(workbook.SheetNames);
          setIsPreview(true);
          
          const sheetName = workbook.SheetNames[0];
          setActiveSheet(sheetName);
          parseSheet(workbook, sheetName);
          setLoading(false);
        }
      } catch (e) {
        setError((e as Error).message);
        setLoading(false);
      }
    };

    loadFile();
  }, [fileUrl, filePath, fileSize, loadTextPreview]);

  const parseSheet = (workbook: XLSX.WorkBook, sheetName: string) => {
    const worksheet = workbook.Sheets[sheetName];
    const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 }) as any[][];
    if (jsonData.length > 0) {
      const rawHeaders = jsonData[0].map(h => String(h || ''));
      const rows = jsonData.slice(1, MAX_RENDER_ROWS + 1);
      setSourceColumns(rawHeaders.length);
      setHeaders(rawHeaders.slice(0, MAX_RENDER_COLUMNS));
      setData(rows.map(row => row.slice(0, MAX_RENDER_COLUMNS)));
    } else {
      setHeaders([]);
      setData([]);
      setSourceColumns(0);
    }
  };

  const handleSheetChange = async (sheetName: string) => {
    setLoading(true);
    setActiveSheet(sheetName);
    try {
      const response = await fetch(fileUrl);
      const arrayBuffer = await response.arrayBuffer();
      const workbook = XLSX.read(arrayBuffer, { sheetRows: MAX_RENDER_ROWS + 1 });
      parseSheet(workbook, sheetName);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (loading && data.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3">
        <Loader2 size={32} className="animate-spin text-blue-500" />
        <span className="text-slate-400">Parsing spreadsheet</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center text-red-500 p-8 text-center font-sans">
        <div>
          <p className="font-semibold mb-2">Error loading spreadsheet</p>
          <p className="text-sm opacity-80">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full font-sans">
      {/* Spreadsheet Header / Tabs */}
      <div className="flex items-center justify-between mb-4 gap-4">
        <div className="flex items-center gap-2">
          {filePath.endsWith('.csv') ? (
            <TableIcon size={20} className="text-emerald-500" />
          ) : (
            <FileSpreadsheet size={20} className="text-emerald-600" />
          )}
          <span className="font-medium text-slate-700">
            {data.length.toLocaleString()} rows shown
            {sourceColumns > headers.length ? `, ${headers.length}/${sourceColumns} columns` : ''}
          </span>
          {isPreview && (
            <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
              Preview limited for responsiveness
            </span>
          )}
        </div>

        {sheets.length > 1 && (
          <div className="flex gap-1 bg-slate-100 p-1 rounded-xl scrollbar-glass overflow-x-auto">
            {sheets.map(sheet => (
              <button
                key={sheet}
                onClick={() => handleSheetChange(sheet)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  activeSheet === sheet 
                    ? 'bg-white text-blue-600 shadow-sm' 
                    : 'text-slate-500 hover:bg-white/50'
                }`}
              >
                {sheet}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Table Container */}
      <div className="flex-1 overflow-auto scrollbar-glass border border-slate-200 rounded-2xl bg-white shadow-inner">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 z-10">
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-3 py-2 text-left font-semibold text-slate-400 border-r border-slate-200 w-10">#</th>
              {headers.map((header, i) => (
                <th key={i} className="px-4 py-2 text-left font-semibold text-slate-600 border-r border-slate-200 last:border-r-0 min-w-[120px]">
                  {header || `Column ${i + 1}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-slate-100 hover:bg-blue-50/30 transition-colors last:border-0">
                <td className="px-3 py-2 text-slate-400 bg-slate-50/50 border-r border-slate-200 font-medium text-center">
                  {rowIndex + 1}
                </td>
                {headers.map((_, colIndex) => (
                  <td key={colIndex} className="px-4 py-2 text-slate-600 border-r border-slate-200 last:border-r-0 whitespace-nowrap">
                    {String(row[colIndex] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
            {isPreview && data.length > 0 && (
              <tr>
                <td colSpan={headers.length + 1} className="p-4 text-center text-amber-600 bg-amber-50/70">
                  Showing a responsive preview of up to {MAX_RENDER_ROWS.toLocaleString()} rows and {MAX_RENDER_COLUMNS.toLocaleString()} columns.
                </td>
              </tr>
            )}
            {data.length === 0 && (
              <tr>
                <td colSpan={headers.length + 1} className="p-8 text-center text-slate-400 italic">
                  Sheet is empty
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
