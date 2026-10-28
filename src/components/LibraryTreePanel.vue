<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, ref, watch, type ComponentPublicInstance, type VNode } from "vue";
import { LIBRARY_PANEL_WIDTH, libraryUi, setLibraryPanelWidth } from "../stores/libraryUi";

export interface LibraryFolderNode {
  id: string;
  name: string;
  children?: readonly LibraryFolderNode[];
}

const props = withDefaults(defineProps<{
  nodes?: readonly LibraryFolderNode[];
  selectedId: string | null;
  resizable?: boolean;
}>(), { nodes: () => [], resizable: true });
const emit = defineEmits<{ select: [id: string | null] }>();

const expanded = ref(new Set<string>());
const focusedId = ref<string | null>(props.selectedId);
const elements = new Map<string | null, HTMLElement>();
const resizing = ref(false);
let drag: { pointerId: number; startX: number; width: number } | null = null;

const visibleFolders = computed(() => {
  const rows: { node: LibraryFolderNode; parentId?: string }[] = [];
  function visit(nodes: readonly LibraryFolderNode[], parentId?: string) {
    for (const node of nodes) {
      rows.push({ node, parentId });
      if (expanded.value.has(node.id)) visit(node.children ?? [], node.id);
    }
  }
  visit(props.nodes);
  return rows;
});
const visibleIds = computed(() => [null, ...visibleFolders.value.map(({ node }) => node.id)]);

watch(visibleIds, (ids) => {
  if (!ids.includes(focusedId.value)) focusedId.value = null;
}, { immediate: true });

function registerElement(id: string | null, element: Element | ComponentPublicInstance | null) {
  if (element instanceof HTMLElement) elements.set(id, element);
  else elements.delete(id);
}

function focusItem(id: string | null) {
  focusedId.value = id;
  void nextTick(() => elements.get(id)?.focus());
}

function choose(id: string | null) {
  emit("select", id);
  focusItem(id);
}

function toggle(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id);
  else expanded.value.add(id);
  focusItem(id);
}

function handleTreeKey(event: KeyboardEvent, id: string | null) {
  const ids = visibleIds.value;
  const index = ids.indexOf(id);
  const row = visibleFolders.value.find(({ node }) => node.id === id);
  switch (event.key) {
    case "ArrowDown": focusItem(ids[Math.min(index + 1, ids.length - 1)] ?? null); break;
    case "ArrowUp": focusItem(ids[Math.max(index - 1, 0)] ?? null); break;
    case "Home": focusItem(null); break;
    case "End": focusItem(ids[ids.length - 1] ?? null); break;
    case "ArrowRight":
      if (row?.node.children?.length) {
        if (expanded.value.has(row.node.id)) focusItem(row.node.children[0]!.id);
        else toggle(row.node.id);
      }
      break;
    case "ArrowLeft":
      if (id !== null && expanded.value.has(id)) toggle(id);
      else if (row?.parentId !== undefined) focusItem(row.parentId);
      break;
    case "Enter":
    case " ": choose(id); break;
    default: return;
  }
  event.preventDefault();
}

function renderFolder(node: LibraryFolderNode, level: number): VNode {
  const hasChildren = Boolean(node.children?.length);
  const isExpanded = expanded.value.has(node.id);
  return h("li", {
    key: node.id,
    role: "treeitem",
    "aria-label": node.name,
    "aria-level": level,
    "aria-selected": props.selectedId === node.id,
    "aria-expanded": hasChildren ? isExpanded : undefined,
    "data-folder-id": node.id,
    tabindex: focusedId.value === node.id ? 0 : -1,
    ref: (element) => registerElement(node.id, element),
    onFocus: () => { focusedId.value = node.id; },
    onClick: (event: MouseEvent) => { event.stopPropagation(); choose(node.id); },
    onKeydown: (event: KeyboardEvent) => { event.stopPropagation(); handleTreeKey(event, node.id); },
  }, [
    h("div", { class: "tree-row" }, [
      hasChildren ? h("button", {
        class: "tree-toggle", type: "button", tabindex: -1,
        "aria-label": `${node.name} ${isExpanded ? "접기" : "펼치기"}`,
        onClick: (event: MouseEvent) => { event.stopPropagation(); toggle(node.id); },
      }, isExpanded ? "▾" : "▸") : h("span", { class: "tree-toggle-spacer", "aria-hidden": "true" }),
      h("span", { class: "folder-mark", "aria-hidden": "true" }),
      h("span", { class: "folder-name", title: node.name }, node.name),
    ]),
    hasChildren && isExpanded
      ? h("ul", { role: "group" }, node.children!.map((child) => renderFolder(child, level + 1)))
      : null,
  ]);
}

