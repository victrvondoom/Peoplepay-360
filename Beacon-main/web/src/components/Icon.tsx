/* Vector icons.
   Every icon the interface needs as a *shape* lives here as inline SVG.

   Why not Unicode glyphs: the three families this app loads (Figtree,
   EB Garamond, Geist Mono) contain no symbol or emoji coverage, so ◉ 🎙 ☾ ↩︎ ✓ ✗ ✕
   were all silently substituted by whatever font Windows picked. That is why the
   mic read as a plain circle. A path cannot be substituted.

   Sizing follows the text: 1em square, currentColor. Decorative by default
   (aria-hidden); pass a label to expose one to assistive technology. */
import type { CSSProperties, ReactNode } from "react";

export type IconName =
  | "mic"
  | "recording"
  | "play"
  | "moon"
  | "check"
  | "cross"
  | "close"
  | "undo"
  | "chevronRight"
  | "arrowLeft"
  | "arrowRight";

export interface IconProps {
  name: IconName;
  /** Multiplier on the surrounding font size. Default 1. */
  size?: number;
  /** Accessible name. Omit for decorative icons (the default). */
  label?: string;
  className?: string;
  style?: CSSProperties;
  strokeWidth?: number;
}

/* 24x24 viewBox. Stroke icons inherit strokeWidth; filled shapes opt out. */
const PATHS: Record<IconName, ReactNode> = {
  mic: (
    <>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10.5a7 7 0 0 0 14 0" />
      <path d="M12 17.5V21" />
      <path d="M8.5 21h7" />
    </>
  ),
  recording: (
    <>
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
    </>
  ),
  play: <path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none" />,
  moon: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a7.5 7.5 0 1 0 10.5 10.5z" />,
  check: <path d="M4.5 12.5 9.5 17.5 19.5 6.5" />,
  cross: (
    <>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </>
  ),
  close: (
    <>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </>
  ),
  undo: (
    <>
      <path d="M4 9h11a5 5 0 0 1 0 10h-6" />
      <path d="M8 5 4 9l4 4" />
    </>
  ),
  chevronRight: <path d="M9.5 5.5 16 12l-6.5 6.5" />,
  arrowLeft: (
    <>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </>
  ),
  arrowRight: (
    <>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </>
  ),
};

export function Icon({ name, size = 1, label, className, style, strokeWidth = 2 }: IconProps) {
  const shape = PATHS[name];
  // An unknown name must never crash a render.
  if (!shape) {
    if (import.meta.env.DEV) console.warn(`<Icon> unknown name: ${String(name)}`);
    return null;
  }
  const a11y = label ? { role: "img" as const, "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg
      {...a11y}
      focusable="false"
      className={className ? `icon ${className}` : "icon"}
      viewBox="0 0 24 24"
      width={`${size}em`}
      height={`${size}em`}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
    >
      {shape}
    </svg>
  );
}

export default Icon;
