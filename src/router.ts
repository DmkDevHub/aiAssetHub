import { createRouter, createWebHashHistory, type RouterHistory } from "vue-router";
import LibraryView from "./views/LibraryView.vue";
import AppearanceView from "./views/AppearanceView.vue";

export function createAppRouter(history: RouterHistory = createWebHashHistory()) {
  const router = createRouter({
    history,
    routes: [
      { path: "/", redirect: "/library" },
      { path: "/library", component: LibraryView, meta: { title: "라이브러리" } },
      { path: "/settings/appearance", component: AppearanceView, meta: { title: "화면 설정" } },
      { path: "/:pathMatch(.*)*", redirect: "/library" },
    ],
  });

  router.afterEach((to) => {
    document.title = `${String(to.meta.title)} · AI Asset Hub`;
  });

  return router;
}
