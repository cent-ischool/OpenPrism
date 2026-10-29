import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// Shared design system lives at the repo root: /design
const designDir = fileURLToPath(new URL('../../design', import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@design': designDir }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // The devcontainer's bind-mounted workspace does not deliver file-change events, so Vite would serve stale code.
    watch: { usePolling: true, interval: 300 },
    proxy: {
      '/api': {
        target: process.env.OPENPRISM_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        xfwd: true
      },
      '/texlive': {
        target: 'https://texlive.swiftlatex.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/texlive/, '')
      }
    }
  }
});
