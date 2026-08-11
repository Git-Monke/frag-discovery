import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface BarRowProps {
  label: string
  value?: number | null
  total: number
  /** Tailwind bg-* class for the fill. */
  colorClass?: string
  labelClass?: string
}

export function BarRow({ label, value, total, colorClass = 'bg-primary/60', labelClass }: BarRowProps) {
  const pct = total > 0 ? Math.round(((value || 0) / total) * 100) : 0
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className={cn('min-w-[84px] text-right text-muted-foreground', labelClass)}>{label}</span>
      <div className="h-[6px] flex-1 overflow-hidden rounded bg-muted">
        <div className={cn('h-full rounded', colorClass)} style={{ width: `${pct}%` }} />
      </div>
      <span className="min-w-[30px] text-[10px] text-muted-foreground">{pct}%</span>
    </div>
  )
}

interface BarChartProps {
  children: ReactNode
  className?: string
}

export function BarChart({ children, className }: BarChartProps) {
  return <div className={cn('flex flex-col gap-1.5', className)}>{children}</div>
}
