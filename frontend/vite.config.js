import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

const backendUrl = process.env.VITE_BACKEND_URL || "http://127.0.0.1:5051";

export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    https: true,
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
      "/mic": {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
