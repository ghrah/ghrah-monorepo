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
      component: () => import("./pages/config.vue"),
      children: [
        {
          path: "",
          redirect: "/config/general",
        },
        {
          path: "general",
          name: "config-general",
          component: () => import("./components/config/general-config-page.vue"),
        },
        {
          path: "agents",
          name: "config-agents",
          component: () => import("./components/config/agent-config-page.vue"),
        },
        {
          path: "abilities",
          name: "config-abilities",
          component: () => import("./components/config/ability-config-page.vue"),
        },
      ],
    },
    {
      path: "/changes",
      name: "changes",
      component: () => import("./pages/changes.vue"),
    },
  ],
});

export default router;
