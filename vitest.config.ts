import { defineConfig } from 'vitest/config';
import path from 'node:path';
export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  test: { environment: 'node', include: ['tests/**/*.test.ts', 'src/**/*.test.ts'], exclude: ['node_modules', '**/node_modules', '62-cinematic-web-funnel-engine/**', '46-kie-callback-relay/**', '58-podcast-production-engine/**'] },
});
