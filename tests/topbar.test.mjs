import assert from "node:assert/strict";
import { after, afterEach, before, beforeEach, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const virtualConsole = new VirtualConsole();
const dom = new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>', {
  url: "http://component.test/",
  virtualConsole,
});
const originalGlobals = new Map();
originalGlobals.set('isTauri', Object.getOwnPropertyDescriptor(globalThis, 'isTauri'));
for (const key of ["window", "document", "history", "location", "Document", "ShadowRoot", "Element", "HTMLElement", "SVGElement", "Event", "InputEvent", "CompositionEvent", "KeyboardEvent", "MouseEvent"]) {
  originalGlobals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
}

let transportCalls = 0;
const rejectTransport = () => {
  transportCalls++;
  throw new Error("Component tests must not use a network or Core transport");
};
const originalFetch = globalThis.fetch;
globalThis.fetch = dom.window.fetch = rejectTransport;
dom.window.open = rejectTransport;
for (const key of ["XMLHttpRequest", "WebSocket"]) {
  originalGlobals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  const BlockedTransport = class { constructor() { rejectTransport(); } };
  dom.window[key] = BlockedTransport;
  Object.defineProperty(globalThis, key, { configurable: true, value: BlockedTransport });
}

let components;
let createApp;
let h;
let ref;
let nextTick;
let createMemoryHistory;
let app;
let router;
let errors = [];
let mounted = false;
let advanceEventClock;
let workspaceWidth = 1100;
const resizeObservers = new Set();
const originalRect = dom.window.HTMLElement.prototype.getBoundingClientRect;
dom.window.HTMLElement.prototype.getBoundingClientRect = function () {
  if (this.classList.contains('library-workspace')) return { ...originalRect.call(this), width: workspaceWidth };
  return originalRect.call(this);
};
originalGlobals.set('ResizeObserver', Object.getOwnPropertyDescriptor(globalThis, 'ResizeObserver'));
globalThis.ResizeObserver = class {
  constructor(callback) { this.callback = callback; this.target = null; }
  observe(target) { this.target = target; resizeObservers.add(this); }
  disconnect() { this.target = null; resizeObservers.delete(this); }
};
virtualConsole.on("jsdomError", (error) => errors.push(error));

before(async () => {
  const { build } = await import("vite");
  const { default: vuePlugin } = await import("@vitejs/plugin-vue");
  const outDir = fileURLToPath(new URL("../.artifacts/component-tests/", import.meta.url));
  await build({
    configFile: false,
    plugins: [vuePlugin()],
    logLevel: "silent",
    build: {
      outDir,
      emptyOutDir: true,
      minify: false,
      lib: {
        entry: fileURLToPath(new URL("./fixtures/app-entry.ts", import.meta.url)),
        formats: ["es"],
        fileName: () => "app.mjs",
      },
      rolldownOptions: { external: ["vue", "vue-router"] },
    },
  });
  ({ createApp, h, ref, nextTick } = await import("vue"));
  ({ createMemoryHistory } = await import("vue-router"));
  components = await import(pathToFileURL(`${outDir}/app.mjs`).href);
});

beforeEach(async (t) => {
  // Browser events arrive in later tasks; advance Date deterministically for Vue's event guard.
  t.mock.timers.enable({ apis: ["Date", "setInterval"], now: Date.now() });
  advanceEventClock = () => t.mock.timers.tick(1);
  mounted = false;
  transportCalls = 0;
  errors = [];
  workspaceWidth = 1100;
  delete dom.window.__TAURI_INTERNALS__;
  globalThis.isTauri = false;
  components.setSearchQuery("");
  components.setTheme("dark");
  components.setLibraryPanelWidth(components.LIBRARY_PANEL_WIDTH.initial);
  components.selectLibraryFolder(null);
  components.setGalleryViewMode("grid");
  components.setDetailsCollapsed(false);
  components.setPickedFolderPath(null);
  components.resetLibrarySession();
  for (const operation of components.operations) {
    if (operation.state === 'running') components.receiveOperation({ id: operation.id, kind: operation.kind, state: 'cancelled' });
    if (operation.state === 'failed') components.dismissOperationAlert(operation.id);
  }
  components.clearFinishedOperations();
  document.body.innerHTML = '<div id="app"></div>';
  router = components.createAppRouter(createMemoryHistory());
  await router.push("/library");
  app = createApp(components.App);
  app.config.errorHandler = (error) => errors.push(error);
  app.config.warnHandler = (message) => errors.push(new Error(message));
  app.use(router);
  app.mount("#app");
  mounted = true;
  await nextTick();
});

afterEach(() => {
  if (mounted) app.unmount();
  router?.options.history.destroy();
  assert.deepEqual(errors, [], "Vue should not report runtime errors");
  assert.equal(transportCalls, 0, "Input and navigation must not contact a provider or Core");
});

