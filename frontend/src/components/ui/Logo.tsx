import Link from "next/link";

// The Weirling mark: the landing page's diamond and italic Playfair wordmark.
// One component so every page shows the same logo (#159).
export function LogoMark({ size = 24, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 256 256" fill={color} aria-hidden="true">
      <path d="M 128 0 L 256 128 L 128 256 L 0 128 Z M 128 64 L 64 128 L 128 192 L 192 128 Z" />
    </svg>
  );
}

export function Logo({
  href = "/",
  size = "md",
  label = "Weirling home",
}: {
  href?: string | null;
  size?: "md" | "lg";
  label?: string;
}) {
  const content = (
    <span className="inline-flex items-center gap-2 text-white">
      <LogoMark size={size === "lg" ? 30 : 22} />
      <span className={`font-playfair italic ${size === "lg" ? "text-3xl" : "text-2xl"}`}>
        Weirling
      </span>
    </span>
  );
  if (!href) return content;
  return (
    <Link href={href} aria-label={label} className="inline-flex">
      {content}
    </Link>
  );
}
