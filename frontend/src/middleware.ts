import { NextResponse, type NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const configured = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  let apiOrigin: string;
  try {
    apiOrigin = new URL(configured).origin;
  } catch {
    apiOrigin = "http://localhost:8000";
  }
  // Next applies this nonce to its own inline flight scripts when the CSP is
  // on the request. A static script-src 'self' blocks those scripts and the
  // page never hydrates.
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    // Fonts are self-hosted by next/font; no third-party style or font hosts.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' https: data:",
    "font-src 'self' data:",
    `connect-src 'self' ${apiOrigin} https:`,
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  // App-wide security headers (#187): defense in depth on every page, not
  // just the reader.
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  return response;
}

// Every document route. Next's own static/image assets and the public files
// (service worker, manifest, icons) are excluded — no CSP needed there and
// applying one would break the service worker's cache behavior.
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|manifest.json|sw.js|icon.svg|robots.txt|sitemap.xml).*)",
  ],
};
