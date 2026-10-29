<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {collectionUi} from '../stores/collections';
import PackageManager from '../components/PackageManager.vue';
import GroupManager from '../components/GroupManager.vue';
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
import { invoke, isTauri } from '@tauri-apps/api/core';
import { coreSearch } from '../services/coreSearch';
import { keywordFilter, stateFilter } from '../services/assetSearch';
import { folderNodes, filterFolder, type FolderNode } from '../services/assetFolders';

onMounted(() => { void refreshLibraries().then((ok)=>{ if(ok){if(libraries.roots.length)void refreshAssets();else resetAssets();} }); });
const emptyMessage = computed(() => libraries.loading ? '등록 폴더를 불러오는 중입니다.'
  : libraries.error ? '등록 폴더를 확인하지 못했습니다.' : '등록된 폴더가 없습니다.');

const props = defineProps<{ items?: readonly AssetSummary[] }>();
const availableItems = computed(() => assets.items.filter((item) => libraries.roots.some((root) => root.id===item.libraryId)));
const searchMode=ref('keyword'),semanticResults=ref<{id:string;score:number;reason:string}[]|null>(null);
let semanticTimer:ReturnType<typeof setInterval>|undefined;
const tag = ref(''), kind = ref(''), analysis = ref('');
const sourceItems = computed(() => props.items ?? availableItems.value);
const kinds=computed(()=>[...new Set(sourceItems.value.map(item=>item.kind))].sort());
const tags = computed(() => [...new Set(sourceItems.value.flatMap(item => [...item.userTags ?? []]))].sort((a,b)=>a.localeCompare(b,'ko')));
const searchIds = ref<Set<string>|null>(null), searchError=ref(''), searching=ref(false);
let searchGeneration=0;
onBeforeUnmount(()=>{searchGeneration++;if(semanticTimer)clearInterval(semanticTimer);});
watch([()=>searchState.searchQuery, sourceItems, searchMode, tag, kind, analysis, ()=>libraryUi.selectedFolderId,()=>collectionUi.groupId,()=>collectionUi.revision], async ([query])=>{
  const token=++searchGeneration; semanticResults.value=null;if(semanticTimer)clearInterval(semanticTimer);searchIds.value=null; searchError.value=''; searching.value=false;
  if(searchMode.value!=='keyword' || (!query.trim()&&!collectionUi.groupId) || !isTauri())return;
  if(query.length>256 || query.trim().split(/\s+/).length>16){searchError.value='검색어는 256자, 16개 단어까지 입력하세요.';return;}
  searching.value=true;
  try {
    const ids=new Set<string>();
    if(collectionUi.groupId){
      let cursor:string|null=null;
      do{
        const r: {ok:boolean;data:{ids:string[];next_cursor:string|null}}=await invoke('group_query',{groupId:collectionUi.groupId,query,criteria:searchCriteria(),afterId:cursor});
        if(token!==searchGeneration)return;if(!r.ok||!Array.isArray(r.data?.ids))throw new Error();
        for(const id of r.data.ids){if(ids.has(id))throw new Error();ids.add(id);}
        cursor=r.data.next_cursor;if(cursor!==null&&(cursor!==r.data.ids.at(-1)||ids.size>100000))throw new Error();
      }while(cursor);
    }else{for(const id of await coreSearch(query,()=>token===searchGeneration))ids.add(id);}
    if(token===searchGeneration)searchIds.value=ids;
  }
  catch { if(token===searchGeneration)searchError.value=collectionUi.groupId?'그룹 검색을 완료하지 못했습니다. 다시 조회하세요.':'전문 검색을 완료하지 못했습니다. 현재 파일명·태그 일치 결과를 표시합니다.'; }
  finally { if(token===searchGeneration)searching.value=false; }
}, {immediate:true});
function searchCriteria(){
 let library:string|null=null,parts:string[]=[];
 const selected=libraryUi.selectedFolderId;
 if(selected?.startsWith('folder:')){const path=JSON.parse(selected.slice(7)) as string[];library=path[0]??null;parts=path.slice(1);}
 else library=selected;
 return {library_id:library,folder_parts:parts,kind:kind.value,tag:tag.value,analysis:analysis.value,...(collectionUi.groupId?{group_id:collectionUi.groupId}:{})};
}
async function semanticSearch(){
 if(!isTauri() || searching.value || !searchState.searchQuery.trim())return;
 const token=++searchGeneration;searching.value=true;searchError.value='';semanticResults.value=null;
 if(semanticTimer)clearInterval(semanticTimer);
 try{
  const start=await invoke<{ok:boolean;data:{jobId:string}}>('embedding_query',{query:searchState.searchQuery,mode:searchMode.value,confirmed:true,criteria:searchCriteria()});if(token!==searchGeneration)return;if(!start.ok)throw new Error();
  let polling=false;
  const poll=async()=>{if(polling)return;polling=true;try{
   const r=await invoke<{ok:boolean;data:{status:string;results?:NonNullable<typeof semanticResults.value>}}>('embedding_work',{jobId:start.data.jobId});if(token!==searchGeneration)return;
   if(!r.ok || !['queued','running','completed'].includes(r.data.status))throw new Error();
   if(r.data.status==='completed'){semanticResults.value=r.data.results??[];searching.value=false;if(semanticTimer)clearInterval(semanticTimer);}
  }catch{if(token===searchGeneration){searching.value=false;searchError.value='의미 검색에 실패했습니다. 현재 모델의 임베딩 준비 상태를 확인하세요.';if(semanticTimer)clearInterval(semanticTimer);}}finally{polling=false;}};
  semanticTimer=setInterval(()=>{void poll();},500);void poll();
 }catch{if(token===searchGeneration){searching.value=false;searchError.value='의미 검색을 시작하지 못했습니다. 임베딩 모델과 준비된 결과를 확인하세요.';}}
}
const items = computed(() => {
  const folderItems=filterFolder(sourceItems.value, libraryUi.selectedFolderId);
  if(searchMode.value!=='keyword' && searchState.searchQuery.trim()) {
    const ranked=(semanticResults.value??[]).flatMap(row=>{const item=folderItems.find(i=>i.id===row.id);return item?[{...item,searchScore:row.score,matchReason:row.reason}]:[];});
    return stateFilter(keywordFilter(ranked,'',tag.value),kind.value,analysis.value);
  }
  if(collectionUi.groupId&&!searchIds.value)return [];
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
      <template #management><LibraryManagement /><GroupManager /><PackageManager /></template>
    </LibraryTreePanel>
    <AssetGallery :ranked="searchMode!=='keyword' && semanticResults!==null" :items="items" :selected-id="selectedId" @select="selectedId = $event">
      <template #filters><p v-if="collectionUi.groupId">그룹 필터: {{ collectionUi.groupId }}</p><label>검색 방식 <select v-model="searchMode" aria-label="검색 방식"><option value="keyword">키워드</option><option value="semantic">의미 검색</option><option value="hybrid">키워드+의미 혼합</option></select></label>
      <button v-if="searchMode!=='keyword'" type="button" :disabled="searching || !searchState.searchQuery.trim()" @click="semanticSearch">로컬 검색 실행</button>
      <p v-if="searchMode!=='keyword'">입력만으로 임베딩을 생성하지 않습니다. 준비된 벡터가 있을 때 실행한 검색어만 로컬 모델에 전달하며, 기본순은 관련도 상위 50개입니다. 점수는 확률이 아닙니다. 혼합 모드에서 준비된 벡터가 없으면 키워드 결과만 표시합니다.</p><p v-if="searchMode==='keyword' && searchState.searchQuery.trim()">파일명·사용자 정보·현재 활성 AI 설명/태그에서 검색합니다.</p><p v-if="searching" role="status">로컬 전문 검색 중…</p><p v-if="searchError" role="alert">{{ searchError }}</p><label class="tag-filter">사용자 태그 <select v-model="tag" aria-label="사용자 태그 필터"><option value="">전체 태그</option><option v-for="value in tags" :key="value" :value="value">{{ value }}</option></select></label>
      <label class="tag-filter">타입 <select v-model="kind" aria-label="타입 필터"><option value="">전체 타입</option><option v-for="value in kinds" :key="value" :value="value">{{ value }}</option></select></label>
      <label class="tag-filter">분석 상태 <select v-model="analysis" aria-label="분석 상태 필터"><option value="">전체 상태</option><option value="unanalyzed">미분석</option><option value="completed">분석 완료</option><option value="failed">마지막 시도 실패</option></select></label>
      </template>
    </AssetGallery>
    <AssetDetailsPanel :asset="selectedAsset" />
  </div>
</template>
