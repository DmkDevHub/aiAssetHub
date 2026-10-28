<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { invoke,isTauri } from '@tauri-apps/api/core';
const props=defineProps<{assetId:string;revision?:string|null}>();
const active=ref<{description:string;tags:string[];provider?:string;modelId?:string;createdAt:string}|null>(null),error=ref('');let generation=0;
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
  <template v-if="active"><h3>AI 분석 결과</h3><p>{{ active.description }}</p><p>AI 태그: {{ active.tags.join(', ') || '없음' }}</p><p>출처: {{ active.provider }} · {{ active.modelId }} · {{ active.createdAt }}</p></template>
  <p v-else-if="!error">저장된 성공 분석 결과가 없습니다.</p>
  <button v-if="!historyLoaded || cursor" type="button" :disabled="historyBusy" @click="loadHistory">{{ historyLoaded?'이전 시도 더 보기':'분석 이력 조회' }}</button>
  <p v-if="historyLoaded && !history.length">저장된 실행 이력이 없습니다.</p>
  <ol class="analysis-history"><li v-for="item in history" :key="item.id">
   <p>{{ item.createdAt }} · {{ item.status }} · {{ item.modelId??'모델 정보 없음' }}{{ item.active?' · 현재 활성 결과':'' }}</p>
   <p v-if="item.description">{{ item.description }}</p><p v-if="item.errorCode">{{ item.errorCode }}</p>
  </li></ol>
 </section>
</template>
