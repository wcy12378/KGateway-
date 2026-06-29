import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rolldownOptions: {
      output: {
        codeSplitting: true,
        manualChunks(id: string) {
          if (id.includes('react-dom') || id.includes('/react/')) {
            return 'vendor-react';
          }
          if (id.includes('react-syntax-highlighter') || id.includes('prismjs')) {
            return 'vendor-highlighter';
          }
          if (id.includes('react-markdown') || id.includes('remark-') || id.includes('micromark')) {
            return 'vendor-markdown';
          }
          if (id.includes('recharts') || id.includes('d3')) {
            return 'vendor-charts';
          }
          if (id.includes('react-virtuoso')) {
            return 'vendor-virtual-list';
          }
          if (id.includes('react-router')) {
            return 'vendor-router';
          }
          if (id.includes('lucide-react')) {
            return 'vendor-icons';
          }
          if (id.includes('zustand')) {
            return 'vendor-state';
          }
          if (id.includes('node_modules')) {
            return 'vendor-utilities';
          }
        },
      },
    },
  },
})