after(() => {
  dom.window.close();
  globalThis.fetch = originalFetch;
  for (const [key, descriptor] of originalGlobals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

const searchInput = () => document.querySelector('#asset-search');
const currentLocation = () => document.querySelector('.breadcrumbs [aria-current="page"]');
const clearButton = () => document.querySelector('button[aria-label="검색어 지우기"]');

function dispatch(element, event) {
  advanceEventClock();
  return element.dispatchEvent(event);
}

async function inputText(value) {
  searchInput().value = value;
  dispatch(searchInput(), new dom.window.Event("input", { bubbles: true }));
  await nextTick();
}

async function activateLink(selector) {
  dispatch(document.querySelector(selector),
    new dom.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }),
  );
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
}

test("top bar renders a labelled search field and current route breadcrumb", () => {
  assert.equal(document.querySelector('label[for="asset-search"]').textContent, "에셋 검색어");
  assert.equal(searchInput().type, "search");
  assert.equal(searchInput().value, "");
  assert.equal(currentLocation().textContent, "라이브러리");
  assert.equal(document.title, "라이브러리 · AI Asset Hub");
  assert.equal(clearButton(), null);
  assert.equal(document.querySelector('[aria-label="주 메뉴"] a').textContent, "화면 설정");
});

test("Unicode and HTML-like query text stays literal and form submission makes no request", async () => {
  const query = '숲 🌳 <img src=x onerror="alert(1)">';
  await inputText(query);
  assert.equal(components.workspace.searchQuery, query);
  assert.equal(searchInput().value, query);
  assert.equal(document.querySelector("img"), null);
  const submission = new dom.window.Event("submit", { cancelable: true, bubbles: true });
  dispatch(document.querySelector('form[role="search"]'), submission);
  assert.equal(submission.defaultPrevented, true);
  assert.equal(router.currentRoute.value.path, "/library");
  assert.equal(components.workspace.searchQuery, query);
});

test("clear button removes the query and returns focus to the input", async () => {
  await inputText("나무");
  advanceEventClock();
  clearButton().click();
  await nextTick();
  assert.equal(searchInput().value, "");
  assert.equal(components.workspace.searchQuery, "");
  assert.equal(clearButton(), null);
  assert.equal(document.activeElement, searchInput());
});

test("Escape clears a query without leaving the current route", async () => {
  await inputText("중세 성");
  dispatch(searchInput(), new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await nextTick();
  assert.equal(components.workspace.searchQuery, "");
  assert.equal(searchInput().value, "");
  assert.equal(router.currentRoute.value.path, "/library");
});

test("Korean composition waits for commit and composing Escape does not clear the query", async () => {
  await inputText("숲");
  dispatch(searchInput(), new dom.window.CompositionEvent("compositionstart", { bubbles: true }));
  searchInput().value = "숲ㄱ";
  dispatch(searchInput(), new dom.window.InputEvent("input", { bubbles: true, isComposing: true }));
  dispatch(searchInput(), new dom.window.KeyboardEvent("keydown", {
    key: "Escape", bubbles: true, isComposing: true,
  }));
  await nextTick();
  assert.equal(components.workspace.searchQuery, "숲");
  assert.equal(searchInput().value, "숲ㄱ");
  searchInput().value = "숲길";
  dispatch(searchInput(), new dom.window.CompositionEvent("compositionend", { bubbles: true }));
  await nextTick();
  assert.equal(components.workspace.searchQuery, "숲길");
});

test("settings and breadcrumb links change real routes while retaining the query", async () => {
  await inputText("붉은 지붕");
  await activateLink('[aria-label="주 메뉴"] a');
  assert.equal(router.currentRoute.value.path, "/settings/appearance");
  assert.equal(document.querySelector("h1").textContent, "화면 설정");
  assert.equal(currentLocation().textContent, "화면 설정");
  assert.equal(document.title, "화면 설정 · AI Asset Hub");
  assert.equal(searchInput().value, "붉은 지붕");
  await activateLink(".breadcrumbs a");
  assert.equal(router.currentRoute.value.path, "/library");
  assert.equal(currentLocation().textContent, "라이브러리");
  assert.equal(searchInput().value, "붉은 지붕");
});

test("skip link focuses the main content without turning the anchor into a route", async () => {
  await router.push("/settings/appearance");
  await nextTick();
  await activateLink(".skip-link");
  assert.equal(document.activeElement.id, "main-content");
  assert.equal(router.currentRoute.value.path, "/settings/appearance");
});

test("theme changes and unknown-route recovery preserve the top bar state", async () => {
  await inputText("돌길");
  await router.push("/settings/appearance");
  await nextTick();
  const lightTheme = document.querySelector('input[name="theme"][value="light"]');
  lightTheme.checked = true;
  dispatch(lightTheme, new dom.window.Event("change", { bubbles: true }));
  await nextTick();
  assert.equal(document.documentElement.dataset.theme, "light");
  await router.push("/missing-route");
  await nextTick();
  assert.equal(router.currentRoute.value.path, "/library");
  assert.equal(currentLocation().textContent, "라이브러리");
  assert.equal(searchInput().value, "돌길");
  assert.equal(document.documentElement.dataset.theme, "light");
});

// Library folder data is isolated fixture input, never a registered folder or asset ID.
const folderFixture = [
  { id: "fixture-environment", name: "환경", children: [
    { id: "fixture-trees", name: "나무", children: [{ id: "fixture-oak", name: "참나무" }] },
    { id: "fixture-rocks", name: "바위" },
  ] },
  { id: "fixture-audio", name: "효과음" },
];
const tree = () => document.querySelector('[role="tree"]');
const separator = () => document.querySelector('[role="separator"]');
const treeItems = () => [...tree().querySelectorAll('[role="treeitem"]')];
const item = (name) => treeItems().find((element) => element.getAttribute("aria-label") === name);

async function mountPanel(nodes, selectedId = null) {
  app.unmount();
  mounted = false;
  components.selectLibraryFolder(selectedId);
  app = createApp({ render: () => h(components.LibraryTreePanel, {
    nodes,
    selectedId: components.libraryUi.selectedFolderId,
    onSelect: components.selectLibraryFolder,
  }) });
  app.config.errorHandler = (error) => errors.push(error);
  app.config.warnHandler = (message) => errors.push(new Error(message));
  app.mount("#app");
  mounted = true;
  await nextTick();
}

async function key(element, value) {
  dispatch(element, new dom.window.KeyboardEvent("keydown", {
    key: value, bubbles: true, cancelable: true,
  }));
  await nextTick();
}

async function pointer(element, type, clientX, pointerId = 1, button = 0, buttons = type === "pointermove" || type === "pointerdown" ? 1 : 0) {
  const event = new dom.window.MouseEvent(type, {
    bubbles: true, cancelable: true, clientX, button, buttons,
  });
  Object.defineProperties(event, {
    pointerId: { value: pointerId },
    isPrimary: { value: true },
  });
  dispatch(element, event);
  await nextTick();
}

test("production library panel shows an honest empty tree and bounded accessible separator", () => {
  assert.equal(treeItems().length, 1);
  assert.equal(item("전체 에셋").getAttribute("aria-selected"), "true");
  assert.match(document.querySelector(".library-empty").textContent, /등록된 폴더가 없습니다/);
  assert.equal(document.querySelector("[data-folder-id]"), null);
  assert.equal(separator().getAttribute("aria-orientation"), "vertical");
  assert.equal(separator().getAttribute("aria-valuenow"), "240");
  assert.equal(separator().getAttribute("aria-valuemin"), "200");
  assert.equal(separator().getAttribute("aria-valuemax"), "360");
  assert.equal(document.getElementById(separator().getAttribute("aria-controls")).tagName, "ASIDE");
  assert.equal(document.querySelector(".library-workspace").style.getPropertyValue("--library-panel-width"), "240px");
});

test("folder selection emits the supplied ID and all-assets selection clears it", async () => {
  await mountPanel(folderFixture);
  dispatch(item("효과음"), new dom.window.MouseEvent("click", { bubbles: true }));
  await nextTick();
  assert.equal(components.libraryUi.selectedFolderId, "fixture-audio");
  assert.equal(item("효과음").getAttribute("aria-selected"), "true");
  assert.equal(tree().querySelectorAll('[aria-selected="true"]').length, 1);
  await key(item("전체 에셋"), "Enter");
  assert.equal(components.libraryUi.selectedFolderId, null);
  assert.equal(item("전체 에셋").getAttribute("aria-selected"), "true");
});

test("folder disclosure preserves selection and creates nested groups only when expanded", async () => {
  await mountPanel(folderFixture);
  assert.equal(item("나무"), undefined);
  dispatch(item("환경").querySelector("button"), new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
  await nextTick();
  assert.equal(item("환경").getAttribute("aria-expanded"), "true");
  assert.equal(item("나무").parentElement.getAttribute("role"), "group");
  assert.equal(item("나무").getAttribute("aria-level"), "2");
  assert.equal(item("효과음").hasAttribute("aria-expanded"), false);
  assert.equal(components.libraryUi.selectedFolderId, null);
  await key(item("환경"), "ArrowLeft");
  assert.equal(item("환경").getAttribute("aria-expanded"), "false");
  assert.equal(item("나무"), undefined);
});

test("tree keyboard navigation separates focus from selection and follows visible hierarchy", async () => {
  await mountPanel(folderFixture);
  await key(item("전체 에셋"), "ArrowDown");
  assert.equal(document.activeElement, item("환경"));
  assert.equal(components.libraryUi.selectedFolderId, null);
  await key(item("환경"), "ArrowRight");
  await key(item("환경"), "ArrowRight");
  assert.equal(document.activeElement, item("나무"));
  await key(item("나무"), " ");
  assert.equal(components.libraryUi.selectedFolderId, "fixture-trees");
  await key(item("나무"), "ArrowLeft");
  assert.equal(document.activeElement, item("환경"));
  await key(item("환경"), "End");
  assert.equal(document.activeElement, item("효과음"));
  await key(item("효과음"), "ArrowUp");
  assert.equal(document.activeElement, item("바위"));
  await key(item("바위"), "Home");
  assert.equal(document.activeElement, item("전체 에셋"));
  assert.equal(treeItems().filter((element) => element.tabIndex === 0).length, 1);
  assert.equal(components.libraryUi.selectedFolderId, "fixture-trees");
});

test("folder labels remain text even with markup and quote-like IDs", async () => {
  const id = 'fixture-"/strange';
  const name = '<img src=x onerror="alert(1)"> 긴 한글 폴더';
  await mountPanel([{ id, name }]);
  assert.equal(item(name).textContent, name);
  assert.equal(document.querySelector("img"), null);
  dispatch(item(name), new dom.window.MouseEvent("click", { bubbles: true }));
  await nextTick();
  assert.equal(components.libraryUi.selectedFolderId, id);
});

test("separator keyboard resizing clamps width and updates actual layout state", async () => {
  await key(separator(), "ArrowRight");
  assert.equal(components.libraryUi.panelWidth, 256);
  assert.equal(separator().getAttribute("aria-valuenow"), "256");
  assert.equal(document.querySelector(".library-workspace").style.getPropertyValue("--library-panel-width"), "256px");
  await key(separator(), "End");
  await key(separator(), "ArrowRight");
  assert.equal(components.libraryUi.panelWidth, 360);
  await key(separator(), "Home");
  await key(separator(), "ArrowLeft");
  assert.equal(components.libraryUi.panelWidth, 200);
  dispatch(separator(), new dom.window.MouseEvent("dblclick", { bubbles: true }));
  await nextTick();
  assert.equal(components.libraryUi.panelWidth, 240);
});

test("pointer resizing tracks only its pointer, applies limits, and stops after pointerup", async () => {
  await pointer(separator(), "pointerdown", 200);
  await pointer(dom.window, "pointermove", 250, 2);
  assert.equal(components.libraryUi.panelWidth, 240);
  await pointer(dom.window, "pointermove", 250);
  assert.equal(components.libraryUi.panelWidth, 290);
  await pointer(dom.window, "pointermove", 1000);
  assert.equal(components.libraryUi.panelWidth, 360);
  await pointer(dom.window, "pointerup", 1000);
  await pointer(dom.window, "pointermove", 0);
  assert.equal(components.libraryUi.panelWidth, 360);
  assert.equal(separator().classList.contains("is-resizing"), false);
});

test("Escape cancels a drag while pointercancel and window blur remove resize listeners", async () => {
  await pointer(separator(), "pointerdown", 200);
  await pointer(dom.window, "pointermove", 240);
  await key(separator(), "Escape");
  assert.equal(components.libraryUi.panelWidth, 240);
  await pointer(dom.window, "pointermove", 500);
  assert.equal(components.libraryUi.panelWidth, 240);
  await pointer(separator(), "pointerdown", 200);
  await pointer(dom.window, "pointermove", 230);
  await pointer(dom.window, "pointercancel", 230);
  await pointer(dom.window, "pointermove", 350);
  assert.equal(components.libraryUi.panelWidth, 270);
  await pointer(separator(), "pointerdown", 200);
  dispatch(dom.window, new dom.window.Event("blur"));
  await pointer(dom.window, "pointermove", 300);
  assert.equal(components.libraryUi.panelWidth, 270);
});

test("secondary pointer buttons and nonfinite widths do not change the panel", async () => {
  await pointer(separator(), "pointerdown", 200, 1, 2);
  await pointer(dom.window, "pointermove", 300);
  components.setLibraryPanelWidth(Number.NaN);
  components.setLibraryPanelWidth(Number.POSITIVE_INFINITY);
  assert.equal(components.libraryUi.panelWidth, 240);
  assert.equal(separator().classList.contains("is-resizing"), false);
});

test("a released pointer button stops a drag even when pointerup was missed", async () => {
  await pointer(separator(), "pointerdown", 200);
  await pointer(dom.window, "pointermove", 230);
  await pointer(dom.window, "pointermove", 500, 1, 0, 0);
  assert.equal(components.libraryUi.panelWidth, 270);
  assert.equal(separator().classList.contains("is-resizing"), false);
  await pointer(dom.window, "pointermove", 600);
  assert.equal(components.libraryUi.panelWidth, 270);
});

test("route unmount stops dragging and preserves the accepted width for the library", async () => {
  await pointer(separator(), "pointerdown", 200);
  await pointer(dom.window, "pointermove", 240);
  await activateLink('[aria-label="주 메뉴"] a');
  assert.equal(separator(), null);
  await pointer(dom.window, "pointermove", 400);
  assert.equal(components.libraryUi.panelWidth, 280);
  await activateLink(".breadcrumbs a");
  assert.equal(separator().getAttribute("aria-valuenow"), "280");
  assert.equal(treeItems().length, 1);
});

const galleryFixture = [
  { id: "fixture-gallery-tree", name: "나무.png", kind: "PNG" },
  { id: "fixture-gallery-stone", name: "돌 모델.fbx", kind: "FBX" },
];
const galleryButton = (name) => [...document.querySelectorAll('.gallery-view-controls button')]
  .find((button) => button.textContent === name);

async function mountGallery(items) {
  app.unmount();
  mounted = false;
  const data = ref(items);
  app = createApp({ render: () => h(components.AssetGallery, { items: data.value }) });
  app.config.errorHandler = (error) => errors.push(error);
  app.config.warnHandler = (message) => errors.push(new Error(message));
  app.mount("#app");
  mounted = true;
  await nextTick();
  return data;
}

async function changeGalleryMode(name) {
  dispatch(galleryButton(name), new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
  await nextTick();
}

test("production gallery is empty with no fixture assets or pretend preview", () => {
  assert.equal(document.querySelector('.gallery-count').textContent, "0개 에셋");
  assert.match(document.querySelector('.gallery-empty[role="status"]').textContent, /표시할 에셋이 없습니다/);
  assert.equal(document.querySelector(".asset-grid"), null);
  assert.equal(document.querySelector(".asset-list"), null);
  assert.equal(document.querySelector("[data-asset-id]"), null);
  assert.equal(document.querySelector(".asset-gallery img"), null);
  assert.equal(galleryButton("그리드").getAttribute("aria-pressed"), "true");
});

test("view controls work in the empty state and reject an invalid view mode", async () => {
  await changeGalleryMode("목록");
  assert.equal(components.libraryUi.galleryViewMode, "list");
  assert.equal(galleryButton("목록").getAttribute("aria-pressed"), "true");
  assert.equal(galleryButton("그리드").getAttribute("aria-pressed"), "false");
  assert.equal(document.querySelector(".asset-list"), null);
  assert.equal(document.querySelector('.gallery-count').textContent, "0개 에셋");
  components.setGalleryViewMode("invalid-mode");
  assert.equal(components.libraryUi.galleryViewMode, "list");
  await changeGalleryMode("그리드");
  assert.ok(document.querySelector(".gallery-empty"));
  assert.equal(components.libraryUi.galleryViewMode, "grid");
});

test("grid cards render only supplied asset names, formats and IDs in order", async () => {
  await mountGallery(galleryFixture);
  const cards = [...document.querySelectorAll('.asset-grid > li')];
  assert.deepEqual(cards.map((card) => card.dataset.assetId), galleryFixture.map((item) => item.id));
  assert.deepEqual(cards.map((card) => card.querySelector('.asset-name').textContent), ["나무.png", "돌 모델.fbx"]);
  assert.deepEqual(cards.map((card) => card.querySelector('.asset-kind').textContent), ["PNG", "FBX"]);
  assert.equal(document.querySelector('.gallery-count').textContent, "2개 에셋");
  assert.equal(document.querySelector(".gallery-empty"), null);
  assert.equal(document.querySelector("img"), null);
});

test("list table and grid share the same data without changing asset order", async () => {
  await mountGallery(galleryFixture);
  await changeGalleryMode("목록");
  assert.equal(document.querySelector('.asset-list').getAttribute("aria-label"), "에셋 목록");
  assert.deepEqual([...document.querySelectorAll('th[scope="col"]')].map((cell) => cell.textContent), ["에셋명", "유형"]);
  assert.deepEqual([...document.querySelectorAll('tbody tr')].map((row) => [...row.cells].map((cell) => cell.textContent)),
    [["나무.png", "PNG"], ["돌 모델.fbx", "FBX"]]);
  assert.equal(document.querySelector('.asset-grid'), null);
  await changeGalleryMode("그리드");
  assert.equal(document.querySelector('.asset-list'), null);
  assert.deepEqual([...document.querySelectorAll('.asset-card')].map((card) => card.dataset.assetId), galleryFixture.map((item) => item.id));
});

test("incoming gallery data updates counts and returns to the correct empty state", async () => {
  const data = await mountGallery(galleryFixture);
  await changeGalleryMode("목록");
  data.value = [galleryFixture[1]];
  await nextTick();
  assert.equal(document.querySelector('.gallery-count').textContent, "1개 에셋");
  assert.equal(document.querySelectorAll('tbody tr').length, 1);
  data.value = [];
  await nextTick();
  assert.equal(document.querySelector('.asset-list'), null);
  assert.ok(document.querySelector('.gallery-empty'));
  assert.equal(document.querySelector('.gallery-count').textContent, "0개 에셋");
  assert.equal(galleryButton("목록").getAttribute("aria-pressed"), "true");
});

test("gallery view persists across routes alongside query and panel width", async () => {
  await inputText("미분석 검색어");
  await key(separator(), "ArrowRight");
  await changeGalleryMode("목록");
  await activateLink('[aria-label="주 메뉴"] a');
  assert.equal(document.querySelector('.asset-gallery'), null);
  await activateLink('.breadcrumbs a');
  assert.equal(galleryButton("목록").getAttribute("aria-pressed"), "true");
  assert.equal(searchInput().value, "미분석 검색어");
  assert.equal(separator().getAttribute("aria-valuenow"), "256");
  assert.equal(document.querySelector('.gallery-count').textContent, "0개 에셋");
  assert.doesNotMatch(document.querySelector('.gallery-empty').textContent, /검색 결과/);
});

test("long and markup-like asset metadata stays literal in both layouts", async () => {
  const name = '<img src=x onerror="alert(1)">' + "긴 파일명".repeat(30);
  const kind = '<script>alert(1)</script>';
  const id = 'fixture-asset-"/id';
  await mountGallery([{ id, name, kind }]);
  assert.equal(document.querySelector('.asset-name').textContent, name);
  assert.equal(document.querySelector('.asset-name').title, name);
  assert.equal(document.querySelector('[data-asset-id]').dataset.assetId, id);
  assert.equal(document.querySelector('.asset-kind').textContent, kind);
  await changeGalleryMode("목록");
  assert.equal(document.querySelector('.asset-name').title, name);
  assert.equal(document.querySelector('tbody tr').cells[1].textContent, kind);
  assert.equal(document.querySelectorAll('img, script').length, 0);
});

async function mountWorkspace(items) {
  app.unmount();
  mounted = false;
  const data = ref(items);
  app = createApp({ render: () => h(components.LibraryView, { items: data.value }) });
  app.config.errorHandler = (error) => errors.push(error);
  app.config.warnHandler = (message) => errors.push(new Error(message));
  app.mount("#app");
  mounted = true;
  await nextTick();
  return data;
}

async function clickElement(selector) {
  dispatch(document.querySelector(selector), new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
  await nextTick();
}

test("production details start empty and collapse control has a real target", async () => {
  assert.match(document.querySelector('.detail-empty').textContent, /에셋을 선택/);
  assert.equal(document.querySelector('[role="tablist"]'), null);
  assert.equal(document.querySelector('.detail-toggle').getAttribute('aria-controls'), 'asset-details');
  await clickElement('.detail-toggle');
  assert.equal(document.querySelector('#asset-details').hidden, true);
  assert.equal(document.querySelector('.detail-toggle').getAttribute('aria-expanded'), 'false');
  await clickElement('.detail-toggle');
  assert.equal(document.querySelector('#asset-details').hidden, false);
});

test("supplied gallery selection drives details in both grid and list", async () => {
  await mountWorkspace(galleryFixture);
  await clickElement('.asset-card .asset-select');
  assert.equal(document.querySelector('.detail-asset-name').textContent, '나무.png');
  assert.deepEqual([...document.querySelectorAll('#asset-details dd')].map((node) => node.textContent), ['나무.png', 'PNG']);
  assert.equal(document.querySelector('.asset-select').getAttribute('aria-pressed'), 'true');
  await changeGalleryMode('목록');
  assert.equal(document.querySelector('.asset-select').getAttribute('aria-pressed'), 'true');
  await clickElement('tbody tr:last-child .asset-select');
  assert.equal(document.querySelector('.detail-asset-name').textContent, '돌 모델.fbx');
  assert.equal(document.querySelectorAll('.asset-select[aria-pressed="true"]').length, 1);
});

test("detail tabs support roving keyboard activation with linked panels", async () => {
  await mountWorkspace(galleryFixture);
  await clickElement('.asset-select');
  const info = document.querySelector('#detail-tab-info');
  const analysis = document.querySelector('#detail-tab-analysis');
  await key(info, 'ArrowRight');
  assert.equal(document.activeElement, analysis);
  assert.equal(analysis.getAttribute('aria-selected'), 'true');
  assert.equal(info.tabIndex, -1);
  assert.equal(document.querySelector('#detail-panel-info').hidden, true);
  assert.equal(document.querySelector('#detail-panel-analysis').hidden, false);
  assert.match(document.querySelector('.detail-analysis').textContent, /제공된 분석 결과가 없습니다/);
  await key(analysis, 'ArrowRight');
  assert.equal(document.activeElement, info);
  await key(info, 'End');
  assert.equal(document.activeElement, analysis);
  await key(analysis, 'Home');
  assert.equal(document.activeElement, info);
  await key(info, 'ArrowLeft');
  assert.equal(document.activeElement, analysis);
});

test("selection changes reset the tab and removed assets clear stale details", async () => {
  const data = await mountWorkspace([{ ...galleryFixture[0], analysisText: 'fixture 분석문' }, galleryFixture[1]]);
  await clickElement('.asset-select');
  await clickElement('#detail-tab-analysis');
  assert.equal(document.querySelector('.detail-analysis').textContent, 'fixture 분석문');
  await clickElement('.asset-card:last-child .asset-select');
  assert.equal(document.querySelector('#detail-tab-info').getAttribute('aria-selected'), 'true');
  assert.match(document.querySelector('.detail-analysis').textContent, /제공된 분석 결과가 없습니다/);
  data.value = [galleryFixture[0]];
  await nextTick();
  assert.ok(document.querySelector('.detail-empty'));
  assert.equal(document.querySelector('.detail-asset-name'), null);
  assert.equal(document.querySelectorAll('.asset-select[aria-pressed="true"]').length, 0);
});

test("collapsed details retain selection and tab while data updates remain current", async () => {
  const data = await mountWorkspace(galleryFixture);
  await clickElement('.asset-select');
  await clickElement('#detail-tab-analysis');
  await clickElement('.detail-toggle');
  data.value = [{ ...galleryFixture[0], analysisText: '갱신된 fixture 결과' }];
  await nextTick();
  await clickElement('.detail-toggle');
  assert.equal(document.querySelector('#detail-tab-analysis').getAttribute('aria-selected'), 'true');
  assert.equal(document.querySelector('.detail-analysis').textContent, '갱신된 fixture 결과');
});

test("details collapse preference survives actual route navigation", async () => {
  await clickElement('.detail-toggle');
  await activateLink('[aria-label="주 메뉴"] a');
  await activateLink('.breadcrumbs a');
  assert.equal(document.querySelector('#asset-details').hidden, true);
  assert.equal(document.querySelector('.detail-toggle').textContent, '상세 펼치기');
});

test("details render untrusted names and analysis as text without resource loads", async () => {
  const text = '<img src=x onerror="alert(1)"><script>secret()</script>';
  await mountWorkspace([{ id: 'fixture-details', name: text, kind: text, analysisText: text }]);
  await clickElement('.asset-select');
  await clickElement('#detail-tab-analysis');
  assert.equal(document.querySelector('.detail-asset-name').textContent, text);
  assert.equal(document.querySelector('.detail-analysis').textContent, text);
  assert.equal(document.querySelectorAll('img, script').length, 0);
});

async function resizeWorkspace(width) {
  workspaceWidth = width;
  for (const observer of resizeObservers) {
    observer.callback([{ target: observer.target, contentRect: { width } }]);
  }
  await nextTick();
}

test("workspace layout reserves gallery width at narrow, medium and wide sizes", () => {
  const layout = components.workspaceLayout;
  assert.equal(layout(320, 240, false), 'compact');
  assert.equal(layout(569, 240, false), 'compact');
  assert.equal(layout(570, 240, false), 'medium');
  assert.equal(layout(859, 240, false), 'medium');
  assert.equal(layout(860, 240, false), 'wide');
  assert.equal(layout(800, 240, true), 'wide');
  assert.equal(layout(900, 360, false), 'medium');
});

test("resize observer changes layout and removes unusable narrow-screen splitter", async () => {
  assert.equal(document.querySelector('.library-workspace').dataset.layout, 'wide');
  await resizeWorkspace(768);
  assert.equal(document.querySelector('.library-workspace').dataset.layout, 'medium');
  assert.ok(separator());
  await resizeWorkspace(320);
  assert.equal(document.querySelector('.library-workspace').dataset.layout, 'compact');
  assert.equal(separator(), null);
  assert.ok(document.querySelector('.asset-gallery'));
  assert.ok(document.querySelector('.detail-toggle'));
  await resizeWorkspace(1100);
  assert.equal(separator().getAttribute('aria-valuenow'), '240');
});

test("shrinking during a drag stops resizing and restores focus to the gallery", async () => {
  await pointer(separator(), 'pointerdown', 240);
  await pointer(window, 'pointermove', 280);
  await nextTick();
  assert.equal(components.libraryUi.panelWidth, 280);
  await resizeWorkspace(320);
  await nextTick();
  assert.equal(document.activeElement, galleryButton('그리드'));
  await pointer(window, 'pointermove', 350);
  await nextTick();
  assert.equal(components.libraryUi.panelWidth, 280);
  await resizeWorkspace(1100);
  assert.equal(separator().getAttribute('aria-valuenow'), '280');
});

test("resizing and collapse use current width without clearing view or selection", async () => {
  await mountWorkspace(galleryFixture);
  await clickElement('.asset-select');
  await changeGalleryMode('목록');
  await resizeWorkspace(900);
  await key(separator(), 'End');
  assert.equal(document.querySelector('.library-workspace').dataset.layout, 'medium');
  await clickElement('.detail-toggle');
  assert.equal(document.querySelector('.library-workspace').dataset.layout, 'wide');
  await resizeWorkspace(320);
  assert.equal(document.querySelector('.detail-asset-name').textContent, '나무.png');
  assert.equal(galleryButton('목록').getAttribute('aria-pressed'), 'true');
  assert.equal(document.querySelector('#asset-details').hidden, true);
});

test("F6 cycles actual workspace regions and Shift F6 reverses without trapping Tab", async () => {
  const tree = document.querySelector('[role="treeitem"]');
  tree.focus();
  await key(tree, 'F6');
  assert.equal(document.activeElement, galleryButton('그리드'));
  await key(document.activeElement, 'F6');
  assert.equal(document.activeElement, document.querySelector('.detail-toggle'));
  await key(document.activeElement, 'F6');
  assert.equal(document.activeElement, tree);
  const reverse = new dom.window.KeyboardEvent('keydown', { key: 'F6', shiftKey: true, bubbles: true, cancelable: true });
  dispatch(tree, reverse);
  await nextTick();
  assert.equal(document.activeElement, document.querySelector('.detail-toggle'));
  const tab = new dom.window.KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
  dispatch(document.activeElement, tab);
  assert.equal(tab.defaultPrevented, false);
});

test("F6 prefers selected asset and active detail tab even in compact layout", async () => {
  await mountWorkspace(galleryFixture);
  await clickElement('.asset-select');
  await clickElement('#detail-tab-analysis');
  await resizeWorkspace(320);
  const tree = document.querySelector('[role="treeitem"]');
  tree.focus();
  await key(tree, 'F6');
  assert.equal(document.activeElement, document.querySelector('.asset-select[aria-pressed="true"]'));
  await key(document.activeElement, 'F6');
  assert.equal(document.activeElement, document.querySelector('#detail-tab-analysis'));
});

test("workspace observer disconnects on route unmount and ignores invalid measurements", async () => {
  assert.equal(resizeObservers.size, 1);
  await resizeWorkspace(Number.NaN);
  assert.equal(document.querySelector('.library-workspace').dataset.layout, 'wide');
  await activateLink('[aria-label="주 메뉴"] a');
  assert.equal(resizeObservers.size, 0);
  workspaceWidth = 320;
  await activateLink('.breadcrumbs a');
  assert.equal(document.querySelector('.library-workspace').dataset.layout, 'compact');
  assert.equal(resizeObservers.size, 1);
});

test("gallery arrow and Home End focus navigation does not change the selection", async () => {
  await mountWorkspace(galleryFixture);
  await clickElement('.asset-select');
  for (const mode of ['그리드', '목록']) {
    await changeGalleryMode(mode);
    const buttons = [...document.querySelectorAll('.asset-select')];
    buttons[0].focus();
    await key(buttons[0], 'ArrowDown');
    assert.equal(document.activeElement, buttons[1]);
    await key(buttons[1], 'ArrowRight');
    assert.equal(document.activeElement, buttons[1]);
    await key(buttons[1], 'Home');
    assert.equal(document.activeElement, buttons[0]);
    await key(buttons[0], 'End');
    assert.equal(document.activeElement, buttons[1]);
    await key(buttons[1], 'ArrowLeft');
    assert.equal(document.activeElement, buttons[0]);
    assert.equal(buttons[0].getAttribute('aria-pressed'), 'true');
    assert.equal(buttons[1].getAttribute('aria-pressed'), 'false');
  }
});

test("workspace measures on window resize when ResizeObserver is unavailable", async () => {
  await activateLink('[aria-label="주 메뉴"] a');
  const Observer = globalThis.ResizeObserver;
  try {
    globalThis.ResizeObserver = undefined;
    workspaceWidth = 320;
    await activateLink('.breadcrumbs a');
    assert.equal(document.querySelector('.library-workspace').dataset.layout, 'compact');
    workspaceWidth = 1100;
    dispatch(window, new dom.window.Event('resize'));
    await nextTick();
    assert.equal(document.querySelector('.library-workspace').dataset.layout, 'wide');
    assert.equal(resizeObservers.size, 0);
    await activateLink('[aria-label="주 메뉴"] a');
  } finally {
    globalThis.ResizeObserver = Observer;
  }
});

test("status bar starts absent without seeded jobs or fake progress", () => {
  assert.equal(document.querySelector('.app-status'), null);
  assert.equal(components.operations.length, 0);
});

test("actual theme command publishes success and keeps its result across routes", async () => {
  await activateLink('[aria-label="주 메뉴"] a');
  const radio = document.querySelector('input[value="light"]');
  radio.checked = true;
  dispatch(radio, new dom.window.Event('change', { bubbles: true }));
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  assert.equal(document.documentElement.dataset.theme, 'light');
  assert.match(document.querySelector('.app-status').textContent, /테마 변경: 완료/);
  assert.equal(components.operations.length, 1);
  await activateLink('.breadcrumbs a');
  assert.match(document.querySelector('.app-status').textContent, /테마 변경: 완료/);
  assert.equal(document.querySelector('.app-status progress'), null);
  await clickElement('.clear-operations');
  assert.equal(document.querySelector('.app-status'), null);
});

test("actual view change reports its own result and redundant clicks create no job", async () => {
  await changeGalleryMode('목록');
  assert.equal(components.libraryUi.galleryViewMode, 'list');
  assert.equal(components.operations.length, 1);
  assert.equal(components.operations[0].kind, 'gallery.view');
  assert.equal(components.operations[0].state, 'succeeded');
  assert.match(document.querySelector('.app-status').textContent, /갤러리 보기 변경: 완료/);
  await changeGalleryMode('목록');
  assert.equal(components.operations.length, 1);
  assert.equal(components.operations.some((operation) => operation.kind === 'analysis.run'), false);
});

test("measured operation events update concurrent counts and copy incoming progress", async () => {
  const progress = { processed: 1, total: 4 };
  assert.equal(components.receiveOperation({ id: 'fixture-scan', kind: 'library.scan', state: 'running', progress }), true);
  progress.processed = 4;
  assert.equal(components.operations[0].progress.processed, 1);
  assert.equal(components.receiveOperation({ id: 'fixture-analysis', kind: 'analysis.run', state: 'running' }), true);
  await nextTick();
  const bar = document.querySelector('.app-status progress');
  assert.equal(bar.value, 1);
  assert.equal(bar.max, 4);
  assert.equal(bar.getAttribute('aria-label'), '파일 스캔 처리 건수');
  assert.match(document.querySelector('.app-status').textContent, /1 \/ 4/);
  components.receiveOperation({ id: 'fixture-scan', kind: 'library.scan', state: 'succeeded', progress: { processed: 4, total: 4 } });
  components.receiveOperation({ id: 'fixture-analysis', kind: 'analysis.run', state: 'cancelled' });
  await nextTick();
  assert.match(document.querySelector('.app-status').textContent, /파일 스캔: 완료/);
  assert.match(document.querySelector('.app-status').textContent, /AI 분석: 취소됨/);
  assert.equal(components.operations.length, 2);
});

test("operation receiver rejects invalid, regressive and stale event state", () => {
  for (const event of [
    { id: '', kind: 'library.scan', state: 'running' },
    { id: 'fixture-invalid', kind: '__proto__', state: 'running' },
    { id: 'fixture-invalid', kind: 'library.scan', state: 'unknown' },
    ...[{ processed: -1, total: 4 }, { processed: 5, total: 4 }, { processed: 0, total: -1 },
      { processed: NaN, total: 4 }, { processed: 0.5, total: 4 }].map((progress) =>
      ({ id: 'fixture-invalid', kind: 'library.scan', state: 'running', progress })),
  ]) assert.equal(components.receiveOperation(event), false);
  assert.equal(components.operations.length, 0);
  const event = { id: 'fixture-valid', kind: 'library.scan', state: 'running', progress: { processed: 2, total: 4 } };
  assert.equal(components.receiveOperation(event), true);
  assert.equal(components.receiveOperation({ ...event, kind: 'unity.apply' }), false);
  assert.equal(components.receiveOperation({ ...event, progress: { processed: 1, total: 4 } }), false);
  assert.equal(components.receiveOperation({ ...event, progress: { processed: 2, total: 5 } }), false);
  assert.equal(components.receiveOperation({ ...event, state: 'succeeded' }), false);
  assert.equal(components.receiveOperation({ id: event.id, kind: event.kind, state: 'succeeded' }), false);
  assert.equal(components.receiveOperation({ ...event, state: 'succeeded', progress: { processed: 4, total: 4 } }), true);
  assert.equal(components.receiveOperation(event), false);
  assert.equal(components.operations[0].state, 'succeeded');
});

test("unknown error data never appears in alerts, records or DOM attributes", async () => {
  const secret = 'fixture-private-path-and-api-key-<img src=x>';
  components.receiveOperation({ id: 'fixture-private-error', kind: 'unity.apply', state: 'failed',
    errorCode: secret, message: secret, path: secret });
  await nextTick();
  assert.equal(document.querySelector('[role="alert"]').textContent, 'Unity 적용: 작업을 완료하지 못했습니다.');
  assert.equal(document.body.innerHTML.includes(secret), false);
  assert.equal(JSON.stringify(components.operations).includes(secret), false);
  assert.equal(document.querySelector('img'), null);
  assert.equal(document.querySelector('.clear-operations'), null);
});

test("command wrapper stays running until a real callback settles and invokes it once", async () => {
  let complete;
  let calls = 0;
  const completion = new Promise((resolve) => { complete = resolve; });
  const command = components.executeUiCommand('gallery.view', () => { calls++; return completion; });
  await nextTick();
  assert.equal(calls, 1);
  assert.match(document.querySelector('.app-status').textContent, /갤러리 보기 변경: 진행 중/);
  assert.equal(document.querySelector('.clear-operations'), null);
  complete();
  assert.equal(await command, true);
  await nextTick();
  assert.equal(components.operations[0].state, 'succeeded');
  assert.equal(calls, 1);
});

test("command failure is redacted, dismissible and never automatically retried", async () => {
  let calls = 0;
  const secret = 'fixture-exception-secret-C:/private/data';
  const result = await components.executeUiCommand('appearance.change', () => { calls++; throw new Error(secret); });
  await nextTick();
  assert.equal(result, false);
  assert.equal(components.operations[0].state, 'failed');
  assert.match(document.querySelector('[role="alert"]').textContent, /테마 변경: 작업을 완료하지 못했습니다/);
  assert.equal(document.body.textContent.includes(secret), false);
  assert.equal(JSON.stringify(components.operations).includes(secret), false);
  await clickElement('.operation-error button');
  assert.equal(document.querySelector('[role="alert"]'), null);
  await clickElement('.clear-operations');
  assert.equal(document.querySelector('.app-status'), null);
  assert.equal(calls, 1);
});

test("clearing completed states preserves active work and undismissed errors", async () => {
  components.receiveOperation({ id: 'fixture-running', kind: 'library.scan', state: 'running', progress: { processed: 1, total: 3 } });
  components.receiveOperation({ id: 'fixture-failed', kind: 'analysis.run', state: 'failed', errorCode: 'CORE_UNAVAILABLE' });
  components.receiveOperation({ id: 'fixture-done', kind: 'gallery.view', state: 'succeeded' });
  await nextTick();
  await clickElement('.clear-operations');
  assert.equal(components.operations.length, 2);
  await activateLink('[aria-label="주 메뉴"] a');
  assert.match(document.querySelector('[role="alert"]').textContent, /Core에 연결할 수 없습니다/);
  assert.match(document.querySelector('.app-status').textContent, /1 \/ 3/);
  components.receiveOperation({ id: 'fixture-running', kind: 'library.scan', state: 'cancelled' });
  await nextTick();
  assert.match(document.querySelector('.app-status').textContent, /파일 스캔: 취소됨/);
});

test("event history is bounded without evicting active work or unacknowledged errors", () => {
  for (let index = 0; index < components.MAX_OPERATIONS; index++) {
    assert.equal(components.receiveOperation({ id: `fixture-cap-${index}`, kind: 'library.scan', state: 'running' }), true);
  }
  assert.equal(components.receiveOperation({ id: 'fixture-overflow', kind: 'library.scan', state: 'running' }), false);
  assert.equal(components.operations.length, components.MAX_OPERATIONS);
  components.receiveOperation({ id: 'fixture-cap-0', kind: 'library.scan', state: 'failed', errorCode: 'PERMISSION_DENIED' });
  assert.equal(components.receiveOperation({ id: 'fixture-overflow', kind: 'library.scan', state: 'running' }), false);
  components.dismissOperationAlert('fixture-cap-0');
  assert.equal(components.receiveOperation({ id: 'fixture-overflow', kind: 'library.scan', state: 'running' }), true);
  assert.equal(components.operations.length, components.MAX_OPERATIONS);
  assert.equal(components.operations.some((operation) => operation.id === 'fixture-cap-0'), false);
});

test("zero-target completion displays measured zero counts without inventing a progress maximum", async () => {
  assert.equal(components.receiveOperation({ id: 'fixture-empty-scan', kind: 'library.scan', state: 'succeeded',
    progress: { processed: 0, total: 0 } }), true);
  await nextTick();
  assert.match(document.querySelector('.app-status').textContent, /파일 스캔: 완료/);
  assert.match(document.querySelector('.app-status').textContent, /0 \/ 0/);
  assert.equal(document.querySelector('.app-status progress'), null);
});

async function mountConnection(invoke) {
  app.unmount();
  dom.window.__TAURI_INTERNALS__ = { invoke };
  globalThis.isTauri = true;
  app = createApp(components.CoreConnection);
  app.config.errorHandler = (error) => errors.push(error);
  app.mount('#app');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
}

test('browser mode does not pretend to connect to Core', () => {
  assert.equal(document.querySelector('.core-connection'), null);
});

function fixtureHealth(database = { status: 'not_configured' }) {
  return { request_id: '12345678-1234-4234-9234-123456789abc', ok: true, error: null,
    timestamp: '2026-10-28T00:00:00Z', data: { core: { status: 'ready', version: 'fixture-0.5', pid: 123, uptime_ms: 10 }, database } };
}

test('desktop connection displays only the supplied successful health response', async () => {
  const commands = [];
  await mountConnection(async (command) => {
    commands.push(command);
    return fixtureHealth();
  });
  assert.match(document.querySelector('.core-connection').textContent, /Core 연결됨 · fixture-0.5 · DB 미연결/);
  await clickElement('.core-connection button');
  await nextTick();
  assert.deepEqual(commands, ['core_health', 'core_health']);
});

test('desktop failure is redacted and explicit reconnect requests a fresh session', async () => {
  const commands = [];
  await mountConnection(async (command) => {
    commands.push(command);
    if (command === 'core_health') throw new Error('fixture-private-key-path');
    return fixtureHealth();
  });
  assert.equal(document.querySelector('.core-connection button').textContent.trim(), '다시 연결');
  assert.equal(document.body.textContent.includes('fixture-private-key-path'), false);
  await clickElement('.core-connection button');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  assert.deepEqual(commands, ['core_health', 'core_reconnect']);
  assert.match(document.querySelector('.core-connection').textContent, /Core 연결됨/);
});

test('heartbeat detects Core exit and never automatically reconnects or starts analysis', async (t) => {
  const commands = [];
  await mountConnection(async (command) => {
    commands.push(command);
    if (commands.length > 1) throw 'CORE_EXITED';
    return fixtureHealth();
  });
  t.mock.timers.tick(5000);
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  assert.match(document.querySelector('.core-connection [role="alert"]').textContent, /Core가 종료되었습니다/);
  assert.match(document.querySelector('.core-connection [role="status"]').textContent, /연결 끊김/);
  t.mock.timers.tick(20000);
  await nextTick();
  assert.deepEqual(commands, ['core_health', 'core_health']);
  assert.equal(components.operations.length, 0);
});

test('DB errors preserve Core health but provide an explicit safe recovery action', async () => {
  await mountConnection(async () => fixtureHealth({ status: 'error', error_code: 'DATA_IN_USE' }));
  assert.match(document.querySelector('.core-connection [role="status"]').textContent, /Core 연결됨.*DB 연결 오류/);
  assert.match(document.querySelector('.core-connection [role="alert"]').textContent, /다른 Core가 이 데이터를 사용/);
  assert.equal(document.querySelector('.core-connection button').textContent.trim(), '다시 연결');
});

test('incomplete or invalid health cannot be presented as connected', async () => {
  for (const invalid of [null, { ok: true }, { ...fixtureHealth(), error: { message: 'fixture-private' } },
    fixtureHealth({ status: 'ready', schema_version: 0, sqlite_version: 'fixture', journal_mode: 'wal' })]) {
    await mountConnection(async () => invalid);
    assert.match(document.querySelector('.core-connection [role="status"]').textContent, /연결 끊김/);
    assert.match(document.querySelector('.core-connection [role="alert"]').textContent, /Core 응답을 확인할 수 없습니다/);
    assert.equal(document.body.textContent.includes('fixture-private'), false);
  }
});

test('heartbeat and manual checks cannot overlap and are disposed on unmount', async (t) => {
  let resolve;
  let calls = 0;
  await mountConnection(() => { calls++; return new Promise((done) => { resolve = done; }); });
  assert.equal(document.querySelector('.core-connection button').disabled, true);
  t.mock.timers.tick(10000);
  await clickElement('.core-connection button');
  assert.equal(calls, 1);
  app.unmount();
  mounted = false;
  resolve(fixtureHealth());
  await new Promise((done) => setImmediate(done));
  await nextTick();
  t.mock.timers.tick(20000);
  assert.equal(calls, 1);
  assert.equal(document.querySelector('.core-connection'), null);
});

async function mountFolderSelection(invoke) {
  app.unmount();
  dom.window.__TAURI_INTERNALS__ = { invoke };
  globalThis.isTauri = true;
  app = createApp(components.FolderSelection);
  app.config.errorHandler = (error) => errors.push(error);
  app.mount('#app');
  mounted = true;
  await nextTick();
}

async function clickFolderPicker() {
  await clickElement('.pick-folder');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
}

test('folder picker is unavailable in browser mode and never opens on mount', async () => {
  assert.equal(document.querySelector('.pick-folder'), null);
  const commands = [];
  await mountFolderSelection(async (command) => { commands.push(command); return null; });
  assert.ok(document.querySelector('.pick-folder'));
  assert.deepEqual(commands, []);
  assert.equal(components.folderDraft.path, null);
});

test('folder selection invokes only the fixed picker command and retains its supplied path', async () => {
  const commands = [];
  const path = 'C:\\fixture\\한글 에셋 폴더';
  await mountFolderSelection(async (command, args) => { commands.push([command, args]); return { path }; });
  await clickFolderPicker();
  assert.deepEqual(commands, [['select_library_folder', {}]]);
  assert.equal(components.folderDraft.path, path);
  assert.equal(document.querySelector('.picked-folder-path').textContent, path);
  assert.match(document.querySelector('[role="status"]').textContent, /폴더를 선택했습니다/);
  assert.equal(components.operations.length, 0);
});

test('cancelling the picker preserves the previous choice without an error', async () => {
  components.setPickedFolderPath('D:\\fixture\\previous');
  await mountFolderSelection(async () => null);
  await clickFolderPicker();
  assert.equal(components.folderDraft.path, 'D:\\fixture\\previous');
  assert.match(document.querySelector('[role="status"]').textContent, /취소했습니다/);
  assert.equal(document.querySelector('[role="alert"]'), null);
});

test('folder policy errors and raw exceptions use safe messages and keep the previous choice', async () => {
  components.setPickedFolderPath('D:\\fixture\\previous');
  for (const code of ['FOLDER_ROOT_NOT_ALLOWED', 'FOLDER_LOCAL_ONLY', 'FOLDER_UNAVAILABLE', new Error('fixture-secret-api-path')]) {
    await mountFolderSelection(async () => { throw code; });
    await clickFolderPicker();
    assert.ok(document.querySelector('[role="alert"]'));
    assert.equal(document.body.textContent.includes('fixture-secret-api-path'), false);
    assert.equal(components.folderDraft.path, 'D:\\fixture\\previous');
    if (code === 'FOLDER_ROOT_NOT_ALLOWED') assert.match(document.querySelector('[role="alert"]').textContent, /드라이브 전체 대신/);
    if (code === 'FOLDER_LOCAL_ONLY') assert.match(document.querySelector('[role="alert"]').textContent, /네트워크 위치/);
  }
});

test('folder picking suppresses duplicate requests and ignores late results after unmount', async () => {
  let resolve;
  let calls = 0;
  await mountFolderSelection(() => { calls++; return new Promise((done) => { resolve = done; }); });
  await clickElement('.pick-folder');
  assert.equal(document.querySelector('.pick-folder').disabled, true);
  await clickElement('.pick-folder');
  assert.equal(calls, 1);
  app.unmount();
  mounted = false;
  resolve({ path: 'C:\\fixture\\late' });
  await new Promise((done) => setImmediate(done));
  assert.equal(components.folderDraft.path, null);
});

test('selection path is literal text and clearing is a local action', async () => {
  let calls = 0;
  const path = 'C:\\fixture\\<img src=x onerror="alert(1)">';
  await mountFolderSelection(async () => { calls++; return { path }; });
  await clickFolderPicker();
  assert.equal(document.querySelector('.picked-folder-path').textContent, path);
  assert.equal(document.querySelectorAll('img, script').length, 0);
  await clickElement('.clear-folder-selection');
  assert.equal(components.folderDraft.path, null);
  assert.equal(document.querySelector('.picked-folder-path'), null);
  assert.equal(calls, 1);
});

test('invalid picker responses cannot replace a valid selection', async () => {
  components.setPickedFolderPath('D:\\fixture\\previous');
  for (const result of [{}, { path: 1 }, { path: 'relative-path' }, { path: 'file:///C:/fixture' }, { path: 'C:\\fixture\0bad' }]) {
    await mountFolderSelection(async () => result);
    await clickFolderPicker();
    assert.ok(document.querySelector('[role="alert"]'));
    assert.equal(components.folderDraft.path, 'D:\\fixture\\previous');
  }
});

test('actual workspace keeps an unregistered choice across routes without contacting Core on pick', async () => {
  app.unmount();
  const commands = [];
  globalThis.isTauri = true;
  dom.window.__TAURI_INTERNALS__ = { invoke: async (command) => {
    commands.push(command);
    if (command === 'core_health') return fixtureHealth();
    if (command === 'select_library_folder') return { path: 'D:\\fixture\\selected' };
    if (command === 'list_libraries') return { ok: true, error: null, data: { libraries: [], next_cursor: null } };
    return rejectTransport();
  } };
  app = createApp(components.App);
  app.config.errorHandler = (error) => errors.push(error);
  app.use(router);
  app.mount('#app');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  commands.length = 0;
  await clickFolderPicker();
  assert.deepEqual(commands, ['select_library_folder']);
  assert.equal(document.querySelectorAll('[data-folder-id]').length, 0);
  assert.equal(document.querySelector('.gallery-count').textContent, '0개 에셋');
  await activateLink('[aria-label="주 메뉴"] a');
  await activateLink('.breadcrumbs a');
  assert.equal(document.querySelector('.picked-folder-path').textContent, 'D:\\fixture\\selected');
  assert.equal(document.querySelectorAll('[data-folder-id]').length, 0);
});

const libraryFixture = [
  { id: '12345678-1234-4234-9234-123456789abc', name: '등록된 한글 폴더', path: 'D:\\fixture\\registered' },
  { id: '22345678-1234-4234-9234-123456789abc', name: '새 폴더', path: 'D:\\fixture\\new' },
];
test('gallery Ctrl and Shift selection persists across layouts and can clear', async()=>{
  await mountWorkspace([...galleryFixture,{id:'fixture-third',name:'세 번째.txt',kind:'TXT'}]);
  await clickElement('.asset-select');
  let buttons=[...document.querySelectorAll('.asset-select')];
  dispatch(buttons[1],new dom.window.MouseEvent('click',{bubbles:true,ctrlKey:true}));await nextTick();
  assert.equal(document.querySelector('.selection-count').textContent,'2개 선택');
  dispatch(buttons[2],new dom.window.MouseEvent('click',{bubbles:true,shiftKey:true}));await nextTick();
  assert.equal(document.querySelector('.selection-count').textContent,'2개 선택');
  await changeGalleryMode('목록');
  assert.equal(document.querySelectorAll('.asset-select[aria-pressed="true"]').length,2);
  const clear=[...document.querySelectorAll('.gallery-tools button')][0];
  dispatch(clear,new dom.window.MouseEvent('click',{bubbles:true}));await nextTick();
  assert.equal(document.querySelector('.selection-count').textContent,'0개 선택');
  assert.ok(document.querySelector('.detail-empty'));
});
test('gallery sorting and pagination bound rendering and retain supplied IDs',async()=>{
  const items=Array.from({length:61},(_,index)=>({id:`fixture-page-${index}`,name:String(100-index),kind:'TXT'}));
  await mountGallery(items);
  assert.equal(document.querySelectorAll('.asset-card').length,60);
  const next=[...document.querySelectorAll('[aria-label="에셋 페이지"] button')][1];
  dispatch(next,new dom.window.MouseEvent('click',{bubbles:true}));await nextTick();
  assert.equal(document.querySelectorAll('.asset-card').length,1);
  const sort=document.querySelector('[aria-label="에셋 정렬"]');sort.value='name';
  dispatch(sort,new dom.window.Event('change',{bubbles:true}));await nextTick();
  assert.equal(document.querySelectorAll('.asset-card').length,60);
  assert.equal(document.querySelector('.asset-card').dataset.assetId,[...items].sort((a,b)=>a.name.localeCompare(b.name,'ko')||a.id.localeCompare(b.id))[0].id);
});
test('selected asset metadata renders measured values and a missing file state', async () => {
  app.unmount();
  globalThis.isTauri=true;
  let missing=false;
  dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{
    assert.equal(command,'get_asset');
    return {ok:true,data:missing?{availability:'missing',path:'D:\\fixture\\missing.png'}:
      {availability:'present',path:'D:\\fixture\\a.png',size:123,modified:1700000000000,width:200,height:120}};
  }};
  const selected=ref({id:'fixture-metadata-a',name:'a.png',kind:'PNG',path:'D:\\fixture\\a.png'});
  app=createApp({render:()=>h(components.AssetMetadata,{asset:selected.value})});
  app.mount('#app');
  await new Promise((resolve)=>setImmediate(resolve)); await nextTick();
  assert.match(document.body.textContent,/123 바이트/);
  assert.match(document.body.textContent,/200 × 120/);
  missing=true;
  selected.value={...selected.value,id:'fixture-metadata-b'};
  await nextTick(); await new Promise((resolve)=>setImmediate(resolve)); await nextTick();
  assert.match(document.body.textContent,/파일이 없습니다/);
  assert.doesNotMatch(document.body.textContent,/123 바이트/);
});
test('thumbnail loads only after visibility and accepts only a JPEG data URL', async () => {
  app.unmount();
  const previous = globalThis.IntersectionObserver;
  let visible;
  let calls = 0;
  globalThis.IntersectionObserver = class { constructor(callback) { visible=callback; } observe() {} disconnect() {} };
  globalThis.isTauri = true;
  dom.window.__TAURI_INTERNALS__ = {invoke:async (command) => {
    assert.equal(command,'asset_thumbnail'); calls++;
    return {ok:true,data:{status:'ready',url:'data:image/jpeg;base64,/9j/AA=='}};
  }};
  try {
    app=createApp(components.AssetThumbnail,{id:'fixture-thumbnail',kind:'PNG'});
    app.mount('#app');
    assert.equal(calls,0);
    visible([{isIntersecting:true}]);
    await new Promise((resolve)=>setImmediate(resolve));
    await nextTick();
    assert.equal(calls,1);
    assert.match(document.querySelector('img').src,/^data:image\/jpeg;base64,/);
  } finally { app.unmount(); mounted=false; globalThis.IntersectionObserver=previous; }
});
test('indexed folder hierarchy and filtering use whole path segments', () => {
  const items = [
    {id:'fixture-a',name:'a',kind:'TXT',libraryId:libraryFixture[0].id,relativePath:'one\\nested\\a.txt'},
    {id:'fixture-b',name:'b',kind:'TXT',libraryId:libraryFixture[0].id,relativePath:'one-more\\b.txt'},
  ];
  const nodes = components.folderNodes(libraryFixture, items);
  const folder = nodes[0].children.find((node) => node.name === 'one');
  assert.equal(folder.children[0].name, 'nested');
  assert.deepEqual(components.filterFolder(items, folder.id).map((item) => item.id), ['fixture-a']);
  assert.equal(components.filterFolder(items, null).length, 2);
  assert.equal(components.filterFolder(items, 'folder:invalid').length, 0);
});
const libraryEnvelope = (data) => ({ ok: true, error: null, data });

async function mountLibraryWorkspace(invoke) {
  globalThis.isTauri = true;
  dom.window.__TAURI_INTERNALS__ = { invoke: (command,args) => command==='list_assets' ? Promise.resolve(libraryEnvelope({items:[],next_cursor:null})) : invoke(command,args) };
  await mountWorkspace([]);
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
}

test('persisted library list renders supplied roots and no pretend scanned assets', async () => {
  const commands = [];
  await mountLibraryWorkspace(async (command, args) => {
    commands.push([command, args]);
    return libraryEnvelope({ libraries: [libraryFixture[0]], next_cursor: null });
  });
  assert.deepEqual(commands, [['list_libraries', { afterId: null }]]);
  assert.equal(document.querySelector('[data-folder-id]').dataset.folderId, libraryFixture[0].id);
  assert.equal(document.querySelector('[data-folder-id] .folder-name').textContent, libraryFixture[0].name);
  assert.equal(document.querySelector('.gallery-count').textContent, '0개 에셋');
  assert.equal(document.querySelector('.library-empty'), null);
});

test('explicit registration and unregister update the real tree selection without scanning', async () => {
  const commands = [];
  let registered = false;
  await mountLibraryWorkspace(async (command, args) => {
    commands.push([command, args]);
    if (command === 'list_libraries') return libraryEnvelope({ libraries: [], next_cursor: null });
    if (command === 'select_library_folder') return { path: libraryFixture[1].path };
    if (command === 'register_library') {
      const created = !registered;
      registered = true;
      return libraryEnvelope({ library: libraryFixture[1], created });
    }
    if (command === 'unregister_library') return libraryEnvelope({ library_id: args.libraryId, enabled: false });
    return rejectTransport();
  });
  await clickFolderPicker();
  assert.equal(document.querySelectorAll('[data-folder-id]').length, 0);
  await clickElement('.register-library');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  assert.equal(document.querySelector('[data-folder-id]').dataset.folderId, libraryFixture[1].id);
  await clickElement('.register-library');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  assert.equal(document.querySelectorAll('[data-folder-id]').length, 1);
  await clickElement('[data-folder-id]');
  assert.equal(components.libraryUi.selectedFolderId, libraryFixture[1].id);
  await clickElement('.unregister-library');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  assert.equal(components.libraryUi.selectedFolderId, null);
  assert.equal(document.querySelector('[data-folder-id]'), null);
  assert.match(document.querySelector('.library-management').textContent, /원본 파일은 유지됩니다/);
  assert.deepEqual(commands.map(([command]) => command), ['list_libraries', 'select_library_folder', 'register_library', 'register_library', 'unregister_library']);
  assert.deepEqual(commands[2][1], { path: libraryFixture[1].path });
});

test('failed writes keep the last confirmed library and redact raw transport failures', async () => {
  await mountLibraryWorkspace(async (command) => {
    if (command === 'list_libraries') return libraryEnvelope({ libraries: [libraryFixture[0]], next_cursor: null });
    if (command === 'register_library') return { ok: false, data: null, error: { code: 'LIBRARY_OVERLAP' } };
    if (command === 'unregister_library') throw new Error('fixture-secret-db-path');
    return rejectTransport();
  });
  assert.equal(await components.registerLibrary(libraryFixture[1].path), false);
  await nextTick();
  assert.match(document.querySelector('.library-management [role="alert"]').textContent, /범위가 겹칩니다/);
  await clickElement('[data-folder-id]');
  await clickElement('.unregister-library');
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
  assert.ok(document.querySelector('[data-folder-id]'));
  assert.equal(components.libraryUi.selectedFolderId, libraryFixture[0].id);
  assert.equal(document.body.textContent.includes('fixture-secret-db-path'), false);
  assert.match(document.querySelector('.library-management [role="alert"]').textContent, /처리 결과를 확인하지 못했습니다/);
});

test('list failures do not claim an empty database and preserve confirmed roots on refresh failure', async () => {
  let fail = true;
  await mountLibraryWorkspace(async () => {
    if (fail) throw 'DB_UNAVAILABLE';
    return libraryEnvelope({ libraries: [libraryFixture[0]], next_cursor: null });
  });
  assert.equal(document.querySelector('.library-empty').textContent, '등록 폴더를 확인하지 못했습니다.');
  fail = false;
  assert.equal(await components.refreshLibraries(), true);
  await nextTick();
  fail = true;
  assert.equal(await components.refreshLibraries(), false);
  await nextTick();
  assert.ok(document.querySelector('[data-folder-id]'));
  assert.match(document.querySelector('.library-management [role="alert"]').textContent, /DB를 사용할 수 없습니다/);
});

test('library pages merge once and malformed cursors cannot publish partial or duplicate roots', async () => {
  const cursors = [];
  await mountLibraryWorkspace(async (command, args) => {
    cursors.push(args.afterId);
    return libraryEnvelope(args.afterId === null ? { libraries: [libraryFixture[0]], next_cursor: libraryFixture[0].id }
      : { libraries: [libraryFixture[1]], next_cursor: null });
  });
  assert.deepEqual(cursors, [null, libraryFixture[0].id]);
  assert.equal(document.querySelectorAll('[data-folder-id]').length, 2);
  dom.window.__TAURI_INTERNALS__.invoke = async () => libraryEnvelope({ libraries: [libraryFixture[0]], next_cursor: libraryFixture[0].id });
  assert.equal(await components.refreshLibraries(), false);
  await nextTick();
  assert.equal(document.querySelectorAll('[data-folder-id]').length, 2);
});

test('registration cannot overlap and session reset ignores late write responses', async () => {
  let complete;
  let writes = 0;
  await mountLibraryWorkspace(async (command) => {
    if (command === 'list_libraries') return libraryEnvelope({ libraries: [], next_cursor: null });
    if (command === 'register_library') { writes++; return new Promise((resolve) => { complete = resolve; }); }
    return rejectTransport();
  });
  const pending = components.registerLibrary(libraryFixture[1].path);
  assert.equal(await components.registerLibrary(libraryFixture[1].path), false);
  assert.equal(await components.unregisterLibrary('guessed-library-id'), false);
  assert.equal(writes, 1);
  components.resetLibrarySession();
  complete(libraryEnvelope({ library: libraryFixture[1], created: true }));
  assert.equal(await pending, false);
  assert.equal(components.libraries.roots.length, 0);
  assert.equal(components.libraries.mutating, false);
});

test('a fresh UI session reloads stored library IDs and renders names as literal text', async () => {
  const record = { ...libraryFixture[0], name: '<img src=x onerror="alert(1)">' };
  const invoke = async () => libraryEnvelope({ libraries: [record], next_cursor: null });
  await mountLibraryWorkspace(invoke);
  assert.equal(document.querySelector('.folder-name').textContent, record.name);
  assert.equal(document.querySelector('img'), null);
  components.resetLibrarySession();
  await mountLibraryWorkspace(invoke);
  assert.equal(document.querySelector('[data-folder-id]').dataset.folderId, record.id);
  assert.equal(document.querySelectorAll('[data-folder-id]').length, 1);
});

async function mountAnnotations(invoke) {
  app.unmount(); globalThis.isTauri = true;
  dom.window.__TAURI_INTERNALS__ = {invoke};
  app = createApp(components.AssetAnnotations, {assetId:'12345678-1234-4234-9234-123456789abc'});
  app.config.errorHandler = error => errors.push(error); app.mount('#app');
  await new Promise(resolve => setImmediate(resolve)); await nextTick();
}
test('user tags load, submit and delete through fixed Core commands', async () => {
  const calls=[];
  await mountAnnotations(async (command, args) => {
    calls.push([command,args]);
    return {ok:true,data:{tags:command==='asset_annotations'?['old']:args.add}};
  });
  assert.match(document.querySelector('.user-annotations').textContent,/old/);
  const input=document.querySelector('.tag-form input'); input.value='숲';
  dispatch(input,new Event('input',{bubbles:true})); await nextTick();
  dispatch(document.querySelector('.tag-form'),new Event('submit',{bubbles:true,cancelable:true}));
  await new Promise(resolve => setImmediate(resolve)); await nextTick();
  assert.deepEqual(calls[1][1].add,['숲']);
  dispatch(document.querySelector('.user-annotations li button'),new MouseEvent('click',{bubbles:true}));
  await new Promise(resolve => setImmediate(resolve)); await nextTick();
  assert.deepEqual(calls.filter(c=>c[0]==='edit_asset_tags')[1][1].remove,['숲']);
  assert.equal(document.querySelectorAll('.user-annotations li').length,0);
});
test('user tag write failure is visible and keeps saved tags', async () => {
  await mountAnnotations(async command => ({ok:command==='asset_annotations',data:{tags:['saved']}}));
  dispatch(document.querySelector('.user-annotations li button'),new MouseEvent('click',{bubbles:true}));
  await new Promise(resolve => setImmediate(resolve)); await nextTick();
  assert.match(document.querySelector('[role=alert]').textContent,/저장하지 못/);
  assert.match(document.querySelector('.user-annotations li').textContent,/saved/);
});

test('user title and description load and save explicitly', async () => {
  const calls=[];
  await mountAnnotations(async (command,args) => {calls.push([command,args]); return {ok:true,data:{tags:[],title:'별칭',description:'설명'}};});
  const input=document.querySelector('.annotation-form input');
  assert.equal(input.value,'별칭'); assert.equal(document.querySelector('textarea').value,'설명');
  input.value='나무'; dispatch(input,new Event('input',{bubbles:true})); await nextTick();
  assert.equal(calls.length,1);
  dispatch(document.querySelector('.annotation-form'),new Event('submit',{bubbles:true,cancelable:true}));
  await new Promise(resolve=>setImmediate(resolve)); await nextTick();
  assert.equal(calls[1][0],'save_asset_annotation'); assert.equal(calls[1][1].title,'나무');
  assert.match(document.querySelector('.annotation-form').textContent,/저장했습니다/);
});

test('basic text separates original name and aliases and only submits on save', async () => {
  const calls=[];
  await mountAnnotations(async (command,args) => {
    calls.push([command,args]);
    return {ok:true,data:{tags:[],title:'display',description:'notes',aliases:['Tree','숲'],originalName:'<img src=x>.png',revision:3}};
  });
  assert.match(document.querySelector('.original-name').textContent,/<img src=x>\.png/);
  assert.equal(document.querySelector('.original-name img'),null);
  const aliases=document.querySelector('.alias-input');
  assert.equal(aliases.value,'Tree\n숲'); aliases.value='별칭\n second ';
  dispatch(aliases,new Event('input',{bubbles:true})); await nextTick();
  assert.equal(calls.length,1);
  dispatch(document.querySelector('.annotation-form'),new Event('submit',{bubbles:true,cancelable:true}));
  await new Promise(resolve=>setImmediate(resolve)); await nextTick();
  assert.deepEqual(calls[1],['save_asset_annotation',{assetId:'12345678-1234-4234-9234-123456789abc',title:'display',description:'notes',aliases:['별칭','second'],expectedRevision:3}]);
  assert.equal(document.querySelector('.annotation-form input').maxLength,128);
  assert.equal(document.querySelector('.annotation-form textarea').maxLength,1024);
});

test('basic text conflict preserves draft and requires explicit discard before reloading', async () => {
  const calls=[];
  await mountAnnotations(async (command,args) => {
    calls.push([command,args]);
    return command==='asset_annotations'?{ok:true,data:{tags:[],title:'server',aliases:['stored'],revision:2}}:
      {ok:false,error:{code:'METADATA_CONFLICT',message:'PRIVATE raw error'}};
  });
  const aliases=document.querySelector('.alias-input'); aliases.value='unsaved';
  dispatch(aliases,new Event('input',{bubbles:true}));
  dispatch(document.querySelector('.annotation-form'),new Event('submit',{bubbles:true,cancelable:true}));
  await new Promise(resolve=>setImmediate(resolve));await nextTick();
  assert.equal(aliases.value,'unsaved');assert.equal(document.querySelector('.annotation-form button').disabled,true);
  assert.doesNotMatch(document.body.textContent,/PRIVATE/);
  assert.equal(calls.length,2);
  const reload=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('초안을 버리고'));
  dispatch(reload,new MouseEvent('click',{bubbles:true}));
  await new Promise(resolve=>setImmediate(resolve));await nextTick();
  assert.equal(document.querySelector('.alias-input').value,'stored');assert.equal(calls.length,3);
});

test('basic text save failure preserves draft and successful save advances revision', async () => {
  const calls=[];let attempt=0;
  await mountAnnotations(async (command,args) => {
    calls.push([command,args]);
    if(command==='asset_annotations')return {ok:true,data:{tags:[],aliases:['stored'],revision:4}};
    if(command==='save_asset_annotation')return ++attempt===1?{ok:false,error:{code:'INVALID_PARAMS',message:'PRIVATE'}}:
      {ok:true,data:{aliases:['normalized'],revision:5}};
    return {ok:true,data:{items:[],next_cursor:null}};
  });
  const aliases=document.querySelector('.alias-input');aliases.value='draft';dispatch(aliases,new Event('input',{bubbles:true}));
  const submit=async()=>{dispatch(document.querySelector('.annotation-form'),new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setImmediate(r));await nextTick();};
  await submit();assert.equal(aliases.value,'draft');assert.doesNotMatch(document.body.textContent,/PRIVATE/);
  await submit();assert.equal(aliases.value,'normalized');
  await submit();assert.equal(calls.filter(c=>c[0]==='save_asset_annotation')[2][1].expectedRevision,5);
});

test('basic text ignores a late save result after changing selection', async () => {
  app.unmount();globalThis.isTauri=true;let finish;
  dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>command==='save_asset_annotation'?new Promise(r=>{finish=r;}):
    {ok:true,data:{tags:[],title:args.assetId,aliases:[args.assetId],originalName:args.assetId+'.png',revision:0}}};
  const props=ref({assetId:'first'});app=createApp({render:()=>h(components.AssetAnnotations,props.value)});
  app.config.errorHandler=error=>errors.push(error);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
  dispatch(document.querySelector('.annotation-form'),new Event('submit',{bubbles:true,cancelable:true}));await nextTick();
  props.value={assetId:'second'};await nextTick();await new Promise(r=>setImmediate(r));await nextTick();
  finish({ok:true,data:{aliases:['old-result'],revision:9}});await new Promise(r=>setImmediate(r));await nextTick();
  assert.equal(document.querySelector('.alias-input').value,'second');assert.match(document.querySelector('.original-name').textContent,/second.png/);
  assert.doesNotMatch(document.body.textContent,/저장했습니다/);
});

test('gallery multi-selection submits only selected asset IDs for batch tags', async () => {
  const calls=[];
  await mountGallery([{id:'first',name:'one',kind:'TXT'},{id:'second',name:'two',kind:'TXT'}]);
  globalThis.isTauri=true;
  dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
    calls.push([command,args]);
    if(command==='list_assets')return {ok:true,data:{items:[],next_cursor:null}};
    return {ok:true,data:{updated:args.assetIds.length}};
  }};
  const buttons=document.querySelectorAll('.asset-select');
  dispatch(buttons[0],new MouseEvent('click',{bubbles:true}));
  dispatch(buttons[1],new MouseEvent('click',{bubbles:true,ctrlKey:true})); await nextTick();
  const input=document.querySelector('.bulk-tags input'); input.value='한글';
  dispatch(input,new Event('input',{bubbles:true})); await nextTick();
  dispatch(document.querySelector('.bulk-tags'),new Event('submit',{bubbles:true,cancelable:true}));
  await new Promise(resolve=>setImmediate(resolve)); await nextTick();
  assert.deepEqual(calls[0],['batch_asset_tags',{assetIds:['first','second'],add:['한글'],remove:[]}]);
  assert.match(document.querySelector('.bulk-tags').textContent,/2개 에셋의 사용자 태그/);
});

