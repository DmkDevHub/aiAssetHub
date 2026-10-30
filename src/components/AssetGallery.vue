<script setup lang="ts">
import { libraryUi, setGalleryViewMode } from "../stores/libraryUi";
import type { AssetSummary } from "../types/assets";
import { executeUiCommand } from "../stores/operations";
import type { GalleryViewMode } from "../stores/libraryUi";
import { sortAssets } from '../services/assetSearch';
import EmbeddingTools from './EmbeddingTools.vue';
import ManualAnalysis from './ManualAnalysis.vue';
import BulkMetadata from './BulkMetadata.vue';
import MetadataExchange from './MetadataExchange.vue';
import AssetThumbnail from './AssetThumbnail.vue';
import { computed, ref, toRef, watch } from 'vue';
import {catalogFilters} from '../stores/catalogFilters';

const props = withDefaults(defineProps<{ items?: readonly AssetSummary[]; ranked?: boolean; orderedByCore?: boolean; selectedId?: string | null }>(), {
  items: () => [], selectedId: null,
});
const emit = defineEmits<{ select: [id: string | null] }>();
const sort = toRef(catalogFilters,'sort');
const page = ref(1);
const selection = ref(new Set<string>(props.selectedId ? [props.selectedId] : []));
const anchor = ref<string|null>(null);
const ordered = computed(() => props.orderedByCore ? props.items : sortAssets(props.items, sort.value));
const pages=computed(()=>Math.max(1,Math.ceil(ordered.value.length/60)));
const visible=computed(()=>ordered.value.slice((page.value-1)*60,page.value*60));
watch(()=>props.items,()=>{
  page.value=Math.min(page.value,pages.value);
  selection.value=new Set([...selection.value].filter((id)=>props.items.some((item)=>item.id===id)));
  if(anchor.value && !props.items.some((item)=>item.id===anchor.value))anchor.value=null;
});
watch(sort,()=>{page.value=1;});
function choose(event:MouseEvent,id:string){
  if(event.shiftKey && anchor.value){
    const start=ordered.value.findIndex((item)=>item.id===anchor.value);
    const end=ordered.value.findIndex((item)=>item.id===id);
    const ids=ordered.value.slice(Math.min(start,end),Math.max(start,end)+1).map((item)=>item.id);
    selection.value=new Set(event.ctrlKey || event.metaKey ? [...selection.value,...ids] : ids);
  }else if(event.ctrlKey || event.metaKey){
    if(selection.value.has(id))selection.value.delete(id);else selection.value.add(id);
    anchor.value=id;
  }else{selection.value=new Set([id]);anchor.value=id;}
  emit('select',selection.value.has(id)?id:[...selection.value].at(-1)??null);
}

function changeView(mode: GalleryViewMode) {
  if (libraryUi.galleryViewMode === mode) return;
  return executeUiCommand('gallery.view', () => setGalleryViewMode(mode));
}

function moveAssetFocus(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const buttons = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('.asset-select')];
  const index = buttons.indexOf(event.target as HTMLElement);
  if (index < 0) return;
  let target: number;
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') target = Math.min(index + 1, buttons.length - 1);
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') target = Math.max(index - 1, 0);
  else if (event.key === 'Home') target = 0;
  else if (event.key === 'End') target = buttons.length - 1;
  else return;
  event.preventDefault();
  buttons[target]?.focus();
}
</script>

