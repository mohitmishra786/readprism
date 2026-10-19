"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { BillingState } from "../lib/types";

const BUTTON = {
  padding: "8px 16px",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  background: "var(--bg-elevated)",
  cursor: "pointer",
} as const;

function day(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString() : "";
}

function describe(state: BillingState): string {
  switch (state.plan) {
    case "trial":
      return `Free trial: ${state.trial_days_left ?? 0} days left (until ${day(state.trial_ends_at)}).`;
    case "pro":
    case "team": {
      const name = state.plan === "team" ? "Team" : "Pro";
      if (state.status === "cancelled") return `${name}, cancelled: active until ${day(state.plan_expires_at)}.`;
      if (state.status === "past_due") return `${name}: the last payment failed. Update your card to keep access.`;
      return state.plan_expires_at ? `${name}: renews ${day(state.plan_expires_at)}.` : `${name}.`;
    }
    default:
      return "No active plan. Subscribe to keep your digests coming.";
  }
}

// Hosted plan and billing (#173). Renders nothing on self-hosted instances.
export function PlanSection() {
  const [state, setState] = useState<BillingState | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.billing.state().then(setState).catch(() => {});
  }, []);

  if (!state || state.plan === "selfhost") return null;

  const go = (pending: Promise<{ url: string }>) =>
    pending
      .then(({ url }) => {
        window.location.href = url;
      })
      .catch(() => setError("Billing is unavailable right now. Try again in a few minutes."));

  const paying = (state.plan === "pro" || state.plan === "team") && state.status !== "cancelled";

  return (
    <section style={{ marginTop: 40, borderTop: "1px solid var(--border)", paddingTop: 24 }}>
      <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 8 }}>Plan</h2>
      <p style={{ color: "var(--text-tertiary)", fontSize: 14, marginBottom: 16 }}>{describe(state)}</p>
      {state.billing_enabled && state.academic_discount && !paying && (
        <p style={{ fontSize: 14, marginBottom: 12 }} role="status">
          🎓 Academic discount: your university email qualifies, and the discount is applied at checkout.
        </p>
      )}
      {state.billing_enabled && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {!paying && (
            <>
              <button style={BUTTON} onClick={() => go(api.billing.checkout("month"))}>
                Subscribe monthly
              </button>
              <button style={BUTTON} onClick={() => go(api.billing.checkout("year"))}>
                Subscribe yearly
              </button>
            </>
          )}
          {state.can_manage && (
            <button style={BUTTON} onClick={() => go(api.billing.portal())}>
              Manage billing
            </button>
          )}
        </div>
      )}
      {error && <p style={{ color: "#dc2626", fontSize: 14, marginTop: 12 }}>{error}</p>}
    </section>
  );
}
