/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],

  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  server: {
    // host:true binds 0.0.0.0 so the dev server is reachable from outside the
    // container; polling is required because bind-mounted files on Windows
    // do not deliver inotify events into the Linux VM.
    host: true,
    port: 5173,
    watch: { usePolling: true },
  },

  build: {
    outDir: 'dist',
    sourcemap: true,
    // Fail the build rather than silently shipping an oversized bundle.
    chunkSizeWarningLimit: 600,
  },

  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Tests stub `fetch`; without these, a stub would leak into the next file.
    restoreMocks: true,
    unstubGlobals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/test/**', 'src/**/*.d.ts'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
        statements: 80,
      },
    },
  },
});
