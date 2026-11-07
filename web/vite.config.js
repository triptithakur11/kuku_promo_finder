import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` -> http://localhost:5173 (proxies /api to the Python server on :8000)
// `npm run build` -> web/dist, which `python server.py` serves at http://localhost:8000
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
