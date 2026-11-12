import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // The API runs on :8000 in dev. In production, serve the built assets behind
      // the same origin as the API so this relative /api path keeps working.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // The admin console is its own API surface with its own token audience.
      '/admin/auth': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/me': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/stats': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/analytics': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/security': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/users': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/admins': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/audit': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/admin/emergency': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: true },
});
