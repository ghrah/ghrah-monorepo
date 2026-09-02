import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  dts: {
    resolve: true,
    compilerOptions: {
      composite: false,
    },
  },
  clean: true,
  sourcemap: true,
  esbuildOptions(options) {
    options.sourcesContent = false;
  },
});
