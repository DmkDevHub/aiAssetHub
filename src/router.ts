import { createRouter, createWebHashHistory, type RouterHistory } from "vue-router";
import LibraryView from "./views/LibraryView.vue";
import ModelsView from './views/ModelsView.vue';
import AppearanceView from "./views/AppearanceView.vue";
import McpView from './views/McpView.vue';
import UnityView from './views/UnityView.vue';
import DiagnosticsView from './views/DiagnosticsView.vue';
import MaintenanceView from './views/MaintenanceView.vue';
import SettingsView from './views/SettingsView.vue';
import SearchSettingsView from './views/SearchSettingsView.vue';
import ImportSettingsView from './views/ImportSettingsView.vue';

const settingsTabs = [
  { path: 'appearance', title: '화면 설정', component: AppearanceView },
  { path: 'models', title: '모델 관리', component: ModelsView },
  { path: 'search', title: '검색 인덱스', component: SearchSettingsView },
  { path: 'mcp', title: 'MCP 연결·로그', component: McpView },
  { path: 'unity', title: 'Unity 연결', component: UnityView },
  { path: 'import', title: '메타데이터 가져오기', component: ImportSettingsView },
  { path: 'diagnostics', title: '진단·비용 감사', component: DiagnosticsView },
  { path: 'maintenance', title: 'DB 백업·복구', component: MaintenanceView },
];

export function createAppRouter(history: RouterHistory = createWebHashHistory()) {
  const router = createRouter({
    history,
    routes: [
      { path: "/", redirect: "/library" },
      { path: "/library", component: LibraryView, meta: { title: "라이브러리" } },
      { path: "/settings/folders", redirect: { path: "/library", query: { panel: "folders" } } },
      { path: "/settings/catalog", redirect: { path: "/library", query: { panel: "catalog" } } },
      {
        path: "/settings",
        component: SettingsView,
        redirect: "/settings/appearance",
        children: settingsTabs.map(({ path, component, title }) => ({ path, component, meta: { title } })),
      },
      { path: "/:pathMatch(.*)*", redirect: "/library" },
    ],
  });

  router.afterEach((to) => {
    document.title = `${String(to.meta.title)} · AI Asset Hub`;
  });

  return router;
}
