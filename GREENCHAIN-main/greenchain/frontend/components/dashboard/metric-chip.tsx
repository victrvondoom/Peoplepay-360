import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface MetricChipProps {
  label: string
  value: string
  delta?: string
  className?: string
}

export function MetricChip({
  label,
  value,
  delta,
  className,
}: MetricChipProps) {
  return (
    <div
      className={cn(
        "panel-glow flex min-w-0 flex-col gap-2 rounded-2xl border border-border/80 bg-card/80 px-3 py-3",
        className
      )}
    >
      <span className="eyebrow">{label}</span>
      <div className="flex items-end justify-between gap-3">
        <span className="text-lg font-medium tracking-tight text-foreground">
          {value}
        </span>
        {delta ? (
          <Badge variant="secondary" className="rounded-full px-2.5 py-0.5">
            {delta}
          </Badge>
        ) : null}
      </div>
    </div>
  )
}
