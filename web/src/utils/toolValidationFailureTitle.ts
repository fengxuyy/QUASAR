/**
 * User-visible titles for tool validation failures (aligned with bridge_history._format_error_content).
 */
const TOOL_VALIDATION_FAILURE_TITLES: Record<string, string> = {
  query_rag: 'Query RAG Failed',
  read_file: 'Read File Failed',
  edit_file: 'Edit File Failed',
  list_directory: 'List Directory Failed',
  execute_python: 'Execute Python Failed',
  execute_code: 'Execute Code Failed',
  execute_temporary_python: 'Temporary Python Parse Failed',
  analyze_image: 'Analyze Image Failed',
  search_web: 'Search Web Failed',
  fetch_web_page: 'Fetch Web Page Failed',
  grep_search: 'Grep Files Failed',
};

/**
 * Title for the log header when a tool call fails validation (missing args, etc.).
 */
export function getToolValidationFailureTitle(toolName: string | null | undefined): string {
  const key = (toolName || '').trim();
  if (key && TOOL_VALIDATION_FAILURE_TITLES[key]) {
    return TOOL_VALIDATION_FAILURE_TITLES[key];
  }
  if (key) {
    const words = key.replace(/_/g, ' ');
    const titled = words.replace(/\b\w/g, (c) => c.toUpperCase());
    return `${titled} Failed`;
  }
  return 'Tool validation failed';
}
