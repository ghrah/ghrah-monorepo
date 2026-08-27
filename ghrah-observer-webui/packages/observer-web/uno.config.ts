import { defineConfig, presetIcons, presetUno } from "unocss";

export default defineConfig({
  darkMode: "class",
  presets: [
    presetUno(),
    presetIcons({
      scale: 1.2,
      cdn: "https://esm.sh/",
    }),
  ],
  shortcuts: {
    btn: "px-3 py-1.5 rounded border-none cursor-pointer text-sm font-medium transition-colors duration-200",
    "btn-primary":
      "btn bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed",
    "btn-danger":
      "btn bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed",
    "btn-secondary":
      "btn bg-gray-200 text-gray-800 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed",
    panel: "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded",
    badge: "inline-block px-2 py-0.5 rounded-full text-xs font-medium",
  },
  theme: {
    colors: {
      primary: "#0066cc",
    },
    fontSize: {
      xs: "0.8125rem",
      sm: "0.9375rem",
      base: "1rem",
      lg: "1.125rem",
    },
  },
});
