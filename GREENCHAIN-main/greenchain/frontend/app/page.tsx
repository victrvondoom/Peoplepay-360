"use client"

import {
  useCallback,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  useSyncExternalStore,
} from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"

import { GreenChainLogo } from "@/components/green-chain-logo"
import { DashboardLaunchOverlay } from "@/components/launch/dashboard-launch-overlay"
import { cn } from "@/lib/utils"

const IMG = {
  heroVid: "/landing/Video_Generation_Complete.mp4",
  heroBg:
    "/landing/Cinematic_top-down_aerial_photograph_of_an_expansi-1776490199103.png",
  warehouse:
    "/landing/Stunning_photorealistic_interior_view_of_a_futuris-1776490260857.png",
  circuit:
    "/landing/Epic_extreme_macro_photography_shot_of_a_vivid_gre-1776490265657.png",
  engineers:
    "/landing/High-quality_candid_photojournalistic_image_of_two-1776490282355.png",
  port: "/landing/Epic_high-altitude_aerial_drone_photograph_of_an_e-1776490293039.png",
  ai: "/landing/Stunning_abstract_conceptual_visualization_of_an_A-1776490301437.png",
  globe:
    "/landing/Stunning_translucent_dark-blue_globe_of_planet_Ear-1776490521137.png",
  ctaPush:
    "/landing/Cinematic_photograph_of_a_professional_engineer_st-1776490359376.png",
  team: "/landing/Candid_editorial_photograph_of_a_diverse_professio-1776490341439.png",
} as const

type Feature = {
  img: string
  label: string
  title: string
  body: string
  bullets: string[]
}

const HERO_SIGNALS = [
  {
    label: "demand",
    value: "Product and destination",
    detail:
      "Define what you need to source, how much you need, and where it needs to arrive.",
  },
  {
    label: "Compare",
    value: "Country and transport",
    detail:
      "Test manufacturing countries side by side and see how shipping mode changes the result.",
  },
  {
    label: "decide",
    value: "Ranking and recommendation",
    detail:
      "Review the tradeoffs quickly and export a short memo with the strongest option.",
  },
] as const

const FEATURES: Feature[] = [
  {
    img: IMG.warehouse,
    label: "Prototype Flow",
    title: "Compare sourcing scenarios quickly.",
    body: "The brief is intentionally focused: compare a few sourcing options quickly, show what drives the footprint, and make the transport tradeoff obvious.",
    bullets: [
      "Product, quantity, and destination input",
      "Country and transport mode comparison",
      "Quick ranked output for sourcing teams",
    ],
  },
  {
    img: IMG.engineers,
    label: "Supply Chain Graph",
    title: "See manufacturers and links as a live network.",
    body: "The graph view turns suppliers, facilities, and routes into a structure you can inspect instead of a list you have to mentally piece together.",
    bullets: [
      "Interactive nodes and connections",
      "Status-focused details",
      "Fast visual context for sourcing decisions",
    ],
  },
  {
    img: IMG.globe,
    label: "Geographic View",
    title: "Match the network with real-world location context.",
    body: "The geographic view makes transport tradeoffs easier to read by putting facilities and routes into a single global frame.",
    bullets: [
      "Location-driven exploration",
      "Graph + globe side by side",
      "Clearer context for transport choices",
    ],
  },
]

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

function useInView(threshold = 0.18) {
  const ref = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setInView(true)
      },
      { threshold }
    )

    observer.observe(element)
    return () => observer.disconnect()
  }, [threshold])

  return { ref, inView }
}

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")
    const update = () => setPrefersReducedMotion(mediaQuery.matches)

    update()
    mediaQuery.addEventListener("change", update)
    return () => mediaQuery.removeEventListener("change", update)
  }, [])

  return prefersReducedMotion
}

