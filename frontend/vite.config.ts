import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// The Python API serves /v1, /health, /openapi.json and the Swagger UI at /docs/api during development.
const apiTarget = process.env.FRONTIER_API_TARGET ?? 'http://127.0.0.1:8000'

const escapeHtml = (value: string) =>
  value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

// The static <title> comes from the copy file, so the page has a name before the app renders.
function copyTitle(): Plugin {
  return {
    name: 'copy-title',
    transformIndexHtml(html) {
      const copy = JSON.parse(readFileSync(new URL('./src/copy/en.json', import.meta.url), 'utf8'))
      return html.replace('%APP_NAME%', escapeHtml(String(copy.app.name)))
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  // The documentation app owns /docs; built assets resolve under /docs/assets/.
  base: '/docs/',
  plugins: [react(), tailwindcss(), copyTitle()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/v1': { target: apiTarget, changeOrigin: true },
      '/health': { target: apiTarget, changeOrigin: true },
      '/openapi.json': { target: apiTarget, changeOrigin: true },
      '/docs/api': { target: apiTarget, changeOrigin: true },
    },
  },
})