test('keyword matching handles Korean, case, whitespace and original filename with overrides', () => {
  const items=[{id:'a',name:'별칭',relativePath:'나무 Forest.png',kind:'PNG',userTags:['초록 숲']},
    {id:'b',name:'바위.png',kind:'PNG',userTags:['돌']}];
  assert.deepEqual(components.keywordFilter(items,'  숲   FOREST ').map(i=>i.id),['a']);
  assert.deepEqual(components.keywordFilter(items,'나무').map(i=>i.id),['a']);
  assert.equal(components.keywordFilter(items,'없는').length,0);
  assert.deepEqual(components.keywordFilter(items,'','돌').map(i=>i.id),['b']);
});
test('global query and tag selection reduce actual gallery cards', async () => {
  await mountWorkspace([{id:'a',name:'나무.png',kind:'PNG',userTags:['숲']},{id:'b',name:'돌.png',kind:'PNG',userTags:['돌']}]);
  components.setSearchQuery('나무'); await nextTick();
  assert.equal(document.querySelectorAll('.asset-card').length,1);
  assert.match(document.querySelector('.asset-card').textContent,/나무/);
  components.setSearchQuery(''); await nextTick();
  const select=document.querySelector('[aria-label="사용자 태그 필터"]'); select.value='돌';
  dispatch(select,new Event('change',{bubbles:true})); await nextTick();
  assert.equal(document.querySelectorAll('.asset-card').length,1);
  assert.match(document.querySelector('.asset-card').textContent,/돌/);
});