function usePrefersReducedMotionSnapshot() {
  return useSyncExternalStore(
    (onStoreChange) => {
      const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")
      mediaQuery.addEventListener("change", onStoreChange)
      return () => mediaQuery.removeEventListener("change", onStoreChange)
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false
  )
}

function DashboardLaunchButton({
  children,
  className,
  disabled = false,
  onLaunch,
}: {
  children: React.ReactNode
  className?: string
  disabled?: boolean
  onLaunch: () => void
}) {
  return (
    <button
      type="button"
      onClick={onLaunch}
      disabled={disabled}
      aria-disabled={disabled}
      className={cn(
        className,
        "disabled:pointer-events-none disabled:cursor-progress disabled:opacity-70"
      )}
    >
      {children}
    </button>
  )
}

function Eyebrow({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return <p className={cn("eyebrow", className)}>{children}</p>
}

function Reveal({
  children,
  className,
  delay = 0,
  y = 28,
}: {
  children: React.ReactNode
  className?: string
  delay?: number
  y?: number
}) {
  const { ref, inView } = useInView()

  return (
    <div
      ref={ref}
      className={cn(
        "transition-all duration-[1150ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
        className
      )}
      style={{
        opacity: inView ? 1 : 0,
        transform: inView ? "translateY(0px)" : `translateY(${y}px)`,
        transitionDelay: `${delay}ms`,
      }}
    >
      {children}
    </div>
  )
}

function LineReveal({
  lines,
  active,
  className,
  lineClass,
  delay = 0,
}: {
  lines: React.ReactNode[]
  active: boolean
  className?: string
  lineClass?: string
  delay?: number
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {lines.map((line, index) => (
        <div key={index} className="overflow-hidden pr-[0.04em]">
          <div
            className={cn(lineClass, "pb-[0.42em]")}
            style={{
              opacity: active ? 1 : 0,
              transform: active ? "translateY(0%)" : "translateY(118%)",
              transition:
                "transform 1.45s cubic-bezier(0.16,1,0.3,1), opacity 1.05s ease",
              transitionDelay: `${delay + index * 180}ms`,
            }}
          >
            {line}
          </div>
        </div>
      ))}
    </div>
  )
}

function ParallaxMedia({
  src,
  alt,
  className,
  speed = 0.14,
  sizes,
  priority = false,
}: {
  src: string
  alt: string
  className?: string
  speed?: number
  sizes: string
  priority?: boolean
}) {
  const frameRef = useRef<HTMLDivElement>(null)
  const mediaRef = useRef<HTMLDivElement>(null)
  const prefersReducedMotion = usePrefersReducedMotion()

  const syncTransform = useEffectEvent(() => {
    const frame = frameRef.current
    const media = mediaRef.current
    if (!frame || !media) return

    if (prefersReducedMotion) {
      media.style.transform = "translate3d(0,0,0) scale(1.04)"
      return
    }

    const rect = frame.getBoundingClientRect()
    const viewportHeight = window.innerHeight || 1
    const progress = clamp(
      (viewportHeight - rect.top) / (viewportHeight + rect.height),
      0,
      1
    )
    const centered = progress * 2 - 1
    const translateY = clamp(centered * speed * -160, -72, 72)

    media.style.transform = `translate3d(0, ${translateY.toFixed(1)}px, 0) scale(1.12)`
  })

  useEffect(() => {
    let frame = 0

    const onFrame = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(syncTransform)
    }

    onFrame()
    window.addEventListener("scroll", onFrame, { passive: true })
    window.addEventListener("resize", onFrame)

    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("scroll", onFrame)
      window.removeEventListener("resize", onFrame)
    }
  }, [prefersReducedMotion])

  return (
    <div ref={frameRef} className={cn("relative overflow-hidden", className)}>
      <div
        ref={mediaRef}
        className="absolute inset-[-12%] will-change-transform"
      >
        <Image
          src={src}
          alt={alt}
          fill
          priority={priority}
          sizes={sizes}
          className="object-cover"
        />
      </div>
    </div>
  )
}

function TiltCard({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const prefersReducedMotion = usePrefersReducedMotion()

  const onMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (prefersReducedMotion || !ref.current) return

    const rect = ref.current.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width - 0.5
    const y = (event.clientY - rect.top) / rect.height - 0.5

    ref.current.style.transform = `perspective(1100px) rotateY(${(x * 7).toFixed(2)}deg) rotateX(${(-y * 7).toFixed(2)}deg) translate3d(0,-2px,0) scale3d(1.01,1.01,1.01)`
  }

  const onLeave = () => {
    if (!ref.current) return
    ref.current.style.transform =
      "perspective(1100px) rotateY(0deg) rotateX(0deg) translate3d(0,0,0) scale3d(1,1,1)"
  }

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      className={className}
      style={{
        transition: "transform 420ms cubic-bezier(0.16,1,0.3,1)",
        willChange: "transform",
        transformStyle: "preserve-3d",
      }}
    >
      {children}
    </div>
  )
}

