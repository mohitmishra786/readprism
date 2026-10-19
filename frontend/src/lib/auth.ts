/**
 * Browser session state (#103).
 *
 * Credentials live only in httpOnly cookies set by the API; JavaScript never
 * sees an access or refresh token. The only client-side state is the CSRF
 * token, kept in memory and restored from `GET /auth/session` after a reload.
 */

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null | undefined): void {
  csrfToken = token || null;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

// Set while this browser has a confirmed session, so an offline reload can
// still show the cached app (#216). It grants nothing: offline, everything
// shown comes from this browser's own cache, and any change needs the server.
const SEEN_KEY = "rp-session-seen";

export function rememberSessionSeen(authenticated: boolean): void {
  try {
    if (authenticated) window.localStorage.setItem(SEEN_KEY, "1");
    else window.localStorage.removeItem(SEEN_KEY);
  } catch {
    // storage unavailable (private mode): offline reload just signs out
  }
}

export function sessionSeenOffline(): boolean {
  try {
    return navigator.onLine === false && window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

export function clearSession(): void {
  csrfToken = null;
  rememberSessionSeen(false);
  // Signing out also drops the offline copies of digests and articles, so
  // the next person on a shared device can't read them (#216).
  if (typeof caches !== "undefined") {
    void caches
      .keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .catch(() => {});
  }
}