test('workspace uses local Core search IDs for description matches and ignores stale results', async () => {
  await mountWorkspace([{id:'a',name:'one.txt',kind:'TXT'},{id:'b',name:'two.txt',kind:'TXT'}]);
  globalThis.isTauri=true; let first;
  dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
    assert.equal(command,'search_assets');
    if(args.query==='first')return new Promise(resolve=>{first=resolve;});
    return {ok:true,data:{ids:['b'],next_cursor:null}};
  }};
  components.setSearchQuery('first'); await nextTick();
  components.setSearchQuery('설명'); await nextTick();
  await new Promise(resolve=>setImmediate(resolve)); await nextTick();
  assert.equal(document.querySelectorAll('.asset-card').length,1);
  assert.match(document.querySelector('.asset-card').textContent,/two/);
  first({ok:true,data:{ids:['a'],next_cursor:null}});
  await new Promise(resolve=>setImmediate(resolve)); await nextTick();
  assert.match(document.querySelector('.asset-card').textContent,/two/);
});
test('Core search failure reports fallback rather than claiming a full result', async () => {
  await mountWorkspace([{id:'a',name:'나무.txt',kind:'TXT'}]);
  globalThis.isTauri=true; dom.window.__TAURI_INTERNALS__={invoke:async()=>{throw new Error('fixture private');}};
  components.setSearchQuery('나무'); await nextTick();
  await new Promise(resolve=>setImmediate(resolve)); await nextTick();
  assert.match(document.querySelector('[role=alert]').textContent,/전문 검색을 완료하지 못/);
  assert.equal(document.querySelectorAll('.asset-card').length,1);
  assert.doesNotMatch(document.body.textContent,/fixture private/);
});

