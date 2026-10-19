import {
  clearSession,
  getCsrfToken,
  rememberSessionSeen,
  sessionSeenOffline,
  setCsrfToken,
} from './auth';
import type {
  BillingState,
  WhyNotSeen,
  ImportResult,
  StarterPack,
  ContentItem,
  ContentItemFull,
  Creator,
  Digest,
  FeedItem,
  InterestGraph,
  PlatformCapabilities,
  Source,
  Token,
  User,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const V1 = `${API_BASE}/api/v1`;

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Browser session state as reported by the API (#103). */
export interface SessionState {
  authenticated: boolean;
  refreshable: boolean;
  csrf_token: string | null;
  /** True when the server was unreachable and the cached app is shown (#216). */
  offline?: boolean;
}

/**
 * Credentials are httpOnly cookies (#103): every call sends them with
 * `credentials: 'include'`, asks for cookie mode, and adds the in-memory CSRF
 * token on mutating requests.
 */
function buildHeaders(options: RequestInit, json = true): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Auth-Mode': 'cookie',
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers as Record<string, string>),
  };
  const method = (options.method || 'GET').toUpperCase();
  const csrf = getCsrfToken();
  if (MUTATING.has(method) && csrf) headers['X-CSRF-Token'] = csrf;
  return headers;
}

/** Ask the API whether a session exists, restoring the CSRF token if so. */
export async function loadSession(): Promise<SessionState> {
  try {
    const res = await fetch(`${V1}/auth/session`, { credentials: 'include' });
    const state = (await res.json()) as SessionState;
    setCsrfToken(state.csrf_token);
    rememberSessionSeen(state.authenticated);
    return state;
  } catch {
    // Offline on a device that was signed in: show the cached app (#216).
    if (sessionSeenOffline()) {
      return { authenticated: true, refreshable: false, csrf_token: null, offline: true };
    }
    return { authenticated: false, refreshable: false, csrf_token: null };
  }
}

/** True when signed in (refreshing an expired access cookie if possible). */
export async function hasSession(): Promise<boolean> {
  const state = await loadSession();
  if (state.authenticated) return true;
  if (state.refreshable && (await tryRefresh())) return (await loadSession()).authenticated;
  return false;
}

// Single-flight refresh: concurrent 401s share one refresh request so we don't
// stampede /auth/refresh (which is single-use and would revoke each other).
let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${V1}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'X-Auth-Mode': 'cookie' },
        });
        if (!res.ok) return false;
        const data = (await res.json()) as Token;
        setCsrfToken(data.csrf_token);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

