/**
 * Detect user-facing tool / Pydantic validation messages so they are not shown as normal "Analysed Task" text.
 * Kept aligned with bridge_history._detect_error_in_content and format_validation_error prefixes.
 */
export function looksLikeToolValidationMessage(text: string): boolean {
  const t = (text || '').trim().toLowerCase();
  if (!t) return false;
  if (t.includes('validation error')) return true;
  if (
    t.includes('field required') &&
    (t.includes("field '") || t.includes('field "') || t.includes('issues):'))
  ) {
    return true;
  }
  return false;
}
