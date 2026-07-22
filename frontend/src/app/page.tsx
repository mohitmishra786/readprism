"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Menu, X } from "lucide-react";
import { isAuthenticated } from "../lib/auth";

// Asset URLs — kept exactly per the design spec (atmospheric dark imagery that
// the spotlight reveals). Swap here to retheme without touching the mechanic.
const BG_IMAGE_1 =
  "https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260609_195923_b0ba8ace-1d1d-4f2c-9a28-1ab84b330680.png&w=1280&q=85";
const BG_IMAGE_2 =
  "https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260609_201152_bba90a12-bf12-459f-91f0-51f237dbaf3b.png&w=1280&q=85";

// Radius of the soft circular mask that reveals the second image.
const SPOTLIGHT_R = 260;

// Center-nav links point at the real existing app routes.
const NAV_LINKS = [
  { label: "Digest", href: "/digest", active: true },
  { label: "Sources", href: "/sources", active: false },
  { label: "Creators", href: "/creators", active: false },
  { label: "Search", href: "/search", active: false },
  { label: "Feed", href: "/feed", active: false },
];

/**
 * RevealLayer — draws a soft radial-gradient mask onto a hidden canvas each
 * frame, then applies it (as a data URL) to the reveal <div>. The second image
 * (BG_IMAGE_2) is only visible inside the glowing circle that trails the cursor.
 */
