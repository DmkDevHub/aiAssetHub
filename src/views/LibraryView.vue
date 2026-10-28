<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import LibraryTreePanel from "../components/LibraryTreePanel.vue";
import AssetGallery from "../components/AssetGallery.vue";
import AssetDetailsPanel from "../components/AssetDetailsPanel.vue";
import { libraryUi, selectLibraryFolder } from "../stores/libraryUi";
import type { AssetSummary } from "../types/assets";
import { useWorkspaceLayout } from "../composables/useWorkspaceLayout";
import LibraryManagement from '../components/LibraryManagement.vue';
import { libraries, refreshLibraries } from '../stores/libraries';
import { assets, refreshAssets, resetAssets } from '../stores/assets';
import { workspace as searchState } from '../stores/workspace';
import { keywordFilter } from '../services/assetSearch';
import { folderNodes, filterFolder, type FolderNode } from '../services/assetFolders';

onMounted(() => { void refreshLibraries().then((ok)=>{ if(ok){if(libraries.roots.length)void refreshAssets();else resetAssets();} }); });
const emptyMessage = computed(() => libraries.loading ? '등록 폴더를 불러오는 중입니다.'
  : libraries.error ? '등록 폴더를 확인하지 못했습니다.' : '등록된 폴더가 없습니다.');

const props = defineProps<{ items?: readonly AssetSummary[] }>();
const availableItems = computed(() => assets.items.filter((item) => libraries.roots.some((root) => root.id===item.libraryId)));
const tag = ref('');
const sourceItems = computed(() => props.items ?? availableItems.value);
const tags = computed(() => [...new Set(sourceItems.value.flatMap(item => [...item.userTags ?? []]))].sort((a,b)=>a.localeCompare(b,'ko')));
const items = computed(() => keywordFilter(filterFolder(sourceItems.value, libraryUi.selectedFolderId), searchState.searchQuery, tag.value));
const nodes = computed(() => folderNodes(libraries.roots, availableItems.value));
watch(nodes,(roots)=>{
  function contains(items: readonly FolderNode[]): boolean { return items.some((node)=>node.id===libraryUi.selectedFolderId || contains(node.children ?? [])); }
  if(libraries.loaded && libraryUi.selectedFolderId && !contains(roots))selectLibraryFolder(null);
});
const selectedId = ref<string | null>(null);
const selectedAsset = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null);
watch(selectedAsset, (asset) => { if (!asset) selectedId.value = null; });
const workspace = ref<HTMLElement>();
const layout = useWorkspaceLayout(workspace);
watch(layout, async (mode) => {
  if (mode === 'compact' && document.activeElement?.classList.contains('library-splitter')) {
    await nextTick();
    workspace.value?.querySelector<HTMLElement>('.gallery-view-controls button')?.focus();
  }
}, { flush: 'pre' });

function moveRegion(event: KeyboardEvent) {
  if (event.key !== 'F6' || event.altKey || event.ctrlKey || event.metaKey) return;
  const root = workspace.value;
  if (!root) return;
  const regions = [root.querySelector('.library-panel'), root.querySelector('.asset-gallery'), root.querySelector('.detail-shell')];
  const current = regions.findIndex((region) => region?.contains(document.activeElement));
  const index = current < 0 ? (event.shiftKey ? 2 : 0) : (current + (event.shiftKey ? 2 : 1)) % 3;
  const selectors = ['[role="treeitem"][tabindex="0"]', '.asset-select[aria-pressed="true"], .gallery-view-controls button',
    libraryUi.detailsCollapsed ? '.detail-toggle' : '[role="tab"][aria-selected="true"], .detail-toggle'];
  // Prefer the selected asset/tab over a toolbar control when one exists.
  const preferred = index === 1 ? regions[index]?.querySelector<HTMLElement>('.asset-select[aria-pressed="true"]')
    : index === 2 && !libraryUi.detailsCollapsed ? regions[index]?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]') : null;
  (preferred ?? regions[index]?.querySelector<HTMLElement>(selectors[index]!))?.focus();
  event.preventDefault();
}
</script>

<template>
  <div ref="workspace" class="library-workspace" :data-layout="layout" @keydown="moveRegion" :style="{
    '--library-panel-width': `${libraryUi.panelWidth}px`,
    '--details-panel-width': libraryUi.detailsCollapsed ? 'auto' : '280px',
  }">
    <LibraryTreePanel :nodes="nodes" :empty-message="emptyMessage" :resizable="layout !== 'compact'"
      :selected-id="libraryUi.selectedFolderId" @select="selectLibraryFolder">
      <template #management><LibraryManagement /></template>
    </LibraryTreePanel>
    <AssetGallery :items="items" :selected-id="selectedId" @select="selectedId = $event">
      <template #filters><label class="tag-filter">사용자 태그 <select v-model="tag" aria-label="사용자 태그 필터"><option value="">전체 태그</option><option v-for="value in tags" :key="value" :value="value">{{ value }}</option></select></label></template>
    </AssetGallery>
    <AssetDetailsPanel :asset="selectedAsset" />
  </div>
</template>