test('combined query, tag, folder, type and analysis filters preserve failed reanalysis success', async () => {
  const fixtures=[
    {id:'a',name:'나무.png',kind:'PNG',libraryId:'root',relativePath:'숲/나무.png',userTags:['초록'],hasActiveResult:true,lastAttemptState:'failed'},
    {id:'b',name:'나무.fbx',kind:'FBX',libraryId:'root',relativePath:'숲/나무.fbx',userTags:['초록'],hasActiveResult:true},
    {id:'c',name:'나무.png',kind:'PNG',libraryId:'root',relativePath:'밖/나무.png',userTags:['초록'],hasActiveResult:true},
    {id:'d',name:'나무.png',kind:'PNG',libraryId:'root',relativePath:'숲/나무.png',userTags:['초록'],hasActiveResult:false,lastAttemptState:'failed'}];
  await mountWorkspace(fixtures);
  components.selectLibraryFolder('folder:'+JSON.stringify(['root','숲']));
  components.setSearchQuery('나무'); await nextTick();
  for(const [name,value] of [['사용자 태그 필터','초록'],['타입 필터','PNG'],['분석 상태 필터','completed']]){
    const select=document.querySelector(`[aria-label="${name}"]`);select.value=value;
    dispatch(select,new Event('change',{bubbles:true}));await nextTick();
  }
  assert.deepEqual([...document.querySelectorAll('.asset-card')].map(node=>node.dataset.assetId),['a']);
  const status=document.querySelector('[aria-label="분석 상태 필터"]');status.value='failed';
  dispatch(status,new Event('change',{bubbles:true})); await nextTick();
  assert.deepEqual([...document.querySelectorAll('.asset-card')].map(node=>node.dataset.assetId),['a','d']);
  status.value='unanalyzed';dispatch(status,new Event('change',{bubbles:true}));await nextTick();
  assert.deepEqual([...document.querySelectorAll('.asset-card')].map(node=>node.dataset.assetId),['d']);
});
test('sort uses exact nanosecond values, analysis dates and stable names', async () => {
  const fixtures=[{id:'a',name:'A',kind:'PNG',mtimeNs:'1700000000000000001',lastAnalysisAt:'2026-10-28T00:00:00Z'},
    {id:'b',name:'B',kind:'TXT',mtimeNs:'1700000000000000002',lastAnalysisAt:null},
    {id:'c',name:'C',kind:'PNG',mtimeNs:'1',lastAnalysisAt:'2026-10-28T01:00:00Z'}];
  assert.deepEqual(components.sortAssets(fixtures,'modified').map(i=>i.id),['b','a','c']);
  assert.deepEqual(components.sortAssets(fixtures,'analysis').map(i=>i.id),['c','a','b']);
  await mountGallery(fixtures);
  const select=document.querySelector('[aria-label="에셋 정렬"]');select.value='modified';
  dispatch(select,new Event('change',{bubbles:true}));await nextTick();
  assert.deepEqual([...document.querySelectorAll('.asset-card')].map(node=>node.dataset.assetId),['b','a','c']);
});

