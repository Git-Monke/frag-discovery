import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Header } from '@/components/layout/Header'
import { useNotes } from '@/hooks/queries'
import { useUIStore } from '@/stores/ui'

export default function AppLayout() {
  const { data: notes } = useNotes()
  const setNoteImages = useUIStore((s) => s.setNoteImages)

  // Populate the note→image map used by the detail note pyramid once.
  useEffect(() => {
    if (notes) setNoteImages(notes)
  }, [notes, setNoteImages])

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Header />
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  )
}
