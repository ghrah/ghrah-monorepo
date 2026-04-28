import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "dashboard",
      component: () => import("./pages/dashboard.vue"),
    },
    {
      path: "/config",
      name: "config",
      component: () => import("./pages/config.vue"),
    },
    {
      path: "/changes",
      name: "changes",
      component: () => import("./pages/changes.vue"),
    },
  ],
});

export default router;
