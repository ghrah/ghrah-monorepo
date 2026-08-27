import { createPinia } from "pinia";
import { createApp } from "vue";
import "virtual:uno.css";
import "./style.css";
import App from "./app.vue";
import { initFontScale } from "./composables/useFontScale";
import { i18n } from "./i18n";
import router from "./router.js";

function initDarkMode() {
  const stored = localStorage.getItem("theme");
  if (stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
}
initDarkMode();
initFontScale();

const app = createApp(App);
app.use(createPinia());
app.use(i18n);
app.use(router);
app.mount("#app");
