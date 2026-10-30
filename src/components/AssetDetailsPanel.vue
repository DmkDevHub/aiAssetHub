<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { libraryUi, setDetailsCollapsed } from "../stores/libraryUi";
import type { AssetSummary } from "../types/assets";
import ClassificationEditor from './ClassificationEditor.vue';
import ProvenancePanel from './ProvenancePanel.vue';
import ProvenanceHistory from './ProvenanceHistory.vue';
import AssetAnalysis from './AssetAnalysis.vue';
import TechnicalMetadata from './TechnicalMetadata.vue';
import AssetAnnotations from './AssetAnnotations.vue';
import AssetPackageMetadata from './AssetPackageMetadata.vue';
import PackageManager from './PackageManager.vue';
import GroupManager from './GroupManager.vue';
import AssetMetadataHistory from './AssetMetadataHistory.vue';
import AssetRelations from './AssetRelations.vue';
import AssetComposition from './AssetComposition.vue';
import AssetManagement from './AssetManagement.vue';
import AssetMetadata from './AssetMetadata.vue';

const props = withDefaults(defineProps<{ asset?: AssetSummary | null }>(), { asset: null });
const tabs = [{id:'info',name:'기본 정보'},{id:'classification',name:'분류·그룹'},{id:'source',name:'제작·출처'},{id:'rights',name:'라이선스·구매'},{id:'technical',name:'기술 정보'},{id:'analysis',name:'AI 분석 결과'},{id:'relations',name:'관계·이력'}] as const;
const visited=ref(new Set(['info']));

const activeTab = ref("info");
watch(activeTab,id=>{visited.value.add(id);});
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
          <AssetAnnotations :asset-id="asset.id" :user-tags="asset.userTags" />
          <AssetManagement :asset-id="asset.id" />

        </div>
        <div id="detail-panel-classification" role="tabpanel" aria-labelledby="detail-tab-classification" :hidden="activeTab!=='classification'"><ClassificationEditor v-if="visited.has('classification')" :asset-id="asset.id" /><GroupManager v-if="visited.has('classification')" :asset-id="asset.id" /><PackageManager v-if="visited.has('classification')" :asset-id="asset.id" /></div>
        <div id="detail-panel-source" role="tabpanel" aria-labelledby="detail-tab-source" :hidden="activeTab!=='source'"><ProvenancePanel v-if="visited.has('source')" :asset-id="asset.id" area="source" /></div>
        <div id="detail-panel-rights" role="tabpanel" aria-labelledby="detail-tab-rights" :hidden="activeTab!=='rights'"><ProvenancePanel v-if="visited.has('rights')" :asset-id="asset.id" area="license" /><AssetPackageMetadata v-if="visited.has('rights')" :asset-id="asset.id" /></div>
        <div id="detail-panel-technical" role="tabpanel" aria-labelledby="detail-tab-technical" :hidden="activeTab!=='technical'"><TechnicalMetadata v-if="visited.has('technical')" :asset-id="asset.id" /><AssetComposition v-if="visited.has('technical')" :asset-id="asset.id" /></div>
        <div id="detail-panel-relations" role="tabpanel" aria-labelledby="detail-tab-relations" :hidden="activeTab!=='relations'"><AssetRelations v-if="visited.has('relations')" :asset-id="asset.id" /><AssetMetadataHistory v-if="visited.has('relations')" :asset-id="asset.id" /><ProvenanceHistory v-if="visited.has('relations')" :asset-id="asset.id" /></div>
        <div id="detail-panel-analysis" role="tabpanel" aria-labelledby="detail-tab-analysis"
          :hidden="activeTab !== 'analysis'" tabindex="0">
          <AssetAnalysis v-if="asset.path" :asset-id="asset.id" :revision="`${asset.activeResultId}:${asset.lastAnalysisJobId}:${asset.lastAttemptState}`" :last-attempt-state="asset.lastAttemptState" :stale="asset.analysisStale" />
          <p v-else class="detail-analysis">{{ asset.analysisText || '제공된 분석 결과가 없습니다.' }}</p>
        </div>
      </template>
    </aside>
  </div>
</template>
