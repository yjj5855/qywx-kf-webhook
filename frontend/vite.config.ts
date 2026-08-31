import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

// dev 模式把 /api 代理到本地 Python 服务（python -m src.main，默认 8000）
export default defineConfig({
  base: '/',
  plugins: [react(), tailwindcss()],
  server: {
    port: 8001,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
});