test('metadata edits during a list refresh queue a fresh read instead of losing updates', async () => {
  globalThis.isTauri=true; let finish; let calls=0;
  dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{
    assert.equal(command,'list_assets'); calls++;
    if(calls===1)return new Promise(resolve=>{finish=resolve;});
    return {ok:true,data:{items:[{id:'saved',name:'saved',kind:'TXT',userTags:['new']}],next_cursor:null}};
  }};
  const pending=components.refreshAssets(); await components.refreshAssets();
  finish({ok:true,data:{items:[],next_cursor:null}}); await pending;
  assert.equal(calls,2);assert.deepEqual([...components.assets.items[0].userTags],['new']);
});

test('failed metadata load blocks blank saves and can be retried', async () => {
  let calls=0;
  await mountAnnotations(async()=>{calls++;return {ok:calls>1,data:{tags:[],title:'preserved'}};});
  assert.equal(document.querySelector('.annotation-form button').disabled,true);
  const retry=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('다시 불러오기'));
  dispatch(retry,new MouseEvent('click',{bubbles:true}));
  await new Promise(resolve=>setImmediate(resolve)); await nextTick();
  assert.equal(document.querySelector('.annotation-form input').value,'preserved');
  assert.equal(document.querySelector('.annotation-form button').disabled,false);
});
test('tag refresh preserves an unsaved title draft', async () => {
  app.unmount();globalThis.isTauri=true;
  dom.window.__TAURI_INTERNALS__={invoke:async()=>({ok:true,data:{tags:['old'],title:'saved'}})};
  const props=ref({assetId:'12345678-1234-4234-9234-123456789abc',userTags:['old']});
  app=createApp({render:()=>h(components.AssetAnnotations,props.value)});
  app.config.errorHandler=error=>errors.push(error);app.mount('#app');
  await new Promise(resolve=>setImmediate(resolve));await nextTick();
  const input=document.querySelector('.annotation-form input');input.value='draft';
  dispatch(input,new Event('input',{bubbles:true}));await nextTick();
  props.value={...props.value,userTags:['new']};await nextTick();
  assert.equal(document.querySelector('.annotation-form input').value,'draft');
  assert.match(document.querySelector('.user-annotations li').textContent,/new/);
});

test('model registry loads actual supplied profiles and registers only on submit', async () => {
  app.unmount();globalThis.isTauri=true;const calls=[];
  dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
    calls.push([command,args]);return {ok:true,data:{items:[{id:'fixture-id',modelId:'actual-from-Core',provider:'fixture',kind:'local',modalities:['image'],enabled:false}],next_cursor:null}};
  }};
  app=createApp(components.ModelsView);app.config.errorHandler=e=>errors.push(e);app.mount('#app');
  await new Promise(resolve=>setImmediate(resolve));await nextTick();
  assert.match(document.querySelector('.model-list').textContent,/actual-from-Core/);
  assert.deepEqual(calls.map(c=>c[0]),['list_models']);
  const inputs=document.querySelectorAll('.model-registration input');
  for(const [index,value] of [[0,'Ollama'],[1,'fixture-model']]){inputs[index].value=value;dispatch(inputs[index],new Event('input',{bubbles:true}));}
  await nextTick();dispatch(document.querySelector('.model-registration'),new Event('submit',{bubbles:true,cancelable:true}));
  await new Promise(resolve=>setImmediate(resolve));await nextTick();
  assert.equal(calls[1][0],'register_model');assert.equal(calls[1][1].modelId,'fixture-model');
  assert.match(document.querySelector('[role=status]').textContent,/프로필을 저장/);
});

test('local model inspection is a separate explicit action with measured status', async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];let inspected=false;
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
   calls.push(command);if(command==='inspect_model'){inspected=true;return {ok:true};}
   return {ok:true,data:{items:[{id:'fixture',provider:'Ollama',kind:'local',modelId:'fixture-model',modalities:['image'],enabled:false,inspection:{status:inspected?'unavailable':'unchecked'}}],next_cursor:null}};
 }};
 app=createApp(components.ModelsView);app.config.errorHandler=e=>errors.push(e);app.mount('#app');
 await new Promise(r=>setImmediate(r));await nextTick();assert.deepEqual(calls,['list_models']);
 dispatch(document.querySelector('.model-list button'),new MouseEvent('click',{bubbles:true}));
 await new Promise(r=>setImmediate(r));await nextTick();
 assert.deepEqual(calls,['list_models','inspect_model','list_models']);assert.match(document.querySelector('.model-list').textContent,/unavailable/);
});

test('external model inspection sends only explicit consent and displays unknown authentication',async()=>{
 app.unmount();globalThis.isTauri=true;let sent;
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
  if(command==='inspect_model'){sent=args;return {ok:true};}
  return {ok:true,data:{items:[{id:'fixture',provider:'OpenRouter',kind:'external',modelId:'fixture/model',modalities:['text'],enabled:false,inspection:{status:'available',costClass:'paid',authentication:'not_tested'}}],next_cursor:null}};
 }};
 app=createApp(components.ModelsView);app.config.errorHandler=e=>errors.push(e);app.mount('#app');
 await new Promise(r=>setImmediate(r));await nextTick();
 dispatch(document.querySelector('.model-list button'),new MouseEvent('click',{bubbles:true}));
 await new Promise(r=>setImmediate(r));await nextTick();assert.equal(sent.allowExternal,false);
 const consent=document.querySelector('.models-page input[type=checkbox]');consent.checked=true;dispatch(consent,new Event('change',{bubbles:true}));await nextTick();
 dispatch(document.querySelector('.model-list button'),new MouseEvent('click',{bubbles:true}));
 await new Promise(r=>setImmediate(r));await nextTick();assert.equal(sent.allowExternal,true);
 assert.match(document.querySelector('.model-list').textContent,/paid/);assert.match(document.querySelector('.model-list').textContent,/not_tested/);
});

