import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api calls go to FastAPI.
// The ports are read from the .env file in the project folder (one level up):
//   API_PORT      where uvicorn runs (default 8010)
//   DEV_WEB_PORT  where this dev server runs (default 5173)
// The video call connects to LiveKit Cloud directly (LIVEKIT_URL), so it needs no proxy here.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const apiPort = env.API_PORT || "8010";

  return {
    plugins: [react()],
    server: {
      port: Number(env.DEV_WEB_PORT || 5173),
      strictPort: true,   // if the port is busy, stop with a clear message instead of picking another
      allowedHosts: [".trycloudflare.com"],   // the HTTPS tunnel (docker compose --profile tunnel); see README
      proxy: {
        "/api": { target: `http://localhost:${apiPort}`, ws: true },
      },
    },
  };
});
