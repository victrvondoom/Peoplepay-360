"use client"

import {
  type ComponentProps,
  type ReactNode,
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react"
import * as ResizablePrimitive from "react-resizable-panels"

import { cn } from "@/lib/utils"

function ResizablePanelGroup({
  className,
  ...props
}: ComponentProps<typeof ResizablePrimitive.Group>) {
  return (
    <ResizablePrimitive.Group
      data-slot="resizable-panel-group"
      className={cn(
        "flex h-full w-full aria-[orientation=vertical]:flex-col",
        className
      )}
      {...props}
    />
  )
}

function ResizablePanel({
  ...props
}: ComponentProps<typeof ResizablePrimitive.Panel>) {
  return <ResizablePrimitive.Panel data-slot="resizable-panel" {...props} />
}

function ResizableHandle({
  children,
  withHandle,
  className,
  ...props
}: ComponentProps<typeof ResizablePrimitive.Separator> & {
  withHandle?: boolean
}) {
  return (
    <ResizablePrimitive.Separator
      data-slot="resizable-handle"
      className={cn(
        "relative z-10 flex w-px items-center justify-center overflow-visible bg-border ring-offset-background after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-hidden aria-[orientation=horizontal]:h-px aria-[orientation=horizontal]:w-full aria-[orientation=horizontal]:after:left-0 aria-[orientation=horizontal]:after:h-1 aria-[orientation=horizontal]:after:w-full aria-[orientation=horizontal]:after:translate-x-0 aria-[orientation=horizontal]:after:-translate-y-1/2",
        className
      )}
      {...props}
    >
      {children ??
        (withHandle ? (
          <div className="z-10 flex h-6 w-1 shrink-0 rounded-lg bg-border" />
        ) : null)}
    </ResizablePrimitive.Separator>
  )
}

function LaggedHandleVisual({
  active,
  introDelayMs = 0,
  orientation,
}: {
  active: boolean
  introDelayMs?: number
  orientation: "horizontal" | "vertical"
}) {
  const [isRevealed, setIsRevealed] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")
    const revealDelayMs = mediaQuery.matches ? 0 : introDelayMs

    let timeoutId: number | null = null
    const frameId = window.requestAnimationFrame(() => {
      timeoutId = window.setTimeout(() => {
        setIsRevealed(true)
      }, revealDelayMs)
    })

    return () => {
      window.cancelAnimationFrame(frameId)

      if (timeoutId !== null) {
        window.clearTimeout(timeoutId)
      }
    }
  }, [introDelayMs])

  const revealOpacity = isRevealed ? 1 : 0
  const revealFilter = isRevealed ? "blur(0px)" : "blur(4px)"

  if (orientation === "vertical") {
    const width = 24
    const height = active ? 110 : 82

    return (
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 left-1/2 block"
        style={{
          filter: revealFilter,
          height,
          opacity: revealOpacity,
          transform: `translate(-50%, -50%) scaleX(${isRevealed ? 1 : 0.72}) scaleY(${isRevealed ? 1 : 0.56})`,
          transition:
            "transform 720ms cubic-bezier(0.22, 1, 0.36, 1), opacity 520ms ease, filter 720ms cubic-bezier(0.22, 1, 0.36, 1)",
          willChange: isRevealed ? undefined : "transform, opacity, filter",
          width,
        }}
      >
        <span
          className="absolute inset-y-2 rounded-full transition-[left,width,opacity,filter,background-color] duration-150"
          style={{
            left: "50%",
            background: active
              ? "rgba(255,255,255,0.14)"
              : "rgba(255,255,255,0.08)",
            filter: `blur(${active ? 8 : 7}px)`,
            opacity: active ? 0.8 : 0.56,
            transform: "translateX(-50%)",
            width: active ? 8 : 7,
          }}
        />
        <span
          className="absolute inset-y-1 rounded-full transition-[width,background-color,box-shadow] duration-150"
          style={{
            left: "50%",
            background: active
              ? "rgba(255,255,255,0.05)"
              : "rgba(255,255,255,0.03)",
            boxShadow: active
              ? "0 0 10px rgba(255,255,255,0.04)"
              : "0 0 8px rgba(255,255,255,0.02)",
            transform: "translateX(-50%)",
            width: active ? 4 : 3,
          }}
        />
        <span
          className="absolute inset-y-1 rounded-full transition-[left,width,background-color,box-shadow] duration-150"
          style={{
            left: "50%",
            background: active
              ? "rgba(255,255,255,0.34)"
              : "rgba(255,255,255,0.22)",
            boxShadow: active
              ? "0 0 10px rgba(255,255,255,0.14)"
              : "0 0 8px rgba(255,255,255,0.08)",
            transform: "translateX(-50%)",
            width: active ? 3 : 2.5,
          }}
        />
      </span>
    )
  }

  const width = active ? 110 : 82
  const height = 24

  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute top-1/2 left-1/2 block"
      style={{
        filter: revealFilter,
        height,
        opacity: revealOpacity,
        transform: `translate(-50%, -50%) scaleX(${isRevealed ? 1 : 0.56}) scaleY(${isRevealed ? 1 : 0.72})`,
        transition:
          "transform 720ms cubic-bezier(0.22, 1, 0.36, 1), opacity 520ms ease, filter 720ms cubic-bezier(0.22, 1, 0.36, 1)",
        willChange: isRevealed ? undefined : "transform, opacity, filter",
        width,
      }}
    >
      <span
        className="absolute inset-x-2 rounded-full transition-[top,height,opacity,filter,background-color] duration-150"
        style={{
          top: "50%",
          background: active
            ? "rgba(255,255,255,0.14)"
            : "rgba(255,255,255,0.08)",
          filter: `blur(${active ? 8 : 7}px)`,
          height: active ? 8 : 7,
          opacity: active ? 0.8 : 0.56,
          transform: "translateY(-50%)",
        }}
      />
      <span
        className="absolute inset-x-1 rounded-full transition-[height,background-color,box-shadow] duration-150"
        style={{
          top: "50%",
          background: active
            ? "rgba(255,255,255,0.05)"
            : "rgba(255,255,255,0.03)",
          boxShadow: active
            ? "0 0 10px rgba(255,255,255,0.04)"
            : "0 0 8px rgba(255,255,255,0.02)",
          height: active ? 4 : 3,
          transform: "translateY(-50%)",
        }}
      />
      <span
        className="absolute inset-x-1 rounded-full transition-[top,height,background-color,box-shadow] duration-150"
        style={{
          top: "50%",
          background: active
            ? "rgba(255,255,255,0.34)"
            : "rgba(255,255,255,0.22)",
          boxShadow: active
            ? "0 0 10px rgba(255,255,255,0.14)"
            : "0 0 8px rgba(255,255,255,0.08)",
          height: active ? 3 : 2.5,
          transform: "translateY(-50%)",
        }}
      />
    </span>
  )
}

