<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { libraryUi, setDetailsCollapsed } from "../stores/libraryUi";
import type { AssetSummary } from "../types/assets";
import AssetAnnotations from './AssetAnnotations.vue';
import AssetMetadata from './AssetMetadata.vue';

const props = withDefaults(defineProps<{ asset?: AssetSummary | null }>(), { asset: null });
const tabs = [{ id: "info", name: "기본 정보" }, { id: "analysis", name: "분석 결과" }] as const;
const activeTab = ref("info");
const tabList = ref<HTMLElement>();
watch(() => props.asset?.id, () => { activeTab.value = "info"; });

async function navigateTabs(event: KeyboardEvent, index: number) {
  let target: number;
  if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
  else if (event.key === "ArrowLeft") target = (index + tabs.length - 1) % tabs.length;
  else if (event.key === "Home") target = 0;
  else if (event.key === "End") target = tabs.length - 1;
  else return;
  event.preventDefault();
  activeTab.value = tabs[target]!.id;
  await nextTick();
  tabList.value?.querySelectorAll<HTMLElement>('[role="tab"]')[target]?.focus();
}
</script>

<template>
  <div class="detail-shell" :class="{ 'is-collapsed': libraryUi.detailsCollapsed }">
    <button type="button" class="detail-toggle" aria-controls="asset-details"
      :aria-expanded="!libraryUi.detailsCollapsed" @click="setDetailsCollapsed(!libraryUi.detailsCollapsed)">
      {{ libraryUi.detailsCollapsed ? '상세 펼치기' : '상세 접기' }}
    </button>
    <aside id="asset-details" :hidden="libraryUi.detailsCollapsed" aria-labelledby="detail-title">
      <h2 id="detail-title">에셋 상세</h2>
      <p v-if="!asset" class="detail-empty">에셋을 선택하면 상세 정보가 표시됩니다.</p>
      <template v-else>
        <p class="detail-asset-name">{{ asset.name }}</p>
        <div ref="tabList" role="tablist" aria-label="에셋 상세 항목" class="detail-tabs">
          <button v-for="(tab, index) in tabs" :id="`detail-tab-${tab.id}`" :key="tab.id" type="button"
            role="tab" :aria-selected="activeTab === tab.id" :tabindex="activeTab === tab.id ? 0 : -1"
            :aria-controls="`detail-panel-${tab.id}`" @click="activeTab = tab.id" @keydown="navigateTabs($event, index)">
            {{ tab.name }}
          </button>
        </div>
        <div id="detail-panel-info" role="tabpanel" aria-labelledby="detail-tab-info"
          :hidden="activeTab !== 'info'" tabindex="0">
          <dl><dt>에셋명</dt><dd>{{ asset.name }}</dd><dt>유형</dt><dd>{{ asset.kind }}</dd></dl>
          <AssetMetadata :asset="asset" />
          <AssetAnnotations :key="`${asset.id}:${asset.userTags?.join(',')}`" :asset-id="asset.id" />
        </div>
        <div id="detail-panel-analysis" role="tabpanel" aria-labelledby="detail-tab-analysis"
          :hidden="activeTab !== 'analysis'" tabindex="0">
          <p class="detail-analysis">{{ asset.analysisText || '제공된 분석 결과가 없습니다.' }}</p>
        </div>
      </template>
    </aside>
  </div>
</template>
