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
  ({ createApp, nextTick } = await import("vue"));
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