<template>
  <section class="page asset-gallery" aria-labelledby="library-title">
    <ManualAnalysis :selected-ids="[...selection]" :folder-id="libraryUi.selectedFolderId" />
    <EmbeddingTools :selected="items.filter(i=>selection.has(i.id) && i.activeResultId).map(i=>({asset_id:i.id,result_id:i.activeResultId!}))" />
    <slot name="filters" />
    <header class="gallery-header">
      <div>
        <h1 id="library-title">라이브러리</h1>
        <p class="gallery-count">{{ items.length }}개 에셋</p>
      </div>
      <div class="gallery-view-controls" role="group" aria-label="에셋 보기 방식">
        <button type="button" :aria-pressed="libraryUi.galleryViewMode === 'grid'"
          @click="changeView('grid')">그리드</button>
        <button type="button" :aria-pressed="libraryUi.galleryViewMode === 'list'"
          @click="changeView('list')">목록</button>
      </div>
    </header>
    <div class="gallery-tools">
      <label>정렬 <select v-model="sort" aria-label="에셋 정렬"><option value="source">{{ ranked?'관련도순':'기본순' }}</option><option value="relevance">관련도순</option><option value="name">이름순</option><option value="kind">유형순</option><option value="size">크기 작은순</option><option value="size_desc">크기 큰순</option><option value="registered">등록일 최신순</option><option value="registered_asc">등록일 오래된순</option><option value="modified">수정일 최신순</option><option value="creator">제작사 이름순</option><option value="analysis">분석일 최신순</option></select></label>
      <p>크기는 가용한 고유 구성 파일 합계입니다. 누락만 있거나 값이 미확인인 항목은 마지막에 표시합니다. 정렬 변경은 선택을 유지하고 첫 페이지를 표시합니다.</p>
      <span class="selection-count">{{ selection.size }}개 선택</span>
      <button v-if="selection.size" type="button" @click="selection.clear();emit('select',null)">선택 해제</button>
      <p>Ctrl로 추가 선택 · Shift로 범위 선택</p>
    </div>

    <MetadataExchange v-if="selection.size" :asset-ids="[...selection]" /><BulkMetadata v-if="selection.size" :asset-ids="[...selection]" />

    <div v-if="items.length === 0" class="gallery-empty" role="status">
      <span class="gallery-empty-mark" aria-hidden="true">◇</span>
      <h2>표시할 에셋이 없습니다.</h2>
      <p>라이브러리가 비어 있습니다.</p>
    </div>
    <ul v-else-if="libraryUi.galleryViewMode === 'grid'" class="asset-grid" aria-label="에셋 그리드" @keydown="moveAssetFocus">
      <li v-for="item in visible" :key="item.id" class="asset-card" :data-asset-id="item.id"
        :class="{ 'is-selected': selection.has(item.id) }">
        <AssetThumbnail :key="`${item.id}:${item.mtimeNs}:${item.exists}`" :id="item.id" :kind="item.kind" :exists="item.exists" />
        <button type="button" class="asset-name asset-select" :title="item.name"
          :aria-pressed="selection.has(item.id)" @click="choose($event,item.id)">{{ item.name }}</button>
        <p class="asset-kind">{{ item.kind }}</p>
        <p v-if="item.searchScore!==undefined">관련도 {{ item.searchScore.toFixed(3) }} · {{ item.matchReason==='hybrid'?'키워드+의미':item.matchReason==='keyword'?'키워드':'의미' }}</p>
        <p class="asset-analysis-state">{{ item.hasActiveResult ? '분석 완료' : '미분석' }}{{ item.lastAttemptState==='failed' ? ' · 마지막 시도 실패' : '' }}{{ item.analysisStale ? ' · 원본 재확인 필요' : '' }}</p>
        <p v-if="item.userTags?.length" class="asset-tags">{{ item.userTags.join(", ") }}</p>
        <p v-if="item.scanChange && item.scanChange!=='unchanged'" class="asset-kind">{{ item.scanChange==='new'?'신규':item.scanChange==='changed'?'변경':item.scanChange==='missing'?'누락':'' }}</p>
      </li>
    </ul>
    <div v-else class="asset-list-container">
      <table class="asset-list" aria-label="에셋 목록">
        <thead><tr><th scope="col">에셋명</th><th scope="col">유형</th></tr></thead>
        <tbody @keydown="moveAssetFocus">
          <tr v-for="item in visible" :key="item.id" :data-asset-id="item.id"
            :class="{ 'is-selected': selection.has(item.id) }">
            <td><button type="button" class="asset-name asset-select" :title="item.name"
              :aria-pressed="selection.has(item.id)" @click="choose($event,item.id)">{{ item.name }}</button></td>
            <td>{{ item.kind }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <nav v-if="pages>1" aria-label="에셋 페이지">
      <button type="button" :disabled="page===1" @click="page--">이전 페이지</button>
      <span>{{ page }} / {{ pages }}</span>
      <button type="button" :disabled="page===pages" @click="page++">다음 페이지</button>
    </nav>
  </section>
</template>
