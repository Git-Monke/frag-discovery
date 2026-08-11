import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useFiltersStore } from '@/stores/filters'
import { fmt } from '@/lib/utils'

export function PageNav({
  total,
  pages,
}: {
  total: number
  pages: number
}) {
  const f = useFiltersStore()
  const page = Math.min(f.page, Math.max(pages, 1))

  const go = (p: number) => {
    const clamped = Math.min(Math.max(p, 1), Math.max(pages, 1))
    f.set({ page: clamped })
  }

  return (
    <div className="flex h-10 shrink-0 items-center gap-1 border-t border-border bg-card px-3 text-xs text-muted-foreground">
      <span className="mr-2">{fmt(total)} results</span>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs"
        disabled={page <= 1}
        onClick={() => go(1)}
      >
        « First
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs"
        disabled={page <= 1}
        onClick={() => go(page - 1)}
      >
        <ChevronLeft className="size-3.5" /> Prev
      </Button>
      <span className="px-2 text-muted-foreground">
        Page <span className="font-semibold text-foreground">{page}</span> of {fmt(Math.max(pages, 1))}
      </span>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs"
        disabled={page >= pages}
        onClick={() => go(page + 1)}
      >
        Next <ChevronRight className="size-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs"
        disabled={page >= pages}
        onClick={() => go(pages)}
      >
        Last »
      </Button>
      <div className="ml-auto flex items-center gap-1.5">
        <span>Per page</span>
        <Select
          value={String(f.pageSize)}
          onValueChange={(v) => f.set({ pageSize: parseInt(v, 10), page: 1 })}
        >
          <SelectTrigger className="h-6 w-[70px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[25, 50, 100].map((n) => (
              <SelectItem key={n} value={String(n)}>{n}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
