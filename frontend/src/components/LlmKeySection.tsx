"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { LLMKeyState } from "../lib/types";

const BUTTON = {
  padding: "8px 16px",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  background: "var(--bg-elevated)",
  cursor: "pointer",
} as const;

const INPUT = {
  padding: "8px 10px",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  background: "var(--bg-elevated)",
  width: "100%",
  maxWidth: 420,
} as const;

// Your own LLM key on hosted (#255). Renders nothing on self-hosted instances.
export function LlmKeySection() {
  const [state, setState] = useState<LLMKeyState | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.account
      .llmKey()
      .then((s) => {
        setState(s);
        setBaseUrl(s.base_url ?? s.allowed_base_urls?.[0] ?? "");
      })
      .catch(() => {});
  }, []);

  if (!state) return null;

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const saved = await api.account.saveLlmKey({ api_key: apiKey, base_url: baseUrl, model: model || undefined });
      setState({ ...state, ...saved });
      setApiKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the key.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.account.removeLlmKey();
      setState({ ...state, configured: false, last4: null, model: null });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section style={{ marginTop: 40, borderTop: "1px solid var(--border)", paddingTop: 24 }}>
      <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 8 }}>Your own AI key</h2>
      <p style={{ color: "var(--text-tertiary)", fontSize: 14, marginBottom: 16 }}>
        Optional. AI summaries for your digest and the articles you open then run on your provider account, with no
        daily limit from your plan. The key is stored encrypted and is never shown again; only you are billed for it.
      </p>
      {state.configured ? (
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 14 }}>
            Key ending in <code>{state.last4 || "····"}</code> at {state.base_url}
            {state.model ? ` (${state.model})` : ""}
          </span>
          <button style={BUTTON} onClick={remove} disabled={busy}>
            Remove key
          </button>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          <label style={{ fontSize: 14 }}>
            Provider
            <select style={{ ...INPUT, display: "block", marginTop: 4 }} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}>
              {(state.allowed_base_urls ?? []).map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </label>
          <label style={{ fontSize: 14 }}>
            API key
            <input
              style={{ ...INPUT, display: "block", marginTop: 4 }}
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>
          <label style={{ fontSize: 14 }}>
            Model (optional)
            <input
              style={{ ...INPUT, display: "block", marginTop: 4 }}
              placeholder="the instance's summary model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
          <div>
            <button style={BUTTON} onClick={save} disabled={busy || apiKey.trim().length < 8}>
              {busy ? "Checking…" : "Check and save"}
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" style={{ color: "#dc2626", fontSize: 14, marginTop: 12 }}>
          {error}
        </p>
      )}
    </section>
  );
}
