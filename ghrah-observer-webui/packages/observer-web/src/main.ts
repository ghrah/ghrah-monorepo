import { createPinia } from "pinia";
import { createApp } from "vue";
import "virtual:uno.css";
import App from "./app.vue";
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

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
