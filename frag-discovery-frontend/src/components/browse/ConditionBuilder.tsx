import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useFiltersStore } from '@/stores/filters'
import type { AtLeastCondition, Condition, ConditionType, NoteCondition } from '@/lib/types'

const CONDITION_TYPES: Array<{ value: ConditionType; label: string }> = [
  { value: 'accord', label: 'Accord' },
  { value: 'top', label: 'Top Note' },
  { value: 'mid', label: 'Mid Note' },
  { value: 'base', label: 'Base Note' },
  { value: 'any_note', label: 'Any Note' },
  { value: 'at_least', label: 'At Least N Of' },
]

/** Text field that commits its value 300ms after typing stops. */
function DeferredInput({
  value,
  onCommit,
  placeholder,
  className,
}: {
  value: string
  onCommit: (v: string) => void
  placeholder?: string
  className?: string
}) {
  const [local, setLocal] = useState(value)
  const debounced = useDebouncedValue(local, 300)
  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    if (debounced !== value) onCommitRef.current(debounced)
  }, [debounced, value])
  return (
    <Input
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      placeholder={placeholder}
      className={className}
    />
  )
}

function ConditionRow({
  condition,
  onChange,
  onRemove,
}: {
  condition: Condition
  onChange: (c: Condition) => void
  onRemove: () => void
}) {
  const isAtLeast = condition.type === 'at_least'
  const initMin = condition.type !== 'at_least' ? (condition.min_pct ?? 0) : 0
  const initMax = condition.type !== 'at_least' ? (condition.max_pct ?? 100) : 100

  const [range, setRange] = useState<[number, number]>([initMin, initMax])
  const name = condition.type !== 'at_least' ? condition.name : ''
  const count = isAtLeast ? (condition as AtLeastCondition).count : 2
  const names = isAtLeast ? (condition as AtLeastCondition).names.join(', ') : ''

  const setType = (t: ConditionType) => {
    setRange([0, 100])
    if (t === 'at_least') {
      onChange({ type: 'at_least', count, names: (condition as AtLeastCondition)?.names ?? [] })
    } else {
      onChange({ type: t, name })
    }
  }

  const commitRange = ([lo, hi]: number[]) => {
    const [l, h] = [Math.min(lo, hi), Math.max(lo, hi)]
    setRange([l, h])
    const next: NoteCondition = {
      type: condition.type as NoteCondition['type'],
      name,
      ...(l > 0 ? { min_pct: l } : {}),
      ...(h < 100 ? { max_pct: h } : {}),
    }
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-1 rounded border border-border bg-background p-1.5">
      <div className="flex items-center gap-1">
        <Select value={condition.type} onValueChange={(v) => setType(v as ConditionType)}>
          <SelectTrigger className="h-7 w-[104px] shrink-0 text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CONDITION_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!isAtLeast && (
          <DeferredInput
            value={name}
            onCommit={(v) => onChange({ ...(condition as NoteCondition), name: v })}
            placeholder="e.g. vetiver"
            className="h-7 min-w-0 flex-1 text-xs"
          />
        )}
        <Button
          variant="ghost"
          size="sm"
          className="h-7 shrink-0 px-1.5 text-muted-foreground hover:text-love"
          onClick={onRemove}
          aria-label="Remove condition"
        >
          ×
        </Button>
      </div>

      {isAtLeast ? (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
            At least
            <Input
              type="number"
              min={1}
              max={20}
              value={count}
              onChange={(e) => {
                const c = Math.max(1, parseInt(e.target.value, 10) || 1)
                onChange({ type: 'at_least', count: c, names: (condition as AtLeastCondition).names })
              }}
              className="h-6 w-10 text-center text-[11px]"
            />
            of:
          </div>
          <DeferredInput
            value={names}
            onCommit={(v) =>
              onChange({
                type: 'at_least',
                count: (condition as AtLeastCondition).count,
                names: v.split(',').map((s) => s.trim()).filter(Boolean),
              })
            }
            placeholder="lavender, vetiver, vanilla..."
            className="h-7 w-full text-[11px]"
          />
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <Slider
            value={range}
            min={0}
            max={100}
            step={1}
            onValueChange={(v) => setRange([v[0] ?? 0, v[1] ?? 100])}
            onValueCommit={(v) => commitRange(v)}
          />
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>{range[0]}%</span>
            <span>{range[1] < 100 ? `${range[1]}%` : '100%'}</span>
          </div>
        </div>
      )}
    </div>
  )
}

export function ConditionBuilder() {
  const conditions = useFiltersStore((s) => s.conditions)
  const setCondition = useFiltersStore((s) => s.setCondition)
  const addCondition = useFiltersStore((s) => s.addCondition)
  const removeCondition = useFiltersStore((s) => s.removeCondition)

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-col gap-1.5">
        {conditions.map((c, i) => (
          <ConditionRow
            key={c.id ?? i}
            condition={c}
            onChange={(next) => setCondition(i, next)}
            onRemove={() => removeCondition(i)}
          />
        ))}
      </div>
      <Button
        variant="outline"
        size="sm"
        className="w-full border-dashed text-muted-foreground hover:border-primary hover:text-primary"
        onClick={() => addCondition()}
      >
        + Add Condition
      </Button>
    </div>
  )
}
