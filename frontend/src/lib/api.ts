import { getToken, removeToken } from './auth';
import type {
  ContentItem,
  Creator,
  Digest,
  FeedItem,
  InterestGraph,
  Source,
  Token,
  User,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const V1 = `${API_BASE}/api/v1`;

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${V1}${path}`, { ...options, headers });

  if (res.status === 401) {
    removeToken();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// Auth
export const api = {
  auth: {
    register: (email: string, password: string, display_name?: string) =>
      request<Token>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, display_name }),
      }),
    login: (email: string, password: string) =>
      request<Token>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),
    me: () => request<User>('/auth/me'),
    refresh: (refresh_token: string) =>
      request<Token>('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token }),
      }),
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
    delete: (id: string) =>
      request<void>(`/sources/${id}`, { method: 'DELETE' }),
    importOpml: (file: File) => {
      const form = new FormData();
      form.append('file', file);
      const token = getToken();
      return fetch(`${V1}/sources/import-opml`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      }).then((r) => r.json());
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
      request<Array<{ id: string; prompt_text: string; prompt_type: string; answered: boolean; answer: string | null }>>(
        `/digest/${digestId}/prompts`
      ),
    answerPrompt: (digestId: string, promptId: string, answer: string) =>
      request<{ id: string; answered: boolean }>(`/digest/${digestId}/prompts/${promptId}/answer`, {
        method: 'POST',
        body: JSON.stringify({ answer }),
      }),
  },

  content: {
    feed: (page?: number, limit?: number) =>
      request<FeedItem[]>(`/content/feed?page=${page || 1}&limit=${limit || 20}`),
    get: (id: string) => request<ContentItem>(`/content/${id}`),
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
      explicit_rating?: number;
      explicit_rating_reason?: string;
      saved?: boolean;
      skipped?: boolean;
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

  search: {
    query: (q: string, limit?: number, offset?: number) =>
      request<{ query: string; hits: ContentItem[]; limit: number; offset: number }>(
        `/search?q=${encodeURIComponent(q)}&limit=${limit || 20}&offset=${offset || 0}`
      ),
  },

  onboarding: {
    complete: (data: {
      interest_text: string;
      sample_ratings: Array<{ article_url: string; title: string; rating: number }>;
      source_opml: string | null;
    }) =>
      request<{ status: string; message: string }>('/onboarding', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },
};
