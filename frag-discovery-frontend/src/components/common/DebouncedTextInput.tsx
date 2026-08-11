import { useEffect, useRef, useState, type InputHTMLAttributes } from 'react'
import { Input } from '@/components/ui/input'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'

interface DebouncedTextInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> {
  value: string
  /** Called with the debounced value (300ms after typing stops). */
  onCommit: (value: string) => void
  delay?: number
}

/**
 * Input with instant typing feedback whose committed value is debounced —
 * mirrors the old app's `input → debounce(triggerSearch)` behavior.
 *
 * The input is *semi-controlled*: it keeps a live `local` buffer for typing,
 * pushes the settled value to the store via `onCommit`, and adopts external
 * changes (reset, navigation, or another input writing the same store field)
 * into `local`. The important contract is that `onCommit` fires ONLY as a
 * result of a real edit in THIS input — never because the `value` prop changed
 * externally. That is what makes multiple inputs safe to bind to one store
 * field: two search boxes sharing `q` each debounce independently, but an
 * server-echo from one never triggers a stale commit in the other.
 */
export function DebouncedTextInput({ value, onCommit, delay = 300, ...props }: DebouncedTextInputProps) {
  const [local, setLocal] = useState(value)
  const debounced = useDebouncedValue(local, delay)
  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit

  // The most recent value this input has sent (or adopted) from the store.
  // Used for idempotency so an echoed value is never pushed back.
  const committedRef = useRef(value)

  // External change (reset, navigation, the other search input fixing `q`):
  // adopt the value into our buffer and re-baseline so we don't push it back.
  // Runs only on `value` changes — never on typing, or we'd wipe the buffer.
  useEffect(() => {
    if (value !== local) setLocal(value)
    committedRef.current = value
    // The `local` read here is the one captured at the render where `value`
    // changed, which is exactly the current buffer to compare against.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  // Local edit that has settled (debounced) and is still the live buffer, and
  // differs from both the store and what we last sent → commit it.
  useEffect(() => {
    if (local === debounced && debounced !== committedRef.current) {
      committedRef.current = debounced
      onCommitRef.current(debounced)
    }
  }, [debounced, local])

  return (
    <Input
      {...props}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
    />
  )
}