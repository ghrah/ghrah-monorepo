import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import UnoCSS from "unocss/vite";
import { defineConfig } from "vite";
import { importMapPlugin } from "./src/import-map-plugin";

export default defineConfig({
  plugins: [UnoCSS(), vue(), importMapPlugin()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
});
