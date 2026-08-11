import type { NoteItem } from '@/lib/types'
import { useUIStore } from '@/stores/ui'

function NoteLayer({ label, notes }: { label: string; notes: NoteItem[] }) {
  const noteImages = useUIStore((s) => s.noteImages)
  if (!notes.length) return null
  const sorted = notes.slice().sort((a, b) => (b.strength_pct ?? 0) - (a.strength_pct ?? 0))
  return (
    <div className="mb-2.5">
      <div className="mb-1.5 text-[10px] tracking-wider text-muted-foreground uppercase">{label}</div>
      <div className="flex flex-wrap gap-2">
        {sorted.map((n) => {
          const img = noteImages?.[n.name]
          const pct = n.strength_pct != null ? n.strength_pct : 100
          const scale = 0.5 + pct / 200
          const imgSize = Math.round(52 * scale)
          return (
            <div key={n.name} className="flex w-[64px] flex-col items-center gap-0.5">
              <div className="flex h-14 items-center justify-center">
                {img ? (
                  <img
                    src={img}
                    alt={n.name}
                    style={{ width: imgSize, height: imgSize, opacity: scale }}
                    loading="lazy"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                ) : null}
              </div>
              <span className="max-w-full truncate text-[10px] text-foreground">{n.name}</span>
              <span className="text-[9px] text-muted-foreground">
                {n.strength_pct != null ? `${Math.round(n.strength_pct)}%` : ''}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function NotePyramid({
  top, middle, base,
}: {
  top: NoteItem[]
  middle: NoteItem[]
  base: NoteItem[]
}) {
  return (
    <div>
      <NoteLayer label="Top" notes={top} />
      <NoteLayer label="Middle" notes={middle} />
      <NoteLayer label="Base" notes={base} />
    </div>
  )
}
