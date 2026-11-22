import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // The API is proxied so the SPA and the API share one origin: cookies stay
  // first-party and no CORS configuration is needed. Docker Compose publishes
  // the backend on :4400; a backend started with uvicorn defaults to :8000.
  const apiTarget = env.ENVO_API_PROXY ?? "http://localhost:4400";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: false, xfwd: true },
      },
    },
  };
});