async function ensureCsrf(method: string | undefined): Promise<void> {
  if (MUTATING.has((method || 'GET').toUpperCase()) && !getCsrfToken()) {
    await loadSession();
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  _retried = false,
): Promise<T> {
  const isAuthPath = path.startsWith('/auth/');
  if (!isAuthPath) await ensureCsrf(options.method);
  const json = !(options.body instanceof FormData);
  const res = await fetch(`${V1}${path}`, {
    ...options,
    credentials: 'include',
    headers: buildHeaders(options, json),
  });

  if (res.status === 401) {
    // Access cookie likely expired — attempt one silent refresh + retry before
    // bouncing to /login. Don't attempt to refresh the auth endpoints themselves.
    if (!_retried && !isAuthPath && (await tryRefresh())) {
      return request<T>(path, options, true);
    }
    clearSession();
    if (typeof window !== 'undefined' && !isAuthPath) {
      window.location.href = '/login';
    }
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || 'Unauthorized');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/**
 * Fire-and-forget POST that survives page unload (`keepalive`).
 *
 * `navigator.sendBeacon` cannot carry the CSRF header, so unload-time
 * telemetry uses a keepalive fetch instead: the browser finishes the request
 * even after the page goes away (UX-05).
 */
export function keepalivePost(path: string, payload: Record<string, unknown>): void {
  try {
    void fetch(`${V1}${path}`, {
      method: 'POST',
      credentials: 'include',
      headers: buildHeaders({ method: 'POST' }),
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {
      // Telemetry must never break navigation.
    });
  } catch {
    // Ignore — e.g. payload larger than the keepalive budget.
  }
}

function rememberCsrf(t: Token): Token {
  setCsrfToken(t.csrf_token);
  return t;
}

// Auth
export const api = {
  auth: {
    register: (email: string, password: string, display_name?: string, invite_code?: string) =>
      request<Token>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, display_name, invite_code }),
      }).then(rememberCsrf),
    /** Whether this instance accepts new accounts (#153). */
    registration: () =>
      request<{ mode: string; open: boolean; invite_required: boolean }>('/auth/registration'),
    login: (email: string, password: string) =>
      request<Token>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }).then(rememberCsrf),
    me: () => request<User>('/auth/me'),
    /** Revokes the refresh cookie server-side and clears all session cookies. */
    logout: () =>
      request<void>('/auth/logout', { method: 'POST' }).finally(() => clearSession()),
    // Passwordless sign-in (audit 10-8).
    magicLinkRequest: (email: string) =>
      request<{ status: string }>('/auth/magic-link/request', {
        method: 'POST',
        body: JSON.stringify({ email }),
      }),
    magicLinkVerify: (token: string) =>
      request<Token>('/auth/magic-link/verify', {
        method: 'POST',
        body: JSON.stringify({ token }),
      }).then(rememberCsrf),
    // Email confirmation (#175).
    verifyEmail: (token: string) =>
      request<{ verified: boolean }>('/auth/verify-email', {
        method: 'POST',
        body: JSON.stringify({ token }),
      }),
    resendVerification: () =>
      request<{ status: string }>('/auth/verify-email/resend', { method: 'POST' }),
  },

  // Personal newsletter address and its live test (#151).
  newsletter: {
    address: () =>
      request<{ address: string; inbound_configured: boolean; email_verified: boolean }>(
        '/newsletter/address',
      ),
    sendTest: () => request<{ status: string }>('/newsletter/address/test', { method: 'POST' }),
    testStatus: () =>
      request<{ status: 'none' | 'waiting' | 'received'; sent_at?: string; received_at?: string }>(
        '/newsletter/address/test',
      ),
  },

  // Hosted billing (#173). Self-hosted instances report plan "selfhost".
  billing: {
    state: () => request<BillingState>('/billing'),
    checkout: (interval: 'month' | 'year') =>
      request<{ url: string }>('/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({ interval }),
      }),
    portal: () => request<{ url: string }>('/billing/portal'),
  },

  account: {
    // Portable JSON copy of all personal data (GDPR export, 06-3).
    export: () => request<Record<string, unknown>>('/account/export'),
    delete: () => request<void>('/account', { method: 'DELETE' }),
  },

  sources: {
    list: () => request<Source[]>('/sources'),
    add: (url: string, priority?: string) =>
      request<Source>('/sources', {
        method: 'POST',
        body: JSON.stringify({ url, priority }),
      }),
    update: (id: string, data: Partial<Source>) =>
      request<Source>(`/sources/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    /** Feed subscriptions from OPML (Feedly/Inoreader); folders become tags (#150). */
    importFeeds: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return request<ImportResult>('/sources/import-opml-v2', { method: 'POST', body: form });
    },
    /** Progress of a background OPML import (#202). */
    importJob: (id: string) =>
      request<{ status: string; total: number; done: number; created: number; progress: number; error?: string | null }>(
        `/sources/import-jobs/${id}`,
      ),
    /** Saved articles: Pocket HTML, CSV, or starred OPML; format auto-detected (#150). */
    importSaved: (file: File, kind = 'auto') => {
      const form = new FormData();
      form.append('file', file);
      return request<ImportResult>(`/sources/import-saved?kind=${encodeURIComponent(kind)}`, {
        method: 'POST',
        body: form,
      });
    },
    starterPacks: (topics: string[] = []) =>
      request<StarterPack[]>(
        `/sources/starter-packs${topics.length ? `?topics=${encodeURIComponent(topics.join(","))}` : ""}`,
      ),
    subscribePack: (id: string) =>
      request<{ status: string; subscribed: number; already_had: number }>(
        `/sources/starter-packs/${id}/subscribe`,
        { method: 'POST' },
      ),
    /** One-click repair of a dead/failing feed (#212). */
    fix: (id: string) =>
      request<{ status: 'fixed' | 'no_new_feed'; feed_url: string | null; suggestion?: string }>(
        `/sources/${id}/fix`,
        { method: 'POST' },
      ),
    delete: (id: string) =>
      request<void>(`/sources/${id}`, { method: 'DELETE' }),
    importOpml: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return request<{ created: number }>('/sources/import-opml', { method: 'POST', body: form });
    },
  },

  creators: {
    list: () => request<Creator[]>('/creators'),
    add: (name_or_url: string, priority?: string) =>
      request<{ creator: Creator; platforms_discovered: number; warning: string | null }>(
        '/creators',
        { method: 'POST', body: JSON.stringify({ name_or_url, priority }) },
      ),
    get: (id: string) => request<Creator>(`/creators/${id}`),
    capabilities: () => request<PlatformCapabilities>('/creators/platform-capabilities'),
    summary: (id: string) =>
      request<{ summary: string; item_count?: number }>(`/creators/${id}/summary`),
    update: (id: string, data: Partial<Creator>) =>
      request<Creator>(`/creators/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    delete: (id: string) =>
      request<void>(`/creators/${id}`, { method: 'DELETE' }),
  },

  digest: {
    latest: () => request<Digest>('/digest/latest'),
    history: (page?: number) => request<Digest[]>(`/digest/history?page=${page || 1}`),
    generate: () =>
      request<{ status: string; message: string }>('/digest/generate', { method: 'POST' }),
    get: (id: string) => request<Digest>(`/digest/${id}`),
    prompts: (digestId: string) =>
      request<Array<{ id: string; prompt_text: string; prompt_type: string; answered: boolean; dismissed: boolean; answer: string | null }>>(
        `/digest/${digestId}/prompts`
      ),
    answerPrompt: (digestId: string, promptId: string, answer: string) =>
      request<{ id: string; answered: boolean }>(`/digest/${digestId}/prompts/${promptId}/answer`, {
        method: 'POST',
        body: JSON.stringify({ answer }),
      }),
    dismissPrompt: (digestId: string, promptId: string) =>
      request<{ id: string; dismissed: boolean }>(
        `/digest/${digestId}/prompts/${promptId}/dismiss`,
        { method: 'POST' },
      ),
  },

  content: {
    feed: (page?: number, limit?: number) =>
      request<FeedItem[]>(`/content/feed?page=${page || 1}&limit=${limit || 20}`),
    history: (page?: number, limit?: number) =>
      request<FeedItem[]>(`/content/history?page=${page || 1}&limit=${limit || 20}`),
    get: (id: string) => request<ContentItemFull>(`/content/${id}`),
  },

  feedback: {
    getInteraction: (contentItemId: string) =>
      request<{ saved: boolean; explicit_rating: number | null } | null>(
        `/feedback/interaction/${contentItemId}`
      ),
    interaction: (data: {
      content_item_id: string;
      read_completion_pct?: number;
      time_on_page_seconds?: number;
      scroll_depth_pct?: number;
      active_time_seconds?: number;
      reached_end?: boolean;
      explicit_rating?: number;
      explicit_rating_reason?: string;
      saved?: boolean;
      skipped?: boolean;
      opened_externally?: boolean;
    }) =>
      request<unknown>('/feedback/interaction', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    adjustInterests: (topic: string, action: string, duration_days?: number) =>
      request<unknown>('/feedback/adjust-interests', {
        method: 'POST',
        body: JSON.stringify({ topic, action, duration_days }),
      }),
    renameInterest: (from_label: string, to_label: string) =>
      request<{ status: string }>('/feedback/rename-interest', {
        method: 'POST',
        body: JSON.stringify({ from_label, to_label }),
      }),
    mergeInterests: (from_label: string, into_label: string) =>
      request<{ status: string }>('/feedback/merge-interests', {
        method: 'POST',
        body: JSON.stringify({ from_label, into_label }),
      }),
  },

  preferences: {
    get: () => request<User>('/preferences'),
    update: (data: Partial<User>) =>
      request<User>('/preferences', {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    interestGraph: () => request<InterestGraph>('/preferences/interest-graph'),
  },

  metrics: {
    llmStatus: () =>
      request<{
        llm_configured: boolean;
        model_primary: string;
        model_fast: string;
        openai_fallback_enabled: boolean;
        embedding_model?: string;
        embedding_is_hash?: boolean;
        embedding_quality_note?: string;
        embedding_upgrade_hint?: string | null;
      }>('/metrics/llm-status'),
  },

  search: {
    query: (q: string, limit?: number, offset?: number) =>
      request<{ query: string; hits: ContentItem[]; limit: number; offset: number }>(
        `/search?q=${encodeURIComponent(q)}&limit=${limit || 20}&offset=${offset || 0}`
      ),
    /** "Why didn't I see this?" for any item (#267). */
    why: (contentId: string) => request<WhyNotSeen>(`/search/why/${contentId}`),
  },

  onboarding: {
    expandInterests: (interest_text: string) =>
      request<{ topics: string[] }>('/onboarding/expand-interests', {
        method: 'POST',
        body: JSON.stringify({ interest_text }),
      }),
    complete: (data: {
      interest_text: string;
      sample_ratings: Array<{ article_url: string; title: string; rating: number }>;
      source_opml: string | null;
      confirmed_topics?: string[];
    }) =>
      request<{ status: string; message: string }>('/onboarding', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    /** Up to 8–12 diverse headlines from the user's new sources (#149). */
    calibration: (limit = 8) =>
      request<CalibrationItem[]>(`/onboarding/calibration?limit=${limit}`),
    rateCalibration: (id: string, rating: 1 | -1) =>
      request<{ status: string; clusters_updated: number; clusters_created: number }>(
        `/onboarding/calibration/${id}`,
        { method: 'POST', body: JSON.stringify({ rating }) },
      ),
    /** Start the first-digest flow (idempotent) and return its status (#102). */
    startFirstDigest: () =>
      request<FirstDigestStatus & { started: boolean }>('/onboarding/first-digest', {
        method: 'POST',
      }),
    firstDigestStatus: () => request<FirstDigestStatus>('/onboarding/first-digest/status'),
  },
};

export interface CalibrationItem {
  id: string;
  title: string;
  url: string;
  topic_clusters: string[];
  reading_time_minutes: number | null;
}

export interface FirstDigestStatus {
  sources_total: number;
  sources_fetched: number;
  items: number;
  items_embedded: number;
  items_summarized: number;
  ready: boolean;
  digest_id: string | null;
}
