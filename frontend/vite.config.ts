import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Same file the backend reads, so the footer can never disagree with the
// API version or the backup manifest.  Read at build time — the Debian
// buildroot has no git history, so anything derived from `git describe`
// would silently produce an empty string there.
const version = readFileSync(
  fileURLToPath(new URL('../backend/app/VERSION', import.meta.url)),
  'utf-8',
).trim()

// https://vite.dev/config/
export default defineConfig({
  define: {
    __KANFEI_VERSION__: JSON.stringify(version),
  },
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
