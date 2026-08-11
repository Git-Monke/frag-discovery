import { useState, type ImgHTMLAttributes, type ReactNode } from 'react'

interface ImageWithFallbackProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  src?: string | null
  fallback?: ReactNode
}

/**
 * Image that swaps to `fallback` when the src fails to load (or is missing) —
 * replaces the old app's inline onerror handlers.
 */
export function ImageWithFallback({ src, fallback, onError, ...props }: ImageWithFallbackProps) {
  const [failed, setFailed] = useState(false)
  if (failed || !src) return <>{fallback ?? null}</>
  return (
    <img
      {...props}
      src={src}
      onError={(e) => {
        setFailed(true)
        onError?.(e)
      }}
    />
  )
}