function LaggedPanelShell({
  children,
  className,
  edge,
  lagOffset,
  orientation,
}: {
  children: ReactNode
  className?: string
  edge: "leading" | "trailing"
  lagOffset: number
  orientation: "horizontal" | "vertical"
}) {
  const MAX_SPLIT_REVEAL_PX = 10
  const SHADOW_SIZE_PX = 24
  const splitReveal = Math.min(MAX_SPLIT_REVEAL_PX, Math.abs(lagOffset))
  const edgeInset = splitReveal / 2
  const clipInsets =
    orientation === "vertical"
      ? edge === "trailing"
        ? { bottom: 0, left: 0, right: edgeInset, top: 0 }
        : { bottom: 0, left: edgeInset, right: 0, top: 0 }
      : edge === "trailing"
        ? { bottom: edgeInset, left: 0, right: 0, top: 0 }
        : { bottom: 0, left: 0, right: 0, top: edgeInset }
  const clipPath = `inset(${clipInsets.top}px ${clipInsets.right}px ${clipInsets.bottom}px ${clipInsets.left}px)`
  const shadowOpacity =
    edgeInset <= 0.05
      ? 0
      : Math.min(0.14, 0.04 + (edgeInset / (MAX_SPLIT_REVEAL_PX / 2)) * 0.08)
  const shadowStyle =
    orientation === "vertical"
      ? edge === "trailing"
        ? {
            background:
              "linear-gradient(to left, rgba(4, 8, 12, 0.22), rgba(4, 8, 12, 0))",
            bottom: 0,
            right: `${edgeInset}px`,
            top: 0,
            width: SHADOW_SIZE_PX,
          }
        : {
            background:
              "linear-gradient(to right, rgba(4, 8, 12, 0.22), rgba(4, 8, 12, 0))",
            bottom: 0,
            left: `${edgeInset}px`,
            top: 0,
            width: SHADOW_SIZE_PX,
          }
      : edge === "trailing"
        ? {
            background:
              "linear-gradient(to top, rgba(4, 8, 12, 0.2), rgba(4, 8, 12, 0))",
            bottom: `${edgeInset}px`,
            height: SHADOW_SIZE_PX,
            left: 0,
            right: 0,
          }
        : {
            background:
              "linear-gradient(to bottom, rgba(4, 8, 12, 0.2), rgba(4, 8, 12, 0))",
            height: SHADOW_SIZE_PX,
            left: 0,
            right: 0,
            top: `${edgeInset}px`,
          }

  return (
    <div
      className={cn(
        "relative h-full min-h-0 w-full overflow-visible",
        className
      )}
    >
      <div className="pointer-events-none absolute inset-0 overflow-visible">
        <div
          className="pointer-events-auto absolute inset-0 min-h-0 overflow-visible"
          style={{
            WebkitClipPath: clipPath,
            clipPath,
            willChange: edgeInset > 0.05 ? "clip-path" : undefined,
          }}
        >
          <div className="h-full min-h-0 w-full">{children}</div>
          {edgeInset > 0.05 ? (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute z-10"
              style={{
                ...shadowStyle,
                opacity: shadowOpacity,
              }}
            />
          ) : null}
        </div>
      </div>
    </div>
  )
}

