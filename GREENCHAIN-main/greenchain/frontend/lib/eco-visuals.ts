export interface EcoDotStyles {
  background: string
  shadow: string
}

export interface EcoRoutePalette {
  coreFaint: string
  coreMedium: string
  coreSoft: string
  coreStrong: string
  glowFaint: string
  glowMedium: string
  glowStrong: string
  highlightCore: string
  highlightGlowSoft: string
  highlightGlowStrong: string
  pulseFaint: string
  pulseMedium: string
  pulseStrong: string
}

export interface EcoSelectionStyles {
  accent: string
  edge: string
  glow: string
  surface: string
  surfaceStrong: string
}

interface EcoVisualTone {
  dot: EcoDotStyles
  route: EcoRoutePalette
  selection: EcoSelectionStyles
}

function hexToRgba(hex: string, alpha: number) {
  const normalized = hex.replace("#", "")
  const value =
    normalized.length === 3
      ? normalized
          .split("")
          .map((char) => `${char}${char}`)
          .join("")
      : normalized

  const red = parseInt(value.slice(0, 2), 16)
  const green = parseInt(value.slice(2, 4), 16)
  const blue = parseInt(value.slice(4, 6), 16)

  return `rgba(${red},${green},${blue},${alpha})`
}

export function withAlpha(color: string, alpha: number) {
  if (color.startsWith("#")) {
    return hexToRgba(color, alpha)
  }

  const rgbMatch = color.match(
    /rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i
  )

  if (!rgbMatch) {
    return color
  }

  return `rgba(${rgbMatch[1]},${rgbMatch[2]},${rgbMatch[3]},${alpha})`
}

function createEcoVisualTone(base: string, pulse: string): EcoVisualTone {
  return {
    dot: {
      background: base,
      shadow: `0 0 10px ${withAlpha(base, 0.3)}`,
    },
    route: {
      coreFaint: withAlpha(base, 0.16),
      coreMedium: withAlpha(base, 0.76),
      coreSoft: withAlpha(base, 0.52),
      coreStrong: base,
      glowFaint: withAlpha(base, 0.06),
      glowMedium: withAlpha(base, 0.18),
      glowStrong: withAlpha(base, 0.3),
      highlightCore: withAlpha(base, 0.9),
      highlightGlowSoft: withAlpha(base, 0.14),
      highlightGlowStrong: withAlpha(base, 0.24),
      pulseFaint: withAlpha(pulse, 0.2),
      pulseMedium: withAlpha(pulse, 0.68),
      pulseStrong: withAlpha(pulse, 0.88),
    },
    selection: {
      accent: base,
      edge: withAlpha(base, 0.46),
      glow: `0 0 14px ${withAlpha(base, 0.12)}`,
      surface: withAlpha(base, 0.08),
      surfaceStrong: withAlpha(base, 0.13),
    },
  }
}

const GOOD_VISUALS = createEcoVisualTone("#34D399", "#ECFDF5")
const MODERATE_VISUALS = createEcoVisualTone("#FBBF24", "#FEF3C7")
const HIGH_VISUALS = createEcoVisualTone("#F87171", "#FEE2E2")

function getEcoVisualTone(score: number) {
  if (score < 40) {
    return GOOD_VISUALS
  }

  if (score < 60) {
    return MODERATE_VISUALS
  }

  return HIGH_VISUALS
}

export function getEcoDotStyles(score: number) {
  return getEcoVisualTone(score).dot
}

export function getEcoRoutePalette(score: number) {
  return getEcoVisualTone(score).route
}

export function getEcoSelectionStyles(score: number) {
  return getEcoVisualTone(score).selection
}