const BLOOM_SPRITE_SCALE = 2

/** Pre-renders a radial glow once so the frame loop can blit it instead of building gradients. */
function createBloomSprite(radius: number, color: string, alpha: number) {
  const size = Math.max(2, Math.ceil(radius * 2 * BLOOM_SPRITE_SCALE))
  const sprite = document.createElement("canvas")
  sprite.width = size
  sprite.height = size

  const context = sprite.getContext("2d")
  if (!context) return sprite

  const center = size / 2
  const gradient = context.createRadialGradient(
    center,
    center,
    0,
    center,
    center,
    center
  )
  gradient.addColorStop(0, `rgba(${color},${alpha})`)
  gradient.addColorStop(0.35, `rgba(${color},${alpha * 0.45})`)
  gradient.addColorStop(1, `rgba(${color},0)`)
  context.fillStyle = gradient
  context.fillRect(0, 0, size, size)

  return sprite
}

function HeroThreeField({ disabled }: { disabled: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (disabled) return

    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    const context = canvas.getContext("2d")
    if (!context) return

    const randomBetween = (min: number, max: number) =>
      min + Math.random() * (max - min)
    const lerp = (from: number, to: number, amount: number) =>
      from + (to - from) * amount

    const orbiters = Array.from({ length: 16 }, (_, index) => {
      const size = randomBetween(1.8, 4.8)
      const alpha = randomBetween(0.24, 0.58)
      const color =
        index % 3 === 0
          ? "148,255,209"
          : index % 3 === 1
            ? "110,214,255"
            : "200,255,235"

      return {
        radiusX: randomBetween(110, 270),
        radiusY: randomBetween(60, 185),
        size,
        speed: randomBetween(0.12, 0.36) * (index % 2 === 0 ? 1 : -1),
        phase: randomBetween(0, Math.PI * 2),
        alpha,
        color,
        bloom: createBloomSprite(size * 4.8, color, alpha),
      }
    })
    const dustAlphaBuckets = [0.1, 0.14, 0.18, 0.22]
    const dust = Array.from({ length: 180 }, () => ({
      radiusX: randomBetween(130, 520),
      radiusY: randomBetween(90, 310),
      size: randomBetween(0.6, 2.2),
      speed: randomBetween(0.03, 0.11),
      phase: randomBetween(0, Math.PI * 2),
      offset: randomBetween(-0.8, 0.8),
      bucket: Math.floor(Math.random() * dustAlphaBuckets.length),
    }))

    const pointerTarget = { x: 0, y: 0 }
    const pointerCurrent = { x: 0, y: 0 }
    let width = 1
    let height = 1
    let frame = 0
    let running = false
    const start = performance.now()

    const onPointerMove = (event: PointerEvent) => {
      const rect = container.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      pointerTarget.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointerTarget.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1)
    }

    const onPointerLeave = () => {
      pointerTarget.x = 0
      pointerTarget.y = 0
    }

    const resize = () => {
      const rect = container.getBoundingClientRect()
      if (!rect.width || !rect.height) return

      width = rect.width
      height = rect.height

      const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    resize()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(container)
    container.addEventListener("pointermove", onPointerMove)
    container.addEventListener("pointerleave", onPointerLeave)

    const tick = (now: number) => {
      const elapsed = (now - start) / 1000
      pointerCurrent.x = lerp(pointerCurrent.x, pointerTarget.x, 0.075)
      pointerCurrent.y = lerp(pointerCurrent.y, pointerTarget.y, 0.075)

      context.clearRect(0, 0, width, height)

      const centerX = width * 0.5 + pointerCurrent.x * 28
      const centerY = height * 0.38 - pointerCurrent.y * 18
      const radius = Math.min(width, height) * 0.14

      const glow = context.createRadialGradient(
        centerX,
        centerY,
        radius * 0.08,
        centerX,
        centerY,
        radius * 4.2
      )
      glow.addColorStop(0, "rgba(145,255,208,0.24)")
      glow.addColorStop(0.34, "rgba(86,231,173,0.10)")
      glow.addColorStop(0.7, "rgba(85,170,255,0.06)")
      glow.addColorStop(1, "rgba(0,0,0,0)")
      context.fillStyle = glow
      context.fillRect(0, 0, width, height)

      dustAlphaBuckets.forEach((alpha, bucket) => {
        context.beginPath()

        for (const mote of dust) {
          if (mote.bucket !== bucket) continue

          const angle = mote.phase + elapsed * mote.speed
          const x =
            centerX +
            Math.cos(angle) * mote.radiusX +
            pointerCurrent.x * mote.radiusX * 0.05
          const y =
            centerY +
            Math.sin(angle * 1.3 + mote.offset) * mote.radiusY +
            pointerCurrent.y * mote.radiusY * 0.04

          context.moveTo(x + mote.size, y)
          context.arc(x, y, mote.size, 0, Math.PI * 2)
        }

        context.fillStyle = `rgba(148,255,209,${alpha})`
        context.fill()
      })

      context.save()
      context.translate(centerX, centerY)
      context.rotate(elapsed * 0.12 + pointerCurrent.x * 0.18)
      context.strokeStyle = "rgba(172,255,224,0.16)"
      context.lineWidth = 1.2
      context.beginPath()
      context.ellipse(0, 0, radius * 1.85, radius * 1.18, 0.35, 0, Math.PI * 2)
      context.stroke()

      context.rotate(-elapsed * 0.2 + 0.7)
      context.strokeStyle = "rgba(108,214,255,0.16)"
      context.beginPath()
      context.ellipse(0, 0, radius * 1.42, radius * 2.1, 0.2, 0, Math.PI * 2)
      context.stroke()
      context.restore()

      const layers = [
        {
          scale: 1.1,
          stroke: "rgba(184,255,226,0.22)",
          rotation: elapsed * 0.42,
        },
        {
          scale: 0.9,
          stroke: "rgba(98,245,174,0.28)",
          rotation: -elapsed * 0.58 + 0.5,
        },
        {
          scale: 0.7,
          stroke: "rgba(95,208,255,0.18)",
          rotation: elapsed * 0.75 + 1.1,
        },
      ] as const

      for (const layer of layers) {
        context.save()
        context.translate(centerX, centerY)
        context.rotate(layer.rotation + pointerCurrent.x * 0.12)
        context.beginPath()

        for (let index = 0; index <= 10; index += 1) {
          const angle = (index / 10) * Math.PI * 2
          const wobble =
            1 + Math.sin(angle * 3 + elapsed * 1.2 + layer.scale) * 0.14
          const currentRadius = radius * layer.scale * wobble
          const x = Math.cos(angle) * currentRadius
          const y = Math.sin(angle) * currentRadius * 0.84

          if (index === 0) context.moveTo(x, y)
          else context.lineTo(x, y)
        }

        context.closePath()
        context.strokeStyle = layer.stroke
        context.lineWidth = 1
        context.stroke()
        context.restore()
      }

      for (const orbiter of orbiters) {
        const angle = orbiter.phase + elapsed * orbiter.speed
        const x =
          centerX +
          Math.cos(angle) * orbiter.radiusX +
          pointerCurrent.x * orbiter.radiusX * 0.08
        const y =
          centerY +
          Math.sin(angle * 1.2) * orbiter.radiusY +
          pointerCurrent.y * orbiter.radiusY * 0.06

        const bloomRadius = orbiter.size * 4.8
        context.drawImage(
          orbiter.bloom,
          x - bloomRadius,
          y - bloomRadius,
          bloomRadius * 2,
          bloomRadius * 2
        )

        context.fillStyle = `rgba(${orbiter.color},${Math.min(orbiter.alpha + 0.2, 0.9)})`
        context.beginPath()
        context.arc(x, y, orbiter.size, 0, Math.PI * 2)
        context.fill()
      }

      frame = requestAnimationFrame(tick)
    }

    const startLoop = () => {
      if (running) return
      running = true
      frame = requestAnimationFrame(tick)
    }

    const stopLoop = () => {
      running = false
      cancelAnimationFrame(frame)
    }

    const visibilityObserver = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) startLoop()
      else stopLoop()
    })
    visibilityObserver.observe(container)

    return () => {
      stopLoop()
      visibilityObserver.disconnect()
      resizeObserver.disconnect()
      container.removeEventListener("pointermove", onPointerMove)
      container.removeEventListener("pointerleave", onPointerLeave)
    }
  }, [disabled])

  return (
    <div
      ref={containerRef}
      className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
    >
      <canvas
        ref={canvasRef}
        className={cn(
          "h-full w-full transition-opacity duration-700 ease-out",
          disabled ? "opacity-45" : "opacity-100"
        )}
      />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_24%,_rgba(147,255,210,0.12),_transparent_42%),radial-gradient(circle_at_68%_24%,_rgba(126,190,255,0.08),_transparent_36%)]" />
    </div>
  )
}

