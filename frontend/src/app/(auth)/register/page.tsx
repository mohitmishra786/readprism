"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../../lib/api";
import { setToken } from "../../../lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await api.auth.register(email, password, displayName || undefined);
      setToken(token.access_token);
      router.replace("/digest");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: "0 16px" }}>
      <h1 style={{ fontSize: "1.75rem", fontWeight: 700, marginBottom: 8 }}>ReadPrism</h1>
      <p style={{ color: "#666", marginBottom: 32 }}>Create your account</p>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontWeight: 500 }}>Display name (optional)</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6 }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontWeight: 500 }}>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6 }}
          />
        </div>
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", marginBottom: 4, fontWeight: 500 }}>Password (min 8 chars)</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
            style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6 }}
          />
        </div>
        {error && <p style={{ color: "#ef4444", marginBottom: 16 }}>{error}</p>}
        <button
          type="submit"
          disabled={loading}
          style={{
            width: "100%",
            padding: "10px",
            background: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            fontSize: "1rem",
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? "Creating account..." : "Create account"}
        </button>
      </form>
      <p style={{ marginTop: 16, textAlign: "center" }}>
        Have an account? <a href="/login" style={{ color: "#2563eb" }}>Sign in</a>
      </p>
    </div>
  );
}
