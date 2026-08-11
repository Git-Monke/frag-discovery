import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Google auth → new FastAPI backend on :8000 (regex key so it wins over
      // the broader /api rule below, which Vite doesn't sort reliably).
      '^/api/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Per-user data endpoints (favorites, feedback, recommend, fragrance
      // detail) → the new per-user backend on :8000. Keys are regex-tested in
      // insertion order, so these win over the /api fallback below.
      '^/api/(favorites|recommend|feedback|fragrance)': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Everything else (search, stats, notes, ingredient-stats) → reference
      // Flask backend (python app.py) on 3232, until the browse swap lands.
      '/api': {
        target: 'http://localhost:3232',
        changeOrigin: true,
      },
    },
  },
})