test('credential input is masked, sent only on save and cleared after failure',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);return {ok:false};}};
 app=createApp(components.ModelCredential,{id:'fixture',hasCredential:false,allowExternal:false});app.config.errorHandler=e=>errors.push(e);app.mount('#app');
 const input=document.querySelector('.model-credential input');assert.equal(input.type,'password');input.value='fixture-private-key';dispatch(input,new Event('input',{bubbles:true}));await nextTick();assert.equal(calls.length,0);
 dispatch(document.querySelector('.model-credential form'),new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(calls[0][0],'model_credential');assert.equal(calls[0][1].key,'fixture-private-key');assert.equal(input.value,'');assert.doesNotMatch(document.body.textContent,/fixture-private-key/);
});

test('paid model policy defaults off and transmits explicit approvals only on save',async()=>{
 app.unmount();globalThis.isTauri=true;let sent;
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{assert.equal(command,'configure_model');sent=args.policy;return {ok:false,error:{code:'MODEL_POLICY_DENIED'}};}};
 app=createApp(components.ModelPolicy,{id:'fixture',enabled:false});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await nextTick();
 const checks=[...document.querySelectorAll('.model-policy input[type=checkbox]')];assert.ok(checks.every(c=>!c.checked));assert.equal(sent,undefined);
 dispatch(document.querySelector('.model-policy'),new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(sent.allow_paid,false);assert.equal(sent.allow_external,false);assert.equal(sent.enabled,false);assert.match(document.querySelector('[role=status]').textContent,/모델 상태/);
});

test('incompatible model cannot be selected and compatible input uses server validation',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
  calls.push([command,args]);if(command==='validate_model')return {ok:true,data:{compatible:false,reason:'MODEL_CAPABILITY_MISMATCH'}};
  return {ok:true,data:{items:[{id:'fixture',provider:'Ollama',kind:'local',modelId:'text-only',modalities:['image'],enabled:true,inspection:{modalities:['text']}}],next_cursor:null}};
 }};
 app=createApp(components.ModelsView);app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 const select=[...document.querySelectorAll('.model-list button')].find(b=>b.textContent==='이 모델 선택');assert.equal(select.disabled,true);
 const validate=[...document.querySelectorAll('.model-list button')].find(b=>b.textContent==='입력 지원 검사');dispatch(validate,new MouseEvent('click',{bubbles:true}));
 await new Promise(r=>setImmediate(r));await nextTick();assert.match(document.querySelector('[role=status]').textContent,/MODEL_CAPABILITY_MISMATCH/);assert.equal(calls[1][1].modality,'image');
});

