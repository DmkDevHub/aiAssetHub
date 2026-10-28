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
  dom.window.__TAURI_INTERNALS__ = { invoke };
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
