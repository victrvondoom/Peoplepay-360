"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"

function RouteTransition({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    let nextFrame = 0
    const frame = window.requestAnimationFrame(() => {
      nextFrame = window.requestAnimationFrame(() => {
        setIsVisible(true)
      })
    })

    return () => {
      window.cancelAnimationFrame(frame)
      window.cancelAnimationFrame(nextFrame)
    }
  }, [])

  return (
    <div className={`app-route-transition${isVisible ? " is-visible" : ""}`}>
      <div aria-hidden className="app-route-transition__veil" />
      <div className="app-route-transition__content">{children}</div>
    </div>
  )
}

export default function Template({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const pathname = usePathname()

  if (pathname === "/" || pathname === "/launch") {
    return children
  }

  return <RouteTransition key={pathname}>{children}</RouteTransition>
}
