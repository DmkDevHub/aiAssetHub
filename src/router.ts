import { createRouter, createWebHashHistory, type RouterHistory } from "vue-router";
import LibraryView from "./views/LibraryView.vue";
import ModelsView from './views/ModelsView.vue';
import AppearanceView from "./views/AppearanceView.vue";
import McpView from './views/McpView.vue';
import UnityView from './views/UnityView.vue';
import DiagnosticsView from './views/DiagnosticsView.vue';
import MaintenanceView from './views/MaintenanceView.vue';

export function createAppRouter(history: RouterHistory = createWebHashHistory()) {
  const router = createRouter({
    history,
    routes: [
      { path: "/", redirect: "/library" },
      { path: "/library", component: LibraryView, meta: { title: "라이브러리" } },
      { path: "/settings/models", component: ModelsView, meta: { title: "모델 관리" } },
      { path: "/settings/appearance", component: AppearanceView, meta: { title: "화면 설정" } },
      { path: '/settings/mcp', component: McpView, meta: { title: 'MCP 연결·로그' } },
      { path: '/settings/unity', component: UnityView, meta: { title: 'Unity 연결' } },
      { path: '/settings/diagnostics', component: DiagnosticsView, meta: { title: '진단·비용 감사' } },
      { path: '/settings/maintenance', component: MaintenanceView, meta: { title: 'DB 백업·복구' } },
      { path: "/:pathMatch(.*)*", redirect: "/library" },
    ],
  });

  router.afterEach((to) => {
    document.title = `${String(to.meta.title)} · AI Asset Hub`;
  });

  return router;
}
