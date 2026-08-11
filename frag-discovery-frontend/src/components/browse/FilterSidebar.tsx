import type { ReactNode } from 'react'
import { ConditionBuilder } from '@/components/browse/ConditionBuilder'
import { DebouncedTextInput } from '@/components/common/DebouncedTextInput'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useStats } from '@/hooks/queries'
import { useFiltersStore } from '@/stores/filters'
import type { Gender, Longevity, Season, Sillage } from '@/lib/types'

const ANY = '__any__'

const LONGEVITY_OPTIONS: Array<{ value: Longevity; label: string }> = [
  { value: 'very_weak', label: 'Very Weak' },
  { value: 'weak', label: 'Weak' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'long_lasting', label: 'Long Lasting' },
  { value: 'eternal', label: 'Eternal' },
]

const SILLAGE_OPTIONS: Array<{ value: Sillage; label: string }> = [
  { value: 'intimate', label: 'Intimate' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'strong', label: 'Strong' },
  { value: 'enormous', label: 'Enormous' },
]

const SEASON_OPTIONS: Array<{ value: Season; label: string }> = [
  { value: 'hot', label: 'Hot' },
  { value: 'cold', label: 'Cold' },
  { value: 'universal', label: 'Universal' },
  { value: 'spring', label: 'Spring' },
  { value: 'summer', label: 'Summer' },
  { value: 'fall', label: 'Fall' },
  { value: 'winter', label: 'Winter' },
]

const GENDER_OPTIONS: Array<{ value: Gender; label: string }> = [
  { value: 'female', label: 'Feminine' },
  { value: 'more_female', label: 'More Feminine' },
  { value: 'female_wearable', label: 'Feminine Wearable' },
  { value: 'unisex', label: 'Unisex' },
  { value: 'male_wearable', label: 'Masculine Wearable' },
  { value: 'more_male', label: 'More Masculine' },
  { value: 'male', label: 'Masculine' },
]

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <div className="mt-3 mb-1 first:mt-0 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
      {children}
    </div>
  )
}

function MinMaxRow({
  minValue, maxValue,
  onMin, onMax,
}: {
  minValue: string
  maxValue: string
  onMin: (v: string) => void
  onMax: (v: string) => void
}) {
  return (
    <div className="flex items-center gap-1.5">
      <DebouncedTextInput
        type="number"
        value={minValue}
        onCommit={onMin}
        placeholder="Min"
        className="h-7 text-xs"
      />
      <span className="text-muted-foreground">–</span>
      <DebouncedTextInput
        type="number"
        value={maxValue}
        onCommit={onMax}
        placeholder="Max"
        className="h-7 text-xs"
      />
    </div>
  )
}

export function FilterSidebar() {
  const f = useFiltersStore()
  const { data: stats } = useStats()

  return (
    <aside className="flex flex-col gap-1 overflow-y-auto border-r border-border bg-card p-3">
      <SectionTitle>Search</SectionTitle>
      <DebouncedTextInput
        value={f.q}
        onCommit={(v) => f.set({ q: v }, true)}
        placeholder="Name or brand…"
        className="h-7 text-xs"
      />

      <SectionTitle>Brand</SectionTitle>
      {/* 8k+ brands: a native <select> is browser-virtualized (the old app did
          exactly this); a Radix Select with 8k items freezes on open. */}
      <select
        value={f.brand || ANY}
        onChange={(e) => f.set({ brand: e.target.value === ANY ? '' : e.target.value }, true)}
        className="h-7 w-full rounded-lg border border-input bg-background px-2.5 text-xs outline-none focus-visible:border-ring [&>option]:bg-popover [&>option]:text-popover-foreground"
      >
        <option value={ANY}>All brands</option>
        {stats?.brand_list.map((b) => (
          <option key={b} value={b}>{b}</option>
        ))}
      </select>

      <SectionTitle>Year</SectionTitle>
      <MinMaxRow
        minValue={f.yearMin}
        maxValue={f.yearMax}
        onMin={(v) => f.set({ yearMin: v }, true)}
        onMax={(v) => f.set({ yearMax: v }, true)}
      />

      <SectionTitle>Rating</SectionTitle>
      <MinMaxRow
        minValue={f.ratingMin}
        maxValue={f.ratingMax}
        onMin={(v) => f.set({ ratingMin: v }, true)}
        onMax={(v) => f.set({ ratingMax: v }, true)}
      />

      <SectionTitle>Votes</SectionTitle>
      <MinMaxRow
        minValue={f.votesMin}
        maxValue={f.votesMax}
        onMin={(v) => f.set({ votesMin: v }, true)}
        onMax={(v) => f.set({ votesMax: v }, true)}
      />

      <label className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Checkbox
          checked={f.available}
          onCheckedChange={(c) => f.set({ available: !!c }, true)}
        />
        Confirmed available only
      </label>

      <SectionTitle>Longevity</SectionTitle>
      <div className="flex flex-col gap-1.5">
        <Select
          value={f.longevity || ANY}
          onValueChange={(v) => f.set({ longevity: v === ANY ? '' : (v as Longevity) }, true)}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {LONGEVITY_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Checkbox
            checked={f.longevityMin}
            onCheckedChange={(c) => f.set({ longevityMin: !!c }, true)}
          />
          Or better
        </label>
      </div>

      <SectionTitle>Sillage</SectionTitle>
      <div className="flex flex-col gap-1.5">
        <Select
          value={f.sillage || ANY}
          onValueChange={(v) => f.set({ sillage: v === ANY ? '' : (v as Sillage) }, true)}
        >
          <SelectTrigger className="h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {SILLAGE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Checkbox
            checked={f.sillageMin}
            onCheckedChange={(c) => f.set({ sillageMin: !!c }, true)}
          />
          Or better
        </label>
      </div>

      <SectionTitle>Season</SectionTitle>
      <Select
        value={f.season || ANY}
        onValueChange={(v) => f.set({ season: v === ANY ? '' : (v as Season) }, true)}
      >
        <SelectTrigger className="h-7 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {SEASON_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <SectionTitle>Gender</SectionTitle>
      <Select
        value={f.gender || ANY}
        onValueChange={(v) => f.set({ gender: v === ANY ? '' : (v as Gender) }, true)}
      >
        <SelectTrigger className="h-7 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {GENDER_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <SectionTitle>Conditions</SectionTitle>
      <ConditionBuilder />

      <Button
        variant="ghost"
        size="sm"
        className="mt-3 w-full border border-border text-muted-foreground hover:text-foreground"
        onClick={() => f.reset()}
      >
        Reset filters
      </Button>
    </aside>
  )
}