test('opening and closing manual analysis only reads profiles and cannot start without review',async()=>{
 await mountGallery([{id:'fixture',name:'fixture.png',kind:'PNG'}]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{calls.push(command);return {ok:true,data:{items:[],next_cursor:null}};}};
 dispatch(document.querySelector('.analysis-open'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 const dialog=document.querySelector('[role=dialog]');assert.ok(dialog);assert.deepEqual(calls,['list_models']);
 const start=[...dialog.querySelectorAll('button')].find(b=>b.textContent.includes('분석 시작'));assert.equal(start.disabled,true);
 dispatch(dialog,new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await nextTick();assert.equal(document.querySelector('[role=dialog]'),null);assert.equal(document.activeElement,document.querySelector('.analysis-open'));
});

test('manual target preview sends selected mode and shows server count without starting work',async()=>{
 await mountGallery([]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
  calls.push([command,args]);
  if(command==='list_models')return {ok:true,data:{items:[{id:'fixture-model-id',modelId:'fixture',enabled:true,selected:true,inspection:{modalities:['image']}}],next_cursor:null}};
  return {ok:true,data:{targetCount:2,missingCount:0,planToken:'fixture-token'}};
 }};
 dispatch(document.querySelector('.analysis-open'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 const selects=document.querySelectorAll('[role=dialog] select');selects[0].value='all';dispatch(selects[0],new Event('change',{bubbles:true}));selects[1].value='all';dispatch(selects[1],new Event('change',{bubbles:true}));await nextTick();
 const preview=[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='대상 확인');dispatch(preview,new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(calls[1][0],'preview_analysis');assert.equal(calls[1][1].plan.mode,'all');assert.match(document.querySelector('[role=dialog] [role=status]').textContent,/대상 2개/);assert.equal(calls.length,2);
});

test('analysis start is explicit after review and uses a stable idempotency ID',async()=>{
 await mountGallery([]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
  calls.push([command,args]);
  if(command==='list_models')return {ok:true,data:{items:[{id:'fixture-model-id',modelId:'fixture',enabled:true,selected:true,inspection:{modalities:['image']}}],next_cursor:null}};
  if(command==='preview_analysis')return {ok:true,data:{targetCount:1,missingCount:0,planToken:'a'.repeat(64),estimatedUpperBoundUsd:'0',externalTransfer:false,paid:false}};
  return {ok:true,data:{jobId:'fixture-real-response-id'}};
 }};
 dispatch(document.querySelector('.analysis-open'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 const selects=document.querySelectorAll('[role=dialog] select');for(const select of [selects[0],selects[1]]){select.value='all';dispatch(select,new Event('change',{bubbles:true}));}await nextTick();
 dispatch([...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='대상 확인'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(calls.length,2);
 const button=document.querySelector('.analysis-start');assert.equal(button.disabled,false);dispatch(button,new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(calls[2][0],'start_analysis');assert.equal(calls[2][1].request.confirmed,true);assert.match(calls[2][1].request.request_id,/^[a-f0-9-]{36}$/);
 assert.match(document.querySelector('[role=dialog]').textContent,/fixture-real-response-id/);
});

test('stored AI result renders description and provenance as text without executing content',async()=>{
 app.unmount();globalThis.isTauri=true;
 dom.window.__TAURI_INTERNALS__={invoke:async command=>{assert.equal(command,'asset_analysis');return {ok:true,data:{active:{description:'<img src=x onerror=alert(1)> red square',tags:['red'],provider:'Ollama',modelId:'fixture-model',createdAt:'fixture-time'}}};}};
 app=createApp(components.AssetAnalysis,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 assert.match(document.querySelector('.asset-analysis').textContent,/red square/);assert.match(document.querySelector('.asset-analysis').textContent,/fixture-model/);assert.equal(document.querySelector('.asset-analysis img'),null);
});

test('job list restores measured batch progress without opening the analysis dialog',async()=>{
 await mountGallery([]);globalThis.isTauri=true;
 dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{
  if(command==='analysis_jobs')return {ok:true,data:{items:[{id:'fixture-batch',status:'running',total:3,createdAt:'fixture-time'}]}};
  assert.equal(command,'analysis_status');return {ok:true,data:{status:'running',total:3,processed:2,succeeded:1,failed:1,canceled:0,needsRecovery:false,errors:[]}};
 }};
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='최근 분석 작업 확인'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 dispatch(document.querySelector('.analysis-job-list button'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(document.querySelector('[role=dialog]'),null);assert.match(document.querySelector('.asset-gallery [role=status]').textContent,/2\/3/);
 assert.equal(components.operations.find(o=>o.id==='fixture-batch').progress.processed,2);
});

test('cancel is a separate explicit action and reports actual terminal state',async()=>{
 await mountGallery([]);globalThis.isTauri=true;let canceled=false;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{
  calls.push(command);
  if(command==='analysis_jobs')return {ok:true,data:{items:[{id:'fixture-cancel',status:'running',total:2,createdAt:'fixture'}]}};
  if(command==='cancel_analysis'){canceled=true;return {ok:true,data:{cancelRequested:true,status:'running'}};}
  if(command==='list_assets')return {ok:true,data:{items:[],next_cursor:null}};
  return {ok:true,data:{status:canceled?'canceled':'running',total:2,processed:canceled?2:0,succeeded:0,failed:0,canceled:canceled?2:0,needsRecovery:false,errors:[]}};
 }};
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='최근 분석 작업 확인'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();dispatch(document.querySelector('.analysis-job-list button'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(canceled,false);
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='분석 취소 요청'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(canceled,true);assert.ok(!calls.includes('start_analysis'));
 assert.match(document.querySelector('.asset-gallery').textContent,/canceled/);
});

test('retry reloads old conditions for a new review without automatically starting',async()=>{
 await mountGallery([]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{
  calls.push([command,args]);
  if(command==='analysis_jobs')return {ok:true,data:{items:[{id:'fixture-retry',status:'canceled',total:1,createdAt:'fixture'}]}};
  if(command==='analysis_status')return {ok:true,data:{status:'canceled',total:1,processed:1,succeeded:0,failed:0,canceled:1,needsRecovery:false,errors:[]}};
  if(command==='list_assets')return {ok:true,data:{items:[],next_cursor:null}};
  if(command==='retry_analysis_plan')return {ok:true,data:{plan:{mode:'selected',scope:'all',library_id:null,folder_parts:[],selected_ids:['old-selected-asset'],model_id:'fixture-model'}}};
  if(command==='list_models')return {ok:true,data:{items:[{id:'fixture-model',modelId:'fixture',enabled:true,selected:true,inspection:{modalities:['image']}}],next_cursor:null}};
  if(command==='preview_analysis')return {ok:true,data:{targetCount:1,missingCount:0,planToken:'a'.repeat(64),estimatedUpperBoundUsd:'0',externalTransfer:false,paid:false}};
  throw new Error('start must not be called');
 }};
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='최근 분석 작업 확인'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();dispatch(document.querySelector('.analysis-job-list button'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='같은 조건으로 재검토'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 const preview=calls.find(c=>c[0]==='preview_analysis');assert.deepEqual(preview[1].plan.selected_ids,['old-selected-asset']);assert.ok(!calls.some(c=>c[0]==='start_analysis'));assert.equal(document.querySelector('.analysis-start').disabled,false);
});

test('failed attempt history is distinct from the retained active description',async()=>{
 app.unmount();globalThis.isTauri=true;let page=0;
 dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{
  if(command==='asset_analysis')return {ok:true,data:{active:{description:'previous successful description',tags:['old'],provider:'fixture',modelId:'fixture-model',createdAt:'fixture'}}};
  assert.equal(command,'asset_analysis_history');page++;
  return {ok:true,data:{items:[{id:'run-'+page,status:page===1?'failed':'completed',createdAt:'fixture',description:page===1?null:'previous successful description',tags:[],active:page===2,errorCode:page===1?'API_TIMEOUT':null}],next_cursor:page===1?'cursor':null}};
 }};
 app=createApp(components.AssetAnalysis,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 for(let i=0;i<2;i++){dispatch(document.querySelector('.asset-analysis button'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();}
 assert.equal(document.querySelectorAll('.analysis-history li').length,2);assert.match(document.querySelector('.asset-analysis').textContent,/previous successful description/);assert.match(document.querySelector('.analysis-history').textContent,/API_TIMEOUT/);
});

test('user metadata and AI results remain visibly separate after a failed attempt',async()=>{
 app.unmount();globalThis.isTauri=true;
 dom.window.__TAURI_INTERNALS__={invoke:async(command)=>command==='asset_annotations'?{ok:true,data:{tags:['user-tag'],title:'User title',description:'User notes'}}:{ok:true,data:{active:{description:'AI description',tags:['ai-tag'],provider:'Ollama',modelId:'fixture',createdAt:'fixture'}}}};
 app=createApp({render:()=>h('div',[h(components.AssetAnnotations,{assetId:'fixture'}),h(components.AssetAnalysis,{assetId:'fixture',lastAttemptState:'failed'})])});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(document.querySelector('.annotation-form textarea').value,'User notes');assert.match(document.querySelector('.user-annotations').textContent,/user-tag/);assert.doesNotMatch(document.querySelector('.user-annotations').textContent,/AI description/);
 assert.match(document.querySelector('.asset-analysis').textContent,/ai-tag/);assert.match(document.querySelector('.analysis-retained').textContent,/이전 성공 결과를 유지/);
});

test('unsupported preview reports limits and cannot start an all-audio scope',async()=>{
 await mountGallery([]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{calls.push(command);return command==='list_models'?{ok:true,data:{items:[{id:'fixture-model',modelId:'fixture',enabled:true,selected:true,inspection:{modalities:['image']}}],next_cursor:null}}:{ok:true,data:{targetCount:2,eligibleCount:0,unsupportedCount:2,overLimitCount:0,missingCount:0,planToken:'a'.repeat(64),estimatedUpperBoundUsd:'0'}};}};
 dispatch(document.querySelector('.analysis-open'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();const selects=document.querySelectorAll('[role=dialog] select');for(const select of [selects[0],selects[1]]){select.value='all';dispatch(select,new Event('change',{bubbles:true}));}await nextTick();dispatch([...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='대상 확인'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(document.querySelector('.analysis-start').disabled,true);assert.match(document.querySelector('[role=dialog]').textContent,/미지원 2개/);assert.ok(!calls.includes('start_analysis'));
});

test('embedding profile configuration is explicit metadata only',async()=>{
 await mountGallery([]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);return {ok:true,data:{profile:{modelName:'fixture',dimension:3,version:'fixture-version'},readyCount:0}};}};
 const form=document.querySelector('.embedding-tools form'),input=form.querySelector('input');input.value='fixture';dispatch(input,new Event('input',{bubbles:true}));await nextTick();assert.equal(calls.length,0);
 dispatch(form,new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.deepEqual(calls.map(c=>c[0]),['embedding_configure','embedding_status']);assert.match(document.querySelector('.embedding-tools').textContent,/3차원/);
});

test('semantic mode and query editing do not embed until explicit execution',async()=>{
 await mountWorkspace([{id:'a',name:'one',kind:'PNG'},{id:'b',name:'two',kind:'PNG'}]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);return command==='embedding_query'?{ok:true,data:{jobId:'fixture-query'}}:{ok:true,data:{status:'completed',results:[{id:'b',score:.8,reason:'semantic'}]}};}};
 const select=document.querySelector('[aria-label="검색 방식"]');select.value='semantic';dispatch(select,new Event('change',{bubbles:true}));await nextTick();components.setSearchQuery('중세 횃불');await nextTick();assert.equal(calls.length,0);
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='로컬 검색 실행'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.deepEqual(calls.map(c=>c[0]),['embedding_query','embedding_work']);assert.match(document.querySelector('.asset-card').textContent,/two/);assert.match(document.querySelector('.asset-card').textContent,/0.800/);
});

test('hybrid query sends combined filters before server ranking',async()=>{
 await mountWorkspace([{id:'a',name:'one',kind:'PNG',userTags:['숲']}]);globalThis.isTauri=true;let criteria;
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{if(command==='embedding_query'){criteria=args.criteria;return {ok:true,data:{jobId:'hybrid-job'}};}return {ok:true,data:{status:'completed',results:[{id:'a',score:.03,reason:'hybrid'}]}};}};
 const mode=document.querySelector('[aria-label="검색 방식"]');mode.value='hybrid';dispatch(mode,new Event('change',{bubbles:true}));await nextTick();components.setSearchQuery('숲');await nextTick();
 const type=document.querySelector('[aria-label="타입 필터"]');type.value='PNG';dispatch(type,new Event('change',{bubbles:true}));await nextTick();
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='로컬 검색 실행'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(criteria.kind,'PNG');assert.match(document.querySelector('.asset-card').textContent,/키워드\+의미/);
});

test('whole embedding rebuild requires a separate explicit approval',async()=>{
 await mountGallery([]);globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command)=>{calls.push(command);if(command==='embedding_status')return {ok:true,data:{profile:{modelName:'fixture',dimension:3,version:'v'},readyCount:0}};if(command==='embedding_rebuild')return {ok:true,data:{jobId:'fixture-rebuild'}};return {ok:true,data:{status:'completed',processed:1,total:1,failed:0}};}};
 const button=[...document.querySelectorAll('.embedding-tools button')].find(b=>b.textContent==='현재 버전 전체 재구축');assert.equal(button.disabled,true);
 dispatch([...document.querySelectorAll('.embedding-tools button')].find(b=>b.textContent==='임베딩 준비 상태 확인'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(button.disabled,true);
 const approval=document.querySelector('.embedding-tools input[type=checkbox]');approval.checked=true;dispatch(approval,new Event('change',{bubbles:true}));await nextTick();assert.deepEqual(calls,['embedding_status']);dispatch(button,new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.ok(calls.includes('embedding_rebuild'));assert.ok(!calls.includes('embedding_start'));
});

test('MCP connection and audit page renders actual read data and escapes asset text',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);if(command==='mcp_connection')return {ok:true,data:{brokerReady:true,transport:'stdio',readOnly:true,configuration:{command:'C:/fixture/core.exe',args:['--mcp'],cwd:'C:/fixture'}}};return {ok:true,data:{items:[{id:'audit-1',host:'reference-host',hostFingerprint:'hash',tool:'<img src=x onerror=alert(1)>',outcome:'succeeded',createdAt:'fixture-time',requestId:'request-1',targetIds:['asset-1'],targetCount:1,errorCode:null,durationMs:2}],next_cursor:null}};}};
 app=createApp(components.McpView);app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 assert.deepEqual(calls.map(c=>c[0]),['mcp_connection','mcp_audit']);assert.match(document.body.textContent,/Core 조회 채널: 준비됨/);assert.match(document.querySelector('.mcp-audit').textContent,/request-1/);assert.match(document.querySelector('.mcp-audit').textContent,/asset-1/);assert.equal(document.querySelector('.mcp-audit img'),null);assert.doesNotMatch(document.querySelector('.mcp-configuration').textContent,/token|mac|port/);
});

test('MCP audit page retries a failed read and pages with the actual cursor',async()=>{
 app.unmount();globalThis.isTauri=true;let fail=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);if(fail)throw new Error('private transport details');if(command==='mcp_connection')return {ok:true,data:{brokerReady:false,transport:'stdio',readOnly:true,configuration:{command:'fixture',args:['--mcp'],cwd:'fixture'}}};return {ok:true,data:{items:[],next_cursor:args.afterId===null?'audit-cursor':null}};}};
 app=createApp(components.McpView);app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();assert.match(document.querySelector('[role=alert]').textContent,/불러오지 못했습니다/);assert.doesNotMatch(document.body.textContent,/private transport/);
 fail=false;dispatch(document.querySelector('button'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.match(document.body.textContent,/연결 불가/);
 dispatch([...document.querySelectorAll('button')].find(b=>b.textContent==='이전 호출 더 보기'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(calls.at(-1)[1].afterId,'audit-cursor');assert.ok(calls.every(c=>['mcp_connection','mcp_audit'].includes(c[0])));
});


test('management saves explicitly, preserves drafts on conflict and distinguishes unrated', async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];let conflict=true;
 const value={favorite:false,rating:null,status:'unreviewed',notes:'memo',assetVersion:'v1',createdDate:'',modifiedDate:''};
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);return command==='get_asset_management'?{ok:true,data:{value:{...value},revision:2}}:conflict?{ok:false,error:{code:'METADATA_CONFLICT'}}:{ok:true,data:{value:args.value,revision:3}};}};
 app=createApp(components.AssetManagement,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(document.querySelector('.asset-management select').selectedIndex,0);assert.equal(calls.length,1);
 const memo=document.querySelector('.asset-management textarea');memo.value='draft';dispatch(memo,new Event('input',{bubbles:true}));await nextTick();assert.equal(calls.length,1);
 dispatch(document.querySelector('.asset-management form'),new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(calls[1][1].expectedRevision,2);assert.equal(calls[1][1].value.notes,'draft');assert.equal(memo.value,'draft');assert.equal(document.querySelector('.asset-management fieldset button').disabled,true);
 conflict=false;dispatch([...document.querySelectorAll('.asset-management button')].at(-1),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(memo.value,'memo');assert.equal(document.querySelector('.asset-management fieldset button').disabled,false);
});


test('file composition links only selected catalog references and saves explicitly',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 const state={value:{files:[{fileId:'owned',role:'source'}],components:[]},revision:0,availability:'partial',files:[{fileId:'owned',role:'source',name:'original.png',owned:true,available:true}],components:[]};
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);if(command==='get_asset_composition')return {ok:true,data:state};if(command==='asset_link_candidates')return {ok:true,data:{items:[{id:'registered',name:'<b>dependency</b>',available:true}],next_cursor:'next-real-id'}};return {ok:true,data:{...state,value:args.value,revision:1}};}};
 app=createApp(components.AssetComposition,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(document.querySelector('.asset-composition li button').disabled,true);assert.match(document.querySelector('.asset-composition').textContent,/부분 가용/);
 dispatch([...document.querySelectorAll('.asset-composition button')].find(b=>b.textContent==='등록된 참조 찾기'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(document.querySelector('.reference-candidates b'),null);dispatch(document.querySelector('.reference-candidates button'),new MouseEvent('click',{bubbles:true}));await nextTick();assert.equal(calls.length,2);
 dispatch([...document.querySelectorAll('.asset-composition button')].find(b=>b.textContent==='파일 구성 저장'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 assert.equal(calls.at(-1)[0],'save_asset_composition');assert.deepEqual(calls.at(-1)[1].value.files,[{fileId:'owned',role:'source'},{fileId:'registered',role:'dependency'}]);assert.equal(calls.at(-1)[1].expectedRevision,0);
});


test('relations select real candidates, send direction and retain draft after rejected cycle',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);if(command==='get_asset_relations')return {ok:true,data:{value:[],revision:4,items:[]}};if(command==='asset_link_candidates')return {ok:true,data:{items:[{id:'real-target',name:'<script>original</script>',relations:['original_of']}],next_cursor:null}};return {ok:false,error:{code:'INVALID_PARAMS',message:'private details'}};}};
 app=createApp(components.AssetRelations,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
 const select=document.querySelector('.asset-relations select');select.value='derived_from';dispatch(select,new Event('change',{bubbles:true}));await nextTick();
 dispatch([...document.querySelectorAll('.asset-relations button')].find(b=>b.textContent==='등록 에셋 찾기'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(document.querySelector('.relation-candidates script'),null);
 dispatch(document.querySelector('.relation-candidates button'),new MouseEvent('click',{bubbles:true}));await nextTick();assert.equal(calls.length,2);
 dispatch([...document.querySelectorAll('.asset-relations button')].find(b=>b.textContent==='관계 저장'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.deepEqual(calls.at(-1)[1].value,[{targetId:'real-target',kind:'derived_from'}]);assert.equal(calls.at(-1)[1].expectedRevision,4);
 assert.match(document.querySelector('.asset-relations').textContent,/real-target/);assert.match(document.querySelector('.asset-relations [role=status]').textContent,/파생 순환/);assert.doesNotMatch(document.body.textContent,/private details/);
});


test('metadata history pages actual versions, escapes values and preserves rows on failed paging',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];let fail=false;
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);if(fail)throw new Error('private detail');return {ok:true,data:{items:[{id:args.beforeId===null?2:1,field:'management',revision:args.beforeId===null?2:1,action:'set',actor:'user',createdAt:'fixture-date',before:null,after:{value:'<img src=x onerror=bad>'}}],next_cursor:args.beforeId===null?2:null}};}};
 app=createApp(components.AssetMetadataHistory,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await nextTick();assert.equal(calls.length,0);
 const click=async(text)=>{dispatch([...document.querySelectorAll('.asset-metadata-history button')].find(b=>b.textContent===text),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();};
 await click('변경 이력 보기');assert.match(document.querySelector('.asset-metadata-history').textContent,/버전 2/);assert.equal(document.querySelector('.asset-metadata-history img'),null);
 fail=true;await click('이전 변경 더 보기');assert.equal(document.querySelectorAll('.asset-metadata-history li').length,1);assert.doesNotMatch(document.body.textContent,/private detail/);
 fail=false;await click('이전 변경 더 보기');assert.equal(calls.at(-1)[1].beforeId,2);assert.equal(document.querySelectorAll('.asset-metadata-history li').length,2);assert.match(document.querySelector('.asset-metadata-history').textContent,/버전 1/);
});

test('metadata editors ignore stale reads when selected asset changes',async()=>{
 for(const [name,command,make,selector] of [
 ['AssetManagement','get_asset_management',label=>({value:{favorite:false,rating:null,status:'unreviewed',notes:label,assetVersion:'',createdDate:'',modifiedDate:''},revision:0}),'.asset-management textarea'],
 ['AssetComposition','get_asset_composition',label=>({value:{files:[{fileId:label,role:'source'}],components:[]},revision:0,availability:'available',files:[{fileId:label,role:'source',name:label,owned:true,available:true}],components:[]}),'.asset-composition li'],
 ['AssetRelations','get_asset_relations',label=>({value:[{targetId:label,kind:'related'}],revision:0,items:[{targetId:label,kind:'related',name:label,available:true}]}),'.asset-relations li']]){
  app.unmount();globalThis.isTauri=true;let resolveOld;const id=ref('old');
  dom.window.__TAURI_INTERNALS__={invoke:async(c,args)=>{assert.equal(c,command);return args.assetId==='old'?await new Promise(resolve=>{resolveOld=resolve;}):{ok:true,data:make('new-value')};}};
  app=createApp({render:()=>h(components[name],{assetId:id.value})});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await nextTick();id.value='new';await nextTick();await new Promise(r=>setImmediate(r));await nextTick();
  resolveOld({ok:true,data:make('old-value')});await new Promise(r=>setImmediate(r));await nextTick();const node=document.querySelector(selector);assert.match(typeof node.value==='string'?node.value:node.textContent,/new-value/);assert.doesNotMatch(typeof node.value==='string'?node.value:node.textContent,/old-value/);
 }
});

test('file and relationship editors block repeated conflict saves while retaining drafts',async()=>{
 for(const [name,get,save,state,section,label] of [
 ['AssetComposition','get_asset_composition','save_asset_composition',{value:{files:[{fileId:'file',role:'source'}],components:[]},revision:1,availability:'available',files:[{fileId:'file',role:'source',name:'preserved-file',owned:true,available:true}],components:[]},'.asset-composition','파일 구성 저장'],
 ['AssetRelations','get_asset_relations','save_asset_relations',{value:[{targetId:'target',kind:'related'}],revision:1,items:[{targetId:'target',kind:'related',name:'preserved-target',available:true}]},'.asset-relations','관계 저장']]){
  app.unmount();globalThis.isTauri=true;let saves=0;
  dom.window.__TAURI_INTERNALS__={invoke:async(c)=>{if(c===get)return {ok:true,data:state};assert.equal(c,save);saves++;return {ok:false,error:{code:'METADATA_CONFLICT'}};}};
  app=createApp(components[name],{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();
  const button=[...document.querySelectorAll(section+' button')].find(b=>b.textContent===label);dispatch(button,new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(button.disabled,true);assert.match(document.querySelector(section).textContent,/preserved-/);assert.equal(saves,1);
 }
});

test('tag editing sends revision and preserves text drafts on a concurrent tag edit',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);return command==='asset_annotations'?{ok:true,data:{tags:['kept'],title:'title',description:'description',aliases:[],revision:2,tagsRevision:3}}:{ok:false,error:{code:'METADATA_CONFLICT'}};}};
 app=createApp(components.AssetAnnotations,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();const title=document.querySelector('.annotation-form input');title.value='draft';dispatch(title,new Event('input',{bubbles:true}));await nextTick();
 dispatch(document.querySelector('.user-annotations li button'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(calls.at(-1)[1].expectedRevision,3);assert.equal(title.value,'draft');assert.match(document.querySelector('.user-annotations').textContent,/kept/);assert.equal(document.querySelector('.annotation-form button').disabled,true);
});


test('logical group create is explicit and deletes require review without file commands',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);if(command==='group_list')return {ok:true,data:{items:[],next_cursor:null}};if(command==='group_create')return {ok:true,data:{id:'real-group',name:args.value.name,description:'',parentId:null,revision:1}};return {ok:true,data:{deleted:args.groupId}};}};
 app=createApp(components.GroupManager);app.config.errorHandler=e=>errors.push(e);app.mount('#app');await nextTick();dispatch(document.querySelector('.group-manager > button'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();
 const input=document.querySelector('.group-manager form input');input.value='<b>group</b>';dispatch(input,new Event('input',{bubbles:true}));await nextTick();assert.equal(calls.length,1);
 dispatch(document.querySelector('.group-manager form'),new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.equal(calls.at(-1)[0],'group_create');assert.equal(document.querySelector('.group-manager li b'),null);
 dispatch(document.querySelector('.group-manager li button'),new MouseEvent('click',{bubbles:true}));await nextTick();const del=[...document.querySelectorAll('.group-manager button')].find(b=>b.textContent==='그룹 삭제');assert.equal(del.disabled,true);
 const confirm=document.querySelector('.group-manager input[type=checkbox]');confirm.checked=true;dispatch(confirm,new Event('change',{bubbles:true}));await nextTick();dispatch(del,new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.deepEqual(calls.at(-1),['group_delete',{groupId:'real-group',expectedRevision:1}]);
});

test('group membership preserves unloaded group ids and conflicts keep the draft',async()=>{
 app.unmount();globalThis.isTauri=true;const calls=[];
 dom.window.__TAURI_INTERNALS__={invoke:async(command,args)=>{calls.push([command,args]);if(command==='group_list')return {ok:true,data:{items:[{id:'visible',name:'visible',description:'',revision:1,parentId:null}],next_cursor:'next'}};if(command==='group_membership')return {ok:true,data:{ids:['not-yet-loaded'],revision:2}};return {ok:false,error:{code:'METADATA_CONFLICT',message:'private'}};}};
 app=createApp(components.GroupManager,{assetId:'fixture'});app.config.errorHandler=e=>errors.push(e);app.mount('#app');await new Promise(r=>setImmediate(r));await nextTick();const check=document.querySelector('.group-manager li input');check.checked=true;dispatch(check,new Event('change',{bubbles:true}));await nextTick();assert.equal(calls.length,2);
 dispatch([...document.querySelectorAll('.group-manager button')].find(b=>b.textContent==='그룹 소속 저장'),new MouseEvent('click',{bubbles:true}));await new Promise(r=>setImmediate(r));await nextTick();assert.deepEqual(calls.at(-1)[1].groupIds,['not-yet-loaded','visible']);assert.equal(check.checked,true);assert.equal([...document.querySelectorAll('.group-manager button')].find(b=>b.textContent==='그룹 소속 저장').disabled,true);assert.doesNotMatch(document.body.textContent,/private/);
});
