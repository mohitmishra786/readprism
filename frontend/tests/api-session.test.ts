import { afterEach, describe, expect, it, vi } from "vitest";
import { api, hasSession, keepalivePost } from "../src/lib/api";
import { clearSession, getCsrfToken, setCsrfToken } from "../src/lib/auth";

type Call = { url: string; init: RequestInit };

function mockFetch(responses: Array<{ status?: number; body?: unknown }>) {
  const calls: Call[] = [];
  const queue = [...responses];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      const next = queue.shift() ?? { status: 200, body: {} };
      const status = next.status ?? 200;
      return new Response(status === 204 ? null : JSON.stringify(next.body ?? {}), { status });
    }),
  );
  return calls;
}

const header = (call: Call, name: string) =>
  (call.init.headers as Record<string, string> | undefined)?.[name];

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("cookie sessions (#103)", () => {
  it("sends credentials and cookie mode, never an Authorization header", async () => {
    const calls = mockFetch([{ body: { id: "u1" } }]);
    await api.auth.me();
    expect(calls[0].init.credentials).toBe("include");
    expect(header(calls[0], "X-Auth-Mode")).toBe("cookie");
    expect(header(calls[0], "Authorization")).toBeUndefined();
    expect(header(calls[0], "X-CSRF-Token")).toBeUndefined(); // GET
  });

  it("adds the CSRF token to mutating requests", async () => {
    setCsrfToken("csrf-123");
    const calls = mockFetch([{ body: {} }]);
    await api.preferences.update({ digest_max_items: 10 });
    expect(header(calls[0], "X-CSRF-Token")).toBe("csrf-123");
  });

  it("restores the CSRF token from /auth/session before a write after reload", async () => {
    const calls = mockFetch([
      { body: { authenticated: true, refreshable: true, csrf_token: "restored" } },
      { body: {} },
    ]);
    await api.preferences.update({ digest_max_items: 10 });
    expect(calls[0].url).toMatch(/\/auth\/session$/);
    expect(header(calls[1], "X-CSRF-Token")).toBe("restored");
  });

  it("remembers the CSRF token returned by login", async () => {
    mockFetch([{ body: { access_token: "", token_type: "bearer", expires_in: 1800, csrf_token: "from-login" } }]);
    await api.auth.login("a@example.com", "pw");
    expect(getCsrfToken()).toBe("from-login");
  });

  it("hasSession refreshes an expired access cookie once", async () => {
    const calls = mockFetch([
      { body: { authenticated: false, refreshable: true, csrf_token: null } },
      { body: { access_token: "", csrf_token: "after-refresh" } },
      { body: { authenticated: true, refreshable: true, csrf_token: "after-refresh" } },
    ]);
    expect(await hasSession()).toBe(true);
    expect(calls[1].url).toMatch(/\/auth\/refresh$/);
    expect(getCsrfToken()).toBe("after-refresh");
  });

  it("keepalive telemetry carries credentials and CSRF", () => {
    setCsrfToken("csrf-k");
    const calls = mockFetch([{ body: {} }]);
    keepalivePost("/feedback/interaction", { content_item_id: "x" });
    expect(calls[0].init.credentials).toBe("include");
    expect(calls[0].init.keepalive).toBe(true);
    expect(header(calls[0], "X-CSRF-Token")).toBe("csrf-k");
  });
});
