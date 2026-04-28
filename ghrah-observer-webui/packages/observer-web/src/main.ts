import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./app.vue";
import router from "./router.js";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