const FolderNodes = () => props.nodes.map((node) => renderFolder(node, 1));

function stopResize() {
  drag = null;
  resizing.value = false;
  window.removeEventListener("pointermove", moveResize);
  window.removeEventListener("pointerup", endResize);
  window.removeEventListener("pointercancel", endResize);
  window.removeEventListener("blur", stopResize);
}

function moveResize(event: PointerEvent) {
  if (drag && event.pointerId === drag.pointerId) {
    if (event.buttons === 0) {
      stopResize();
      return;
    }
    setLibraryPanelWidth(drag.width + event.clientX - drag.startX);
  }
}

function endResize(event: PointerEvent) {
  if (drag && event.pointerId === drag.pointerId) stopResize();
}

function startResize(event: PointerEvent) {
  if (!props.resizable) return;
  if (event.button !== 0 || event.isPrimary === false) return;
  stopResize();
  event.preventDefault();
  (event.currentTarget as HTMLElement).focus();
  drag = { pointerId: event.pointerId, startX: event.clientX, width: libraryUi.panelWidth };
  resizing.value = true;
  window.addEventListener("pointermove", moveResize);
  window.addEventListener("pointerup", endResize);
  window.addEventListener("pointercancel", endResize);
  window.addEventListener("blur", stopResize);
}

function handleResizeKey(event: KeyboardEvent) {
  switch (event.key) {
    case "ArrowLeft": setLibraryPanelWidth(libraryUi.panelWidth - 16); break;
    case "ArrowRight": setLibraryPanelWidth(libraryUi.panelWidth + 16); break;
    case "Home": setLibraryPanelWidth(LIBRARY_PANEL_WIDTH.min); break;
    case "End": setLibraryPanelWidth(LIBRARY_PANEL_WIDTH.max); break;
    case "Escape":
      if (!drag) return;
      setLibraryPanelWidth(drag.width);
      stopResize();
      break;
    default: return;
  }
  event.preventDefault();
}

onBeforeUnmount(stopResize);
watch(() => props.resizable, (enabled) => { if (!enabled) stopResize(); });
</script>

<template>
  <aside id="library-navigation" class="library-panel" aria-labelledby="library-panel-title">
    <h2 id="library-panel-title">라이브러리</h2>
    <ul class="library-tree" role="tree" aria-label="라이브러리 폴더">
      <li :ref="(element) => registerElement(null, element)" role="treeitem" aria-label="전체 에셋"
        :aria-selected="selectedId === null" :tabindex="focusedId === null ? 0 : -1"
        @focus="focusedId = null" @click="choose(null)" @keydown="handleTreeKey($event, null)">
        <div class="tree-row all-assets">전체 에셋</div>
      </li>
      <FolderNodes />
    </ul>
    <p v-if="nodes.length === 0" class="library-empty">등록된 폴더가 없습니다.</p>
  </aside>
  <div v-if="resizable" class="library-splitter" :class="{ 'is-resizing': resizing }" role="separator" tabindex="0"
    aria-orientation="vertical" aria-label="라이브러리 패널 너비" aria-controls="library-navigation"
    :aria-valuemin="LIBRARY_PANEL_WIDTH.min" :aria-valuemax="LIBRARY_PANEL_WIDTH.max"
    :aria-valuenow="libraryUi.panelWidth" :aria-valuetext="`${libraryUi.panelWidth}px`"
    title="드래그 또는 좌우 방향키로 너비 조절 · 두 번 클릭하여 초기화"
    @pointerdown="startResize" @keydown="handleResizeKey"
    @dblclick="setLibraryPanelWidth(LIBRARY_PANEL_WIDTH.initial)" />
</template>
