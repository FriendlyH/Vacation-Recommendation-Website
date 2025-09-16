// vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',                 // important: asset URLs start at /
  build: { outDir: 'dist', emptyOutDir: true } // build inside this folder
})
