// Vite configuration for React frontend
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],  // Enable React support
  server: {
    host: '0.0.0.0',  // Allow external connections
    port: 3000  // Frontend port
  }
})