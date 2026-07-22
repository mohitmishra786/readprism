import Cookies from 'js-cookie';

const TOKEN_KEY = 'readprism_token';
const REFRESH_KEY = 'readprism_refresh';

export function getToken(): string | null {
  return Cookies.get(TOKEN_KEY) || null;
}

export function getRefreshToken(): string | null {
  return Cookies.get(REFRESH_KEY) || null;
}

// Access tokens are short-lived (30m); the refresh token (30d, revocable
// server-side) is used to mint new access tokens without re-login.
export function setToken(token: string, refreshToken?: string): void {
  Cookies.set(TOKEN_KEY, token, { expires: 1, sameSite: 'strict' });
  if (refreshToken) {
    Cookies.set(REFRESH_KEY, refreshToken, { expires: 30, sameSite: 'strict' });
  }
}

export function removeToken(): void {
  Cookies.remove(TOKEN_KEY);
  Cookies.remove(REFRESH_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
