<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
import { isTauri } from '@tauri-apps/api/core';
import { coreSearch } from '../services/coreSearch';
import { keywordFilter, stateFilter } from '../services/assetSearch';
import { folderNodes, filterFolder, type FolderNode } from '../services/assetFolders';

onMounted(() => { void refreshLibraries().then((ok)=>{ if(ok){if(libraries.roots.length)void refreshAssets();else resetAssets();} }); });
const emptyMessage = computed(() => libraries.loading ? '등록 폴더를 불러오는 중입니다.'
  : libraries.error ? '등록 폴더를 확인하지 못했습니다.' : '등록된 폴더가 없습니다.');

const props = defineProps<{ items?: readonly AssetSummary[] }>();
const availableItems = computed(() => assets.items.filter((item) => libraries.roots.some((root) => root.id===item.libraryId)));
const tag = ref(''), kind = ref(''), analysis = ref('');
const sourceItems = computed(() => props.items ?? availableItems.value);
const kinds=computed(()=>[...new Set(sourceItems.value.map(item=>item.kind))].sort());
const tags = computed(() => [...new Set(sourceItems.value.flatMap(item => [...item.userTags ?? []]))].sort((a,b)=>a.localeCompare(b,'ko')));
const searchIds = ref<Set<string>|null>(null), searchError=ref(''), searching=ref(false);
let searchGeneration=0;
onBeforeUnmount(()=>{searchGeneration++;});
watch([()=>searchState.searchQuery, sourceItems], async ([query])=>{
  const token=++searchGeneration; searchIds.value=null; searchError.value=''; searching.value=false;
  if(!query.trim() || !isTauri())return;
  if(query.length>256 || query.trim().split(/\s+/).length>16){searchError.value='검색어는 256자, 16개 단어까지 입력하세요.';return;}
  searching.value=true;
  try { const ids=await coreSearch(query,()=>token===searchGeneration); if(token===searchGeneration)searchIds.value=ids; }
  catch { if(token===searchGeneration)searchError.value='전문 검색을 완료하지 못했습니다. 현재 파일명·태그 일치 결과를 표시합니다.'; }
  finally { if(token===searchGeneration)searching.value=false; }
}, {immediate:true});
const items = computed(() => {
  const folderItems=filterFolder(sourceItems.value, libraryUi.selectedFolderId);
  const matches=searchIds.value ? keywordFilter(folderItems.filter(item=>searchIds.value!.has(item.id)), '', tag.value)
    : keywordFilter(folderItems, searchState.searchQuery, tag.value);
  return stateFilter(matches,kind.value,analysis.value);
});
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
      <template #filters><p v-if="searching" role="status">로컬 전문 검색 중…</p><p v-if="searchError" role="alert">{{ searchError }}</p><label class="tag-filter">사용자 태그 <select v-model="tag" aria-label="사용자 태그 필터"><option value="">전체 태그</option><option v-for="value in tags" :key="value" :value="value">{{ value }}</option></select></label>
      <label class="tag-filter">타입 <select v-model="kind" aria-label="타입 필터"><option value="">전체 타입</option><option v-for="value in kinds" :key="value" :value="value">{{ value }}</option></select></label>
      <label class="tag-filter">분석 상태 <select v-model="analysis" aria-label="분석 상태 필터"><option value="">전체 상태</option><option value="unanalyzed">미분석</option><option value="completed">분석 완료</option><option value="failed">마지막 시도 실패</option></select></label>
      </template>
    </AssetGallery>
    <AssetDetailsPanel :asset="selectedAsset" />
  </div>
</template>
