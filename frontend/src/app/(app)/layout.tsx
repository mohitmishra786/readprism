"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated, removeToken } from "../../lib/auth";

const navStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 24,
  padding: "12px 24px",
  background: "#fff",
  borderBottom: "1px solid #e5e7eb",
  position: "sticky",
  top: 0,
  zIndex: 10,
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (!isAuthenticated()) {
      router.replace("/login");
    }
  }, [router]);

  if (!mounted) return null;

  return (
    <div>
      <nav style={navStyle}>
        <span style={{ fontWeight: 700, fontSize: "1.1rem", color: "#1d4ed8" }}>ReadPrism</span>
        <a href="/digest" style={{ color: "#374151", textDecoration: "none" }}>Digest</a>
        <a href="/feed" style={{ color: "#374151", textDecoration: "none" }}>Feed</a>
        <a href="/sources" style={{ color: "#374151", textDecoration: "none" }}>Sources</a>
        <a href="/creators" style={{ color: "#374151", textDecoration: "none" }}>Creators</a>
        <a href="/search" style={{ color: "#374151", textDecoration: "none" }}>Search</a>
        <a href="/preferences" style={{ color: "#374151", textDecoration: "none" }}>Preferences</a>
        <button
          onClick={() => { removeToken(); router.replace("/login"); }}
          style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "#6b7280" }}
        >
          Sign out
        </button>
      </nav>
      <main style={{ maxWidth: 900, margin: "0 auto", padding: "24px 16px" }}>
        {children}
      </main>
    </div>
  );
}
