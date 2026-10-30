<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { invoke,isTauri } from '@tauri-apps/api/core';
import AnalysisReview from './AnalysisReview.vue';
const props=defineProps<{assetId:string;revision?:string|null;lastAttemptState?:string|null;stale?:boolean}>();
const active=ref<{id?:string;description:string;tags:string[];provider?:string;modelId?:string;actualModelId?:string;providerReportedCostUsd?:string;createdAt:string;features?:{technical?:{width?:number;height?:number;hasTransparentPixels?:boolean};suggestions?:{action?:string;loopRecommended?:boolean;primary?:string;roles?:string[];styles?:string[];colors?:string[];material?:string[]};audioSuggestions?:{soundClass?:string;mood?:string[];transcript?:string}}}|null>(null),error=ref('');let generation=0;
const history=ref<{id:string;status:string;createdAt:string;description:string|null;tags:string[];modelId?:string;active:boolean;errorCode?:string}[]>([]),cursor=ref<string|null>(null),historyLoaded=ref(false),historyBusy=ref(false);
onBeforeUnmount(()=>{generation++;});
watch(()=>[props.assetId,props.revision],async()=>{
 const token=++generation;active.value=null;error.value='';history.value=[];cursor.value=null;historyLoaded.value=false;if(!isTauri())return;
 try{
  const result=await invoke<{ok:boolean;data:{active:typeof active.value}}>('asset_analysis',{assetId:props.assetId});
  if(token!==generation)return;if(!result.ok)throw new Error();active.value=result.data.active;
 }catch{if(token===generation)error.value='분석 결과를 불러오지 못했습니다.';}
},{immediate:true});
async function loadHistory(){
 if(historyBusy.value || !isTauri())return;historyBusy.value=true;const token=generation;
 try{
  const result=await invoke<{ok:boolean;data:{items:typeof history.value;next_cursor:string|null}}>('asset_analysis_history',{assetId:props.assetId,afterId:cursor.value});
  if(token!==generation)return;if(!result.ok || !Array.isArray(result.data?.items))throw new Error();
  history.value.push(...result.data.items);cursor.value=result.data.next_cursor;historyLoaded.value=true;
 }catch{if(token===generation)error.value='분석 이력을 불러오지 못했습니다.';}
 finally{historyBusy.value=false;}
}
</script>
<template>
 <section class="asset-analysis" aria-label="저장된 AI 분석 결과">
  <p v-if="error" role="alert">{{ error }}</p>
  <p v-if="active && lastAttemptState==='failed'" class="analysis-retained" role="status">마지막 분석은 실패했습니다. 이전 성공 결과를 유지합니다.</p>
  <p v-if="active && stale" role="status">원본 변경 또는 검증 정보 미보유로 재확인이 필요한 이전 결과입니다.</p>
  <template v-if="active"><h3>AI 분석 결과</h3><p>{{ active.description }}</p><p>AI 태그: {{ active.tags.join(', ') || '없음' }}</p><p>출처: {{ active.provider }} · {{ active.actualModelId??active.modelId }}{{ active.actualModelId?'':' (요청 프로필, 실제 응답 모델 기록 없음)' }} · {{ active.createdAt }}</p><p v-if="active.providerReportedCostUsd">공급자 보고 비용: {{ active.providerReportedCostUsd }} USD (청구서와 다를 수 있음)</p></template>
  <p v-else-if="!error">저장된 성공 분석 결과가 없습니다.</p>
  <AnalysisReview v-if="active?.id && active?.features?.suggestions" :asset-id="assetId" :result-id="active.id" /><div v-if="active?.features" class="analysis-features">
   <p v-if="active.features.audioSuggestions">AI 오디오 제안 (미확정): {{ active.features.audioSuggestions.soundClass??'미확인' }} · 분위기 {{ active.features.audioSuggestions.mood?.join(', ')||'미확인' }} · 전사 {{ active.features.audioSuggestions.transcript??'미확인' }}</p>
   <p v-if="active.features.technical?.width">파서 관측: {{ active.features.technical.width }} × {{ active.features.technical.height }} · 투명 픽셀 {{ active.features.technical.hasTransparentPixels?'있음':'없음' }}</p>
   <p v-if="active.features.suggestions?.action">AI 동작 제안: {{ active.features.suggestions.action }} · 루프 추천 {{ active.features.suggestions.loopRecommended??'미확인' }} (파일 루프 설정과 별개)</p><p v-if="active.features.suggestions">AI 제안 (미확정): 분류 {{ active.features.suggestions.primary??'미확인' }} · 역할 {{ active.features.suggestions.roles?.join(', ')||'미확인' }} · 스타일 {{ active.features.suggestions.styles?.join(', ')||'미확인' }} · 색상 {{ active.features.suggestions.colors?.join(', ')||'미확인' }} · 소재 {{ active.features.suggestions.material?.join(', ')||'미확인' }}</p>
  </div>
  <button v-if="!historyLoaded || cursor" type="button" :disabled="historyBusy" @click="loadHistory">{{ historyLoaded?'이전 시도 더 보기':'분석 이력 조회' }}</button>
  <p v-if="historyLoaded && !history.length">저장된 실행 이력이 없습니다.</p>
  <ol class="analysis-history"><li v-for="item in history" :key="item.id">
   <p>{{ item.createdAt }} · {{ item.status }} · {{ item.modelId??'모델 정보 없음' }}{{ item.active?' · 현재 활성 결과':'' }}</p>
   <p v-if="item.description">{{ item.description }}</p><p v-if="item.errorCode">{{ item.errorCode }}</p>
  </li></ol>
 </section>
</template>
