// Everything ReadPrism stores in your browser (#211). All of it is essential
// or a remembered setting: no analytics, advertising or tracking, so there is
// no consent banner. backend/tests/test_utils/test_privacy_page.py checks
// that every cookie the API sets and every localStorage key the app writes
// is listed here.

export interface StoredItem {
  name: string;
  kind: "Cookie" | "Local storage" | "Offline cache";
  purpose: string;
  lifetime: string;
}

export const BROWSER_STORAGE: StoredItem[] = [
  { name: "rp_access", kind: "Cookie", purpose: "Keeps you signed in. httpOnly, so page scripts cannot read it.", lifetime: "Minutes; renewed while you use the app." },
  { name: "rp_refresh", kind: "Cookie", purpose: "Renews your session without a new sign-in. httpOnly, sent only to the sign-in endpoints.", lifetime: "Until it expires (days) or you sign out." },
  { name: "rp_csrf", kind: "Cookie", purpose: "Protects your account against forged requests from other sites. httpOnly.", lifetime: "Same as the session." },
  { name: "rp-session-seen", kind: "Local storage", purpose: "Remembers that this device was signed in, so the app opens offline.", lifetime: "Removed when you sign out." },
  { name: "reader-font-step", kind: "Local storage", purpose: "Your reader text size.", lifetime: "Until you clear site data." },
  { name: "reader-theme", kind: "Local storage", purpose: "Your reader colour theme.", lifetime: "Until you clear site data." },
  { name: "install-prompt-dismissed", kind: "Local storage", purpose: "Stops the 'install the app' hint coming back.", lifetime: "Until you clear site data." },
  { name: "readprism-v2", kind: "Offline cache", purpose: "App pages and articles you opened, so they work offline.", lifetime: "Replaced on each app update." },
];
