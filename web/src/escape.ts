/**
 * Escape text before it is placed into HTML: element text or a quoted attribute.
 * Use it for any value that came from a user, from the server, or from the offline cache,
 * whenever the value is written as HTML (for example into document.write).
 * React escapes text in JSX on its own; this helper is for hand-built HTML only.
 */
export function escapeHtml(value: string | number | null | undefined): string {
  return String(value ?? "").replace(/[&<>"'`]/g, (c) => ESCAPES[c]);
}

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
  "`": "&#96;",
};
