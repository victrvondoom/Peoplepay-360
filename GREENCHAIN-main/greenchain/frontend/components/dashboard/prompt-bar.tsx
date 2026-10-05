"use client"

import { type ComponentProps, type FormEvent, useRef } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Message02Icon } from "@hugeicons/core-free-icons"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface PromptBarProps extends ComponentProps<"div"> {
  error?: string | null
  onSubmit: () => void
  onValueChange: (value: string) => void
  pending?: boolean
  placeholder?: string
  value: string
}

export function PromptBar({
  className,
  error,
  onSubmit,
  onValueChange,
  pending = false,
  placeholder,
  value,
  ...props
}: PromptBarProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!pending && value.trim()) {
      onSubmit()
      inputRef.current?.blur()
    }
  }

  return (
    <div
      className={cn(
        "rounded-2xl border border-white/8 bg-black/24 p-2 backdrop-blur-sm",
        className
      )}
      {...props}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Input
            ref={inputRef}
            name="scenario-prompt"
            data-kimi-prompt-input="true"
            value={value}
            onChange={(event) => onValueChange(event.target.value)}
            placeholder={placeholder ?? "Describe the scenario edit you want to apply"}
            className="h-11 flex-1 rounded-xl border-white/8 bg-black/22 shadow-none"
            disabled={pending}
          />
          <Button
            type="submit"
            size="default"
            className="shrink-0 rounded-xl shadow-none"
            disabled={pending || !value.trim()}
          >
            <HugeiconsIcon
              icon={Message02Icon}
              strokeWidth={2}
              data-icon="inline-start"
            />
            {pending ? "Applying..." : "Submit"}
          </Button>
        </div>
        {error ? <p className="px-1 text-xs text-red-300/80">{error}</p> : null}
      </form>
    </div>
  )
}
