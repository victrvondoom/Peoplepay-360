import { cn } from "@/lib/utils"

type GreenChainLogoProps = {
  className?: string
  title?: string
  /** Use on dark backgrounds so the first syllable stays legible. */
  variant?: "default" | "onDark"
}

export function GreenChainLogo({
  className,
  title = "GreenChain",
  variant = "default",
}: GreenChainLogoProps) {
  const firstFill = variant === "onDark" ? "#f8fafc" : "#0f172a"

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 280 52"
      className={cn("block h-8 w-auto shrink-0 sm:h-9 md:h-10", className)}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <text
        x="0"
        y="38"
        fontFamily="'Inter', '-apple-system', 'Helvetica Neue', Arial, sans-serif"
        fontSize="36"
        fontWeight="800"
        letterSpacing="-2"
      >
        <tspan fill={firstFill}>green</tspan>
        <tspan fill="#16a34a">chain</tspan>
      </text>
    </svg>
  )
}
