import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI backend in ../backend serves both the catalogue API and the
// product imagery. Proxying them keeps the frontend on same-origin paths.
export default defineConfig({
  plugins: [react()],
  server: {
    // 5173 is already taken by the Lecture 7 dev server in this repo.
    port: 5174,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
})
