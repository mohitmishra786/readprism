import DOMPurify from 'dompurify';

/**
 * Sanitize untrusted HTML before it is passed to dangerouslySetInnerHTML.
 *
 * Article bodies (RSS `content`), summaries, and Meilisearch highlight markup
 * all originate from third-party sources and can carry `<script>`, `onerror=`,
 * `javascript:` URLs, etc. DOMPurify strips anything that could execute while
 * preserving the formatting we actually render (audit 06-7 / 09).
 *
 * On the server (SSR) DOMPurify has no DOM; there we return an empty string so
 * nothing unsanitized is ever emitted — the reader is a client component and
 * hydrates the real content in the browser.
 */
export function sanitizeHtml(dirty: string): string {
  if (typeof window === 'undefined') return '';
  return DOMPurify.sanitize(dirty, { USE_PROFILES: { html: true } });
}
