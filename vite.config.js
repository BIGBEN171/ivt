// Local development uses the same /api URLs as production Nginx.
// Run Python on 127.0.0.1:8000 before testing capture and server saving locally.
import { defineConfig } from 'vite';
export default defineConfig({
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