function RevealLayer({
  image,
  cursorX,
  cursorY,
  revealAll = false,
}: {
  image: string;
  cursorX: number;
  cursorY: number;
  revealAll?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const revealRef = useRef<HTMLDivElement | null>(null);

  // Size the hidden canvas to the viewport on mount + resize.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const size = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    size();
    window.addEventListener("resize", size);
    return () => window.removeEventListener("resize", size);
  }, []);

  // Rebuild the radial-gradient mask every render (cursor moved).
  useEffect(() => {
    const canvas = canvasRef.current;
    const reveal = revealRef.current;
    if (!canvas || !reveal) return;
    // Static-reveal mode (touch / reduced-motion): show the whole hero, no
    // per-frame canvas work (audit 09-5).
    if (revealAll) {
      reveal.style.maskImage = "none";
      reveal.style.webkitMaskImage = "none";
      return;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const grad = ctx.createRadialGradient(
      cursorX,
      cursorY,
      0,
      cursorX,
      cursorY,
      SPOTLIGHT_R,
    );
    grad.addColorStop(0, "rgba(255,255,255,1)");
    grad.addColorStop(0.4, "rgba(255,255,255,1)");
    grad.addColorStop(0.6, "rgba(255,255,255,0.75)");
    grad.addColorStop(0.75, "rgba(255,255,255,0.4)");
    grad.addColorStop(0.88, "rgba(255,255,255,0.12)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cursorX, cursorY, SPOTLIGHT_R, 0, Math.PI * 2);
    ctx.fill();

    const url = canvas.toDataURL();
    reveal.style.maskImage = `url(${url})`;
    reveal.style.webkitMaskImage = `url(${url})`;
    reveal.style.maskSize = "100% 100%";
    reveal.style.webkitMaskSize = "100% 100%";
  }, [cursorX, cursorY, revealAll]);

  return (
    <>
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none"
        style={{ display: "none" }}
      />
      <div
        ref={revealRef}
        className="absolute inset-0 bg-center bg-cover bg-no-repeat z-30 pointer-events-none"
        style={{ backgroundImage: `url(${image})` }}
      />
    </>
  );
}

export default function RootPage() {
  const router = useRouter();

  // Spotlight tracking: raw mouse ref + eased (lerped) ref, RAF-driven.
  const mouse = useRef({ x: -999, y: -999 });
  const smooth = useRef({ x: -999, y: -999 });
  const rafRef = useRef<number | null>(null);
  const [cursorPos, setCursorPos] = useState({ x: -999, y: -999 });

  const [menuOpen, setMenuOpen] = useState(false);
  const [staticReveal, setStaticReveal] = useState(false);

  useEffect(() => {
    if (isAuthenticated()) router.replace("/digest");
  }, [router]);

  useEffect(() => {
    // Degrade gracefully (audit 09-5): on touch devices (no fine pointer) or
    // when the user prefers reduced motion, skip the RAF spotlight loop and its
    // per-frame canvas work entirely — just reveal the hero statically.
    const reduce =
      typeof window !== "undefined" &&
      (window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
        window.matchMedia("(pointer: coarse)").matches);

    if (reduce) {
      setStaticReveal(true);
      return;
    }

    const onMove = (e: MouseEvent) => {
      mouse.current.x = e.clientX;
      mouse.current.y = e.clientY;
    };
    window.addEventListener("mousemove", onMove);

    const tick = () => {
      smooth.current.x += (mouse.current.x - smooth.current.x) * 0.1;
      smooth.current.y += (mouse.current.y - smooth.current.y) * 0.1;
      setCursorPos({ x: smooth.current.x, y: smooth.current.y });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("mousemove", onMove);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <div
      className="min-h-screen bg-white tracking-[-0.02em]"
      style={{ fontFamily: "'Inter', sans-serif" }}
    >
      {/* ===== Navigation (fixed, over hero) ===== */}
      <nav className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-between p-4 sm:p-5">
        {/* Left: prism logo + wordmark */}
        <a href="/" className="flex items-center gap-2">
          <svg
            width="26"
            height="26"
            viewBox="0 0 256 256"
            fill="#ffffff"
            aria-hidden="true"
          >
            <path d="M 128 0 L 256 128 L 128 256 L 0 128 Z M 128 64 L 64 128 L 128 192 L 192 128 Z" />
          </svg>
          <span className="text-white text-2xl font-playfair italic">ReadPrism</span>
        </a>

        {/* Center pill (desktop) */}
        <div className="hidden md:flex absolute left-1/2 -translate-x-1/2 bg-white/20 backdrop-blur-md border border-white/30 rounded-full px-2 py-2 items-center gap-1">
          {NAV_LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                link.active
                  ? "text-white"
                  : "text-white/80 hover:bg-white/20 hover:text-white"
              }`}
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Right (desktop) */}
        <a
          href="/register"
          className="hidden md:block bg-white text-gray-900 text-sm font-semibold px-6 py-2.5 rounded-full hover:bg-gray-100"
        >
          Get started
        </a>

        {/* Right (mobile) — hamburger */}
        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          className="md:hidden text-white p-2"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </nav>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="fixed top-16 left-4 right-4 z-[100] md:hidden bg-black/80 backdrop-blur-md border border-white/20 rounded-2xl p-4 flex flex-col gap-1">
          {NAV_LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              className={`px-4 py-2.5 rounded-full text-sm font-medium ${
                link.active ? "text-white" : "text-white/80 hover:text-white"
              }`}
            >
              {link.label}
            </a>
          ))}
          <div className="my-1 h-px bg-white/15" />
          <a
            href="/login"
            onClick={() => setMenuOpen(false)}
            className="px-4 py-2.5 rounded-full text-sm font-medium text-white/80 hover:text-white"
          >
            Sign in
          </a>
          <a
            href="/register"
            onClick={() => setMenuOpen(false)}
            className="px-4 py-2.5 rounded-full text-sm font-semibold text-center bg-white text-gray-900"
          >
            Get started
          </a>
        </div>
      )}

      {/* ===== Hero section ===== */}
      <section
        className="relative w-full overflow-hidden bg-black"
        style={{ height: "100dvh" }}
      >
        {/* 1. Base image */}
        <div
          className="absolute inset-0 bg-center bg-cover bg-no-repeat hero-zoom z-10"
          style={{ backgroundImage: `url(${BG_IMAGE_1})` }}
        />

        {/* 2. Reveal layer (cursor spotlight) */}
        <RevealLayer
          image={BG_IMAGE_2}
          cursorX={cursorPos.x}
          cursorY={cursorPos.y}
          revealAll={staticReveal}
        />

        {/* 3. Heading */}
        <div className="absolute top-[14%] left-0 right-0 flex flex-col items-center text-center px-5 pointer-events-none z-50">
          <h1 className="text-white leading-[0.95]">
            <span
              className="block font-playfair italic font-normal text-5xl sm:text-7xl md:text-8xl hero-anim hero-reveal"
              style={{ letterSpacing: "-0.05em", animationDelay: "0.25s" }}
            >
              Everything you follow,
            </span>
            <span
              className="block font-normal text-5xl sm:text-7xl md:text-8xl -mt-1 hero-anim hero-reveal"
              style={{ letterSpacing: "-0.08em", animationDelay: "0.42s" }}
            >
              ranked for you.
            </span>
          </h1>
        </div>

        {/* 4. Bottom-left paragraph */}
        <div className="hidden sm:block absolute bottom-14 left-10 md:left-14 max-w-[260px] z-50 hero-anim hero-fade" style={{ animationDelay: "0.7s" }}>
          <p className="text-sm text-white/80 leading-relaxed">
            Every signal — scroll depth, source trust, the topics you return to —
            feeds a model that learns what&apos;s worth your attention. Not
            chronology. Not popularity. Relevance.
          </p>
        </div>

        {/* 5. Bottom-right block */}
        <div
          className="absolute bottom-10 sm:bottom-24 left-5 right-5 sm:left-auto sm:right-10 md:right-14 max-w-full sm:max-w-[260px] flex flex-col items-start gap-4 sm:gap-5 z-50 hero-anim hero-fade"
          style={{ animationDelay: "0.85s" }}
        >
          <p className="text-xs sm:text-sm text-white/80 leading-relaxed">
            Tap “Why this?” on any item to see exactly which of the eight signals
            drove its ranking — and how strongly. One score, and it&apos;s yours.
          </p>
          <a
            href="/register"
            className="bg-[#e8702a] hover:bg-[#d2611f] text-white text-sm font-medium px-7 py-3 rounded-full transition-all hover:scale-[1.03] active:scale-95 hover:shadow-lg hover:shadow-[#e8702a]/30"
          >
            Start reading
          </a>
        </div>
      </section>
    </div>
  );
}
