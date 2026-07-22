"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../../lib/api";
import { setToken } from "../../../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [magicSent, setMagicSent] = useState(false);

  const sendMagicLink = async () => {
    if (!email) {
      setError("Enter your email first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.auth.magicLinkRequest(email);
      setMagicSent(true);
    } catch {
      // Non-enumerating: show the same success either way.
      setMagicSent(true);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await api.auth.login(email, password);
      setToken(token.access_token, token.refresh_token);
      router.replace("/digest");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="prism-mark text-3xl">◭ ReadPrism</div>
          <p className="mt-2 text-sm text-stone-500">Sign in to your account</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="card space-y-4 p-6"
        >
          <div>
            <label className="mb-1.5 block text-sm font-medium text-stone-700">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="input"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-stone-700">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="input"
            />
          </div>
          {error && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-2.5"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>

          <div className="pt-1 text-center">
            {magicSent ? (
              <p className="text-sm text-emerald-700">
                Check your email for a sign-in link.
              </p>
            ) : (
              <button
                type="button"
                onClick={sendMagicLink}
                disabled={loading}
                className="text-sm text-stone-500 underline-offset-2 hover:text-prism-600 hover:underline"
              >
                Email me a sign-in link instead
              </button>
            )}
          </div>
        </form>

        <p className="mt-6 text-center text-sm text-stone-500">
          No account?{" "}
          <a href="/register" className="font-medium text-prism-600 hover:text-prism-700">
            Register
          </a>
        </p>
      </div>
    </div>
  );
}
