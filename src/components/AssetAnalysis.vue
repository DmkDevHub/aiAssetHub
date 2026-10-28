<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { invoke,isTauri } from '@tauri-apps/api/core';
const props=defineProps<{assetId:string;revision?:string|null}>();
const active=ref<{description:string;tags:string[];provider?:string;modelId?:string;createdAt:string}|null>(null),error=ref('');let generation=0;
onBeforeUnmount(()=>{generation++;});
watch(()=>[props.assetId,props.revision],async()=>{
 const token=++generation;active.value=null;error.value='';if(!isTauri())return;
 try{
  const result=await invoke<{ok:boolean;data:{active:typeof active.value}}>('asset_analysis',{assetId:props.assetId});
  if(token!==generation)return;if(!result.ok)throw new Error();active.value=result.data.active;
 }catch{if(token===generation)error.value='분석 결과를 불러오지 못했습니다.';}
},{immediate:true});
</script>
<template>
 <section class="asset-analysis" aria-label="저장된 AI 분석 결과">
  <p v-if="error" role="alert">{{ error }}</p>
  <template v-if="active"><h3>AI 분석 결과</h3><p>{{ active.description }}</p><p>AI 태그: {{ active.tags.join(', ') || '없음' }}</p><p>출처: {{ active.provider }} · {{ active.modelId }} · {{ active.createdAt }}</p></template>
  <p v-else-if="!error">저장된 성공 분석 결과가 없습니다.</p>
 </section>
</template>
