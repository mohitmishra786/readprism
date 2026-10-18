"""Browser sessions in httpOnly cookies (#103).

The web app sends `X-Auth-Mode: cookie` on auth calls. The server then sets:

- `rp_access`: access JWT, httpOnly, path `/`;
- `rp_refresh`: refresh JWT, httpOnly, path `/api/v1/auth` only;
- `rp_csrf`: random double-submit token. The value is also returned in the
  response body (`csrf_token`) and from `GET /auth/session`, so the frontend
  never needs to read cookies, even when the API is on another subdomain.

…and leaves the tokens out of the JSON body, so JavaScript never holds a
credential. Cookie-authenticated mutating requests must echo the CSRF token
in `X-CSRF-Token`. Bearer tokens (extension, API tokens, MCP) are unchanged.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import HTTPException, Request, Response, status

from app.config import get_settings

ACCESS_COOKIE = "rp_access"
REFRESH_COOKIE = "rp_refresh"
CSRF_COOKIE = "rp_csrf"
AUTH_MODE_HEADER = "x-auth-mode"
CSRF_HEADER = "x-csrf-token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def wants_cookies(request: Request) -> bool:
    return request.headers.get(AUTH_MODE_HEADER, "").lower() == "cookie"


def is_secure_request(request: Request) -> bool:
    """Whether the browser reached us over HTTPS (directly or via a TLS proxy)."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return (forwarded or request.url.scheme) == "https"


def _secure(request: Request) -> bool:
    """`Secure` cookie flag. COOKIE_SECURE=auto (default) follows the request
    scheme: a self-hosted instance on plain http://192.168.x.x must still be
    able to sign in, since browsers drop Secure cookies on non-HTTPS origins
    other than localhost."""
    mode = get_settings().cookie_secure.strip().lower()
    if mode in ("true", "1", "yes"):
        return True
    if mode in ("false", "0", "no"):
        return False
    return is_secure_request(request)


def _common(request: Request) -> dict:
    return {
        "secure": _secure(request),
        "samesite": "strict",
        "domain": get_settings().cookie_domain or None,
    }


def set_session_cookies(
    response: Response, request: Request, *, access: str, refresh: str | None
) -> str:
    """Set the session cookies and return the CSRF token."""
    s = get_settings()
    common = _common(request)
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=s.access_token_expire_minutes * 60,
        httponly=True,
        path="/",
        **common,
    )
    if refresh:
        response.set_cookie(
            REFRESH_COOKIE,
            refresh,
            max_age=s.refresh_token_expire_days * 86400,
            httponly=True,
            path=REFRESH_COOKIE_PATH,
            **common,
        )
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=s.refresh_token_expire_days * 86400,
        httponly=True,  # the frontend gets it from the body / GET /auth/session
        path="/",
        **common,
    )
    return csrf


def clear_session_cookies(response: Response) -> None:
    common = {"domain": get_settings().cookie_domain or None}
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, **common)
    response.delete_cookie(CSRF_COOKIE, path="/", **common)


def enforce_csrf(request: Request) -> None:
    """Reject a cookie-authenticated mutating request without a matching token."""
    if request.method not in MUTATING_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid"
        )
