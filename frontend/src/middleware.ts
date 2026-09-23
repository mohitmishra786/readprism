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
  // reader never hydrates.
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
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
  return response;
}

export const config = {
  matcher: ["/read/:path*"],
};
