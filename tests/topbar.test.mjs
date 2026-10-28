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
dom.window.__TAURI_INTERNALS__ = { invoke: rejectTransport };
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
  t.mock.timers.enable({ apis: ["Date"], now: Date.now() });
  advanceEventClock = () => t.mock.timers.tick(1);
  mounted = false;
  transportCalls = 0;
  errors = [];
  components.setSearchQuery("");
  components.setTheme("dark");
  components.setLibraryPanelWidth(components.LIBRARY_PANEL_WIDTH.initial);
  components.selectLibraryFolder(null);
  components.setGalleryViewMode("grid");
  components.setDetailsCollapsed(false);
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
