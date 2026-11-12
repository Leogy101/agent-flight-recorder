import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  build: {
    outDir: '../src/agent_flight_recorder/static',
    emptyOutDir: true,
    sourcemap: false,
  },
});
