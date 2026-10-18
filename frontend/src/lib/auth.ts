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

export function clearSession(): void {
  csrfToken = null;
}
