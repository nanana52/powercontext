import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  server: { host: '0.0.0.0', strictPort: true },
  optimizeDeps: { exclude: ['@huggingface/transformers'] },
  build: { outDir: 'dist', emptyOutDir: true }
});