function Hero({
  introReady,
  isLaunching,
  onLaunchDashboard,
}: {
  introReady: boolean
  isLaunching: boolean
  onLaunchDashboard: () => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const prefersReducedMotion = usePrefersReducedMotion()
  const [mounted, setMounted] = useState(false)
  const [videoReady, setVideoReady] = useState(false)

  useEffect(() => {
    if (!introReady) return
    const timeout = window.setTimeout(() => setMounted(true), 120)
    return () => window.clearTimeout(timeout)
  }, [introReady])

  const syncVideo = useEffectEvent(() => {
    const video = videoRef.current
    if (!video) return

    if (prefersReducedMotion || isLaunching) {
      video.pause()
      return
    }

    video.defaultMuted = true
    video.muted = true

    const playPromise = video.play()
    playPromise?.catch(() => {
      setVideoReady(false)
    })
  })

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    if (prefersReducedMotion || isLaunching) {
      video.pause()
      return
    }

    const onCanPlay = () => {
      setVideoReady(true)
      syncVideo()
    }

    const onLoadedData = () => setVideoReady(true)
    const onError = () => setVideoReady(false)
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") syncVideo()
      else video.pause()
    }

    video.addEventListener("canplay", onCanPlay)
    video.addEventListener("loadeddata", onLoadedData)
    video.addEventListener("error", onError)
    document.addEventListener("visibilitychange", onVisibilityChange)

    syncVideo()

    return () => {
      video.removeEventListener("canplay", onCanPlay)
      video.removeEventListener("loadeddata", onLoadedData)
      video.removeEventListener("error", onError)
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [isLaunching, prefersReducedMotion])

  const fadeUp = (delay: number) => ({
    style: {
      opacity: mounted ? 1 : 0,
      transform: mounted ? "translate3d(0,0,0)" : "translate3d(0,30px,0)",
      transition:
        "opacity 1.05s ease, transform 1.3s cubic-bezier(0.16,1,0.3,1)",
      transitionDelay: `${delay}ms`,
    },
  })

  const heroLines = [
    <>Compare sourcing options</>,
    <>
      before you <span className="text-primary">place the order</span>.
    </>,
  ]

  return (
    <section className="relative min-h-[100svh] overflow-hidden border-b border-white/8">
      <div className="absolute inset-0 -z-20">
        <Image
          src={IMG.heroBg}
          alt=""
          fill
          priority
          sizes="100vw"
          className={cn(
            "object-cover transition-transform duration-[3400ms] ease-[cubic-bezier(0.25,1,0.5,1)]",
            introReady ? "scale-100" : "scale-[1.14]"
          )}
        />
        <video
          ref={videoRef}
          autoPlay
          loop
          muted
          playsInline
          preload="auto"
          className={cn(
            "absolute inset-0 h-full w-full object-cover transition-opacity duration-[2400ms]",
            videoReady && !prefersReducedMotion ? "opacity-100" : "opacity-0"
          )}
        >
          <source src={IMG.heroVid} type="video/mp4" />
        </video>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(14,23,24,0.08),_rgba(5,9,12,0.78)_56%,_rgba(5,9,12,0.94)_100%)]" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,_rgba(2,7,10,0.12)_0%,_rgba(2,7,10,0.18)_28%,_rgba(2,7,10,0.72)_72%,_rgba(2,7,10,0.96)_100%)]" />
      </div>

      <HeroThreeField disabled={prefersReducedMotion || isLaunching} />
      <div className="landing-grid absolute inset-0 -z-10 opacity-55" />

      <div className="relative mx-auto flex min-h-[100svh] w-full max-w-screen-2xl flex-col px-6 pt-6 pb-8 md:px-10">
        <header className="flex items-center justify-between gap-4">
          <Link
            href="/"
            className="inline-flex shrink-0 items-center transition-opacity hover:opacity-90"
          >
            <GreenChainLogo
              variant="onDark"
              className="h-8 w-auto sm:h-9 md:h-10"
            />
          </Link>

          <nav className="hidden items-center gap-8 md:flex">
            {[
              ["#features", "Features"],
              ["#about", "About"],
            ].map(([href, label]) => (
              <a
                key={href}
                href={href}
                className="text-sm text-white/58 transition-colors hover:text-white"
              >
                {label}
              </a>
            ))}

            <DashboardLaunchButton
              onLaunch={onLaunchDashboard}
              disabled={isLaunching}
              className="landing-button landing-button--ghost inline-flex items-center gap-2 rounded-full border border-white/14 bg-white/8 px-5 py-2.5 text-sm text-white backdrop-blur-xl hover:border-white/28 hover:bg-white/14"
            >
              Launch Platform
              <span aria-hidden>→</span>
            </DashboardLaunchButton>
          </nav>
        </header>

        <div className="flex min-h-[calc(100svh-5rem)] flex-1 flex-col justify-center gap-12 py-12">
          <div className="max-w-[80rem]">
            <LineReveal
              lines={heroLines}
              active={mounted}
              className="max-w-[80rem]"
              lineClass="landing-display text-[clamp(3.35rem,8vw,7.85rem)] leading-[1] tracking-[-0.055em] text-white"
              delay={120}
            />

            <div {...fadeUp(520)}>
              <p className="mt-8 max-w-xl text-base leading-relaxed text-white/68 md:text-lg">
                GreenChain helps sourcing teams compare manufacturers,
                countries, and transport modes through an environmental lens,
                using open data and fast supplier research.
              </p>
            </div>

            <div
              {...fadeUp(680)}
              className="mt-10 flex flex-wrap items-center gap-4"
            >
              <DashboardLaunchButton
                onLaunch={onLaunchDashboard}
                disabled={isLaunching}
                className="landing-button landing-button--solid inline-flex items-center gap-2 rounded-full bg-primary px-7 py-3.5 text-sm font-medium text-[#04110a] hover:-translate-y-0.5"
              >
                Open Platform
                <span aria-hidden>→</span>
              </DashboardLaunchButton>

              <a
                href="#features"
                className="inline-flex items-center gap-2 text-sm text-white/62 transition-colors hover:text-white"
              >
                See the features
                <span aria-hidden>↓</span>
              </a>
            </div>
          </div>
        </div>

        <div
          {...fadeUp(840)}
          className="grid gap-4 border-t border-white/10 pt-6 md:grid-cols-3"
        >
          {HERO_SIGNALS.map((item) => (
            <div
              key={item.label}
              className="landing-panel rounded-[1.35rem] p-4"
            >
              <Eyebrow className="text-white/42">{item.label}</Eyebrow>
              <p className="mt-3 text-xl font-medium tracking-[-0.03em] text-white md:text-2xl">
                {item.value}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-white/58">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function FeatureCard({
  feature,
  delay = 0,
}: {
  feature: Feature
  delay?: number
}) {
  return (
    <Reveal delay={delay} className="h-full">
      <TiltCard className="landing-panel h-full overflow-hidden rounded-[1.8rem]">
        <div className="relative h-64 overflow-hidden border-b border-white/10 md:h-72">
          <ParallaxMedia
            src={feature.img}
            alt={feature.title}
            speed={0.08}
            sizes="(min-width: 1024px) 44vw, 100vw"
            className="h-full"
          />
          <div className="absolute inset-0 bg-[linear-gradient(180deg,_rgba(4,9,13,0)_0%,_rgba(4,9,13,0.08)_38%,_rgba(4,9,13,0.72)_100%)]" />
        </div>

        <div className="p-6 md:p-7">
          <Eyebrow className="text-primary/78">{feature.label}</Eyebrow>
          <h3 className="landing-display mt-4 text-3xl leading-[0.98] tracking-[-0.045em] text-white">
            {feature.title}
          </h3>
          <p className="mt-4 text-sm leading-relaxed text-white/62 md:text-base">
            {feature.body}
          </p>

          <div className="mt-6 grid gap-2">
            {feature.bullets.map((item) => (
              <div key={item} className="flex gap-3 text-sm text-white/60">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      </TiltCard>
    </Reveal>
  )
}

function FeaturesSection({
  isLaunching,
  onLaunchDashboard,
}: {
  isLaunching: boolean
  onLaunchDashboard: () => void
}) {
  return (
    <section id="features" className="px-6 py-24 md:px-10 md:py-32">
      <div className="mx-auto max-w-screen-xl">
        <Reveal className="max-w-3xl">
          <Eyebrow className="text-primary/82">What you get</Eyebrow>
          <h2 className="landing-display mt-4 text-4xl leading-[0.95] tracking-[-0.05em] text-white md:text-6xl">
            A fast way to compare sourcing options.
          </h2>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-white/62 md:text-lg">
            Input a product and destination, compare a few countries and
            shipping assumptions, then review a ranked recommendation.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-5 lg:grid-cols-3">
          {FEATURES.map((feature, index) => (
            <FeatureCard
              key={feature.label}
              feature={feature}
              delay={index * 80}
            />
          ))}
        </div>

        <Reveal delay={220} className="mt-12">
          <div className="landing-panel flex flex-col items-start justify-between gap-6 rounded-[2rem] border border-white/10 bg-black/16 p-8 md:flex-row md:items-center">
            <div className="max-w-xl">
              <p className="text-sm tracking-[0.3em] text-white/42 uppercase">
                Ready to try it?
              </p>
              <p className="mt-3 text-2xl font-medium tracking-[-0.04em] text-white md:text-3xl">
                Choose a CSV intake or continue into the demo dashboard.
              </p>
            </div>
            <DashboardLaunchButton
              onLaunch={onLaunchDashboard}
              disabled={isLaunching}
              className="landing-button landing-button--solid inline-flex items-center gap-2 rounded-full bg-primary px-7 py-3.5 text-sm font-medium text-[#04110a] hover:-translate-y-0.5"
            >
              Open launch options
              <span aria-hidden>→</span>
            </DashboardLaunchButton>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function Footer({
  isLaunching,
  onLaunchDashboard,
}: {
  isLaunching: boolean
  onLaunchDashboard: () => void
}) {
  return (
    <footer id="about" className="px-6 pt-4 pb-12 md:px-10">
      <div className="mx-auto flex max-w-screen-xl flex-col gap-8 border-t border-white/8 pt-8 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm tracking-[0.3em] text-white/42 uppercase">
            GreenChain
          </p>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-white/54">
            Compare sourcing options across manufacturers, countries, and
            transport modes through an environmental lens.
          </p>
        </div>

        <nav className="flex flex-wrap gap-x-8 gap-y-3 text-sm text-white/52">
          {[
            ["/launch", "Launch"],
            ["#platform", "Platform"],
            ["#capabilities", "Capabilities"],
            ["#about", "About"],
          ].map(([href, label]) =>
            href === "/launch" ? (
              <DashboardLaunchButton
                key={href}
                onLaunch={onLaunchDashboard}
                disabled={isLaunching}
                className="transition-colors hover:text-white"
              >
                {label}
              </DashboardLaunchButton>
            ) : (
              <a
                key={href}
                href={href}
                className="transition-colors hover:text-white"
              >
                {label}
              </a>
            )
          )}
        </nav>
      </div>
    </footer>
  )
}

export default function LandingPage() {
  const router = useRouter()
  const prefersReducedMotion = usePrefersReducedMotionSnapshot()
  const [isLaunching, setIsLaunching] = useState(false)
  const [launchOverlayRunId, setLaunchOverlayRunId] = useState(0)

  useEffect(() => {
    router.prefetch("/launch")
  }, [router])

  useEffect(() => {
    if (!isLaunching) return

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [isLaunching])

  const handleLaunchDashboard = useCallback(() => {
    if (isLaunching) return
    setLaunchOverlayRunId((currentRunId) => currentRunId + 1)
    setIsLaunching(true)
  }, [isLaunching])

  const handleLaunchOverlayComplete = useCallback(() => {
    router.push("/launch")
  }, [router])

  return (
    <main className="landing-page min-h-svh overflow-x-hidden text-foreground">
      <DashboardLaunchOverlay
        active={isLaunching}
        key={launchOverlayRunId}
        onComplete={handleLaunchOverlayComplete}
        reducedMotion={prefersReducedMotion}
      />
      <Hero
        introReady
        isLaunching={isLaunching}
        onLaunchDashboard={handleLaunchDashboard}
      />
      <FeaturesSection
        isLaunching={isLaunching}
        onLaunchDashboard={handleLaunchDashboard}
      />
      <Footer
        isLaunching={isLaunching}
        onLaunchDashboard={handleLaunchDashboard}
      />
    </main>
  )
}
