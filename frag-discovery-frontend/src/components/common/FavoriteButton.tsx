import { useNavigate } from 'react-router-dom'
import { useFavoriteToggle } from '@/hooks/queries'
import { useAuthStore } from '@/stores/auth'
import { cn } from '@/lib/utils'

interface FavoriteButtonProps {
  id: number
  favorited?: boolean
  /** 'toggle' = card/detail style, 'list' = table row style. */
  variant?: 'toggle' | 'list'
  className?: string
  title?: string
}

export function FavoriteButton({ id, favorited = false, variant = 'toggle', className, title }: FavoriteButtonProps) {
  const toggle = useFavoriteToggle()
  const status = useAuthStore((s) => s.status)
  const navigate = useNavigate()
  const on = !!favorited
  const label = on ? 'Remove from favorites' : 'Add to favorites'
  return (
    <button
      type="button"
      aria-label={label}
      title={title ?? label}
      className={
        cn(
          'cursor-pointer leading-none transition-colors',
          variant === 'toggle'
            ? 'flex size-6 items-center justify-center rounded border border-transparent text-base text-muted-foreground hover:border-border hover:text-primary'
            : 'text-sm text-muted-foreground hover:text-primary',
          on && 'text-primary hover:text-primary',
          className,
        )
      }
      onClick={(e) => {
        e.stopPropagation()
        // Favoriting is tied to an account — send signed-out users to sign in.
        if (status !== 'authenticated') {
          navigate('/account')
          return
        }
        // `on` here is the TARGET state: turn the favorite on/off.
        toggle.mutate({ id, on: !on })
      }}
    >
      {on ? '★' : '☆'}
    </button>
  )
}