function useResizeMotion(containerRef: RefObject<HTMLElement | null>) {
  const MAX_VISUAL_LAG_PX = 10
  const RELEASE_SETTLE_MS = 180
  const [position, setPosition] = useState<{ x: number; y: number } | null>(
    null
  )
  const [targetPosition, setTargetPosition] = useState<{
    x: number
    y: number
  } | null>(null)
  const [active, setActive] = useState(false)
  const animationFrameRef = useRef<number | null>(null)
  const releaseTimeoutRef = useRef<number | null>(null)
  const removePointerListenersRef = useRef<(() => void) | null>(null)
  const animateRef = useRef<() => void>(() => {})
  const currentRef = useRef<{ x: number; y: number } | null>(null)
  const targetRef = useRef<{ x: number; y: number } | null>(null)

  const animate = useCallback(() => {
    const current = currentRef.current
    const target = targetRef.current

    if (!current || !target) {
      animationFrameRef.current = null
      return
    }

    const deltaX = target.x - current.x
    const deltaY = target.y - current.y
    const nextPosition =
      Math.abs(deltaX) < 0.35 && Math.abs(deltaY) < 0.35
        ? target
        : {
            x: current.x + deltaX * 0.12,
            y: current.y + deltaY * 0.12,
          }
    const clampedPosition = {
      x: Math.min(
        target.x + MAX_VISUAL_LAG_PX,
        Math.max(target.x - MAX_VISUAL_LAG_PX, nextPosition.x)
      ),
      y: Math.min(
        target.y + MAX_VISUAL_LAG_PX,
        Math.max(target.y - MAX_VISUAL_LAG_PX, nextPosition.y)
      ),
    }

    currentRef.current = clampedPosition
    setPosition(clampedPosition)

    if (
      Math.abs(target.x - clampedPosition.x) >= 0.35 ||
      Math.abs(target.y - clampedPosition.y) >= 0.35
    ) {
      animationFrameRef.current = window.requestAnimationFrame(() => {
        animateRef.current()
      })
      return
    }

    animationFrameRef.current = null
  }, [])

  useEffect(() => {
    animateRef.current = animate
  }, [animate])

  const clearReleaseTimeout = useCallback(() => {
    if (releaseTimeoutRef.current !== null) {
      window.clearTimeout(releaseTimeoutRef.current)
      releaseTimeoutRef.current = null
    }
  }, [])

  const stopActive = useCallback(() => {
    removePointerListenersRef.current?.()
    removePointerListenersRef.current = null
    clearReleaseTimeout()

    releaseTimeoutRef.current = window.setTimeout(() => {
      releaseTimeoutRef.current = null
      setActive(false)
    }, RELEASE_SETTLE_MS)
  }, [RELEASE_SETTLE_MS, clearReleaseTimeout])

  const measure = useCallback(() => {
    const container = containerRef.current

    if (!container) {
      return
    }

    const handle = container.querySelector(
      "[data-group] > [data-slot='resizable-handle']"
    ) as HTMLElement | null

    if (!handle) {
      return
    }

    const containerBounds = container.getBoundingClientRect()
    const handleBounds = handle.getBoundingClientRect()
    const nextTarget = {
      x: handleBounds.left - containerBounds.left + handleBounds.width / 2,
      y: handleBounds.top - containerBounds.top + handleBounds.height / 2,
    }

    targetRef.current = nextTarget
    setTargetPosition(nextTarget)

    if (!currentRef.current) {
      currentRef.current = nextTarget
      setPosition(nextTarget)
      return
    }

    if (animationFrameRef.current === null) {
      animationFrameRef.current = window.requestAnimationFrame(animate)
    }
  }, [animate, containerRef])

  const startActive = useCallback(() => {
    removePointerListenersRef.current?.()
    removePointerListenersRef.current = null
    clearReleaseTimeout()
    setActive(true)
    measure()

    const handlePointerEnd = () => {
      stopActive()
    }

    window.addEventListener("pointerup", handlePointerEnd)
    window.addEventListener("pointercancel", handlePointerEnd)
    window.addEventListener("blur", handlePointerEnd)

    removePointerListenersRef.current = () => {
      window.removeEventListener("pointerup", handlePointerEnd)
      window.removeEventListener("pointercancel", handlePointerEnd)
      window.removeEventListener("blur", handlePointerEnd)
    }
  }, [clearReleaseTimeout, measure, stopActive])

  useEffect(() => {
    const frameId = window.requestAnimationFrame(measure)

    return () => window.cancelAnimationFrame(frameId)
  }, [measure])

  useEffect(() => {
    const container = containerRef.current

    if (!container) {
      return
    }

    const observer = new ResizeObserver(() => {
      measure()
    })

    observer.observe(container)
    window.addEventListener("resize", measure)

    return () => {
      observer.disconnect()
      window.removeEventListener("resize", measure)
    }
  }, [containerRef, measure])

  useEffect(() => {
    return () => {
      removePointerListenersRef.current?.()
      clearReleaseTimeout()

      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [clearReleaseTimeout])

  return {
    active,
    lagOffset:
      position && targetPosition
        ? {
            x: position.x - targetPosition.x,
            y: position.y - targetPosition.y,
          }
        : { x: 0, y: 0 },
    measure,
    onHandlePointerDownCapture: startActive,
    position,
    targetPosition,
  }
}

export {
  LaggedPanelShell,
  LaggedHandleVisual,
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
  useResizeMotion,
}
