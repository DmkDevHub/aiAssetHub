<script setup lang="ts">
import { ref,watch,onBeforeUnmount } from 'vue';
import { metadata } from '../services/metadata';
const props=defineProps<{assetId:string}>();
const stale=ref(false);
const observation=ref<unknown>(null),busy=ref(false),error=ref('');let generation=0;
onBeforeUnmount(()=>{generation++;});
watch(()=>props.assetId,()=>{generation++;observation.value=null;stale.value=false;error.value='';void read();},{immediate:true});
async function read(){const token=generation;try{const result=await metadata<{observation:unknown;stale?:boolean}>('asset.technical',{asset_id:props.assetId});if(token===generation){observation.value=result.observation;stale.value=result.stale??false;}}catch{if(token===generation)error.value='기술 정보를 불러오지 못했습니다.';}}
async function collect(){if(busy.value)return;busy.value=true;error.value='';const token=++generation;try{const result=await metadata<{observation:unknown;stale?:boolean}>('asset.technical.collect',{asset_id:props.assetId,confirmed:true});if(token===generation){observation.value=result.observation;stale.value=result.stale??false;}}catch{if(token===generation)error.value='기술 추출 실패: 미지원·잘못된 형식·크기 제한·파일 접근 상태를 확인하세요.';}finally{busy.value=false;}}
</script>
<template><section class="technical-metadata" aria-label="파서 기술 관측"><h3>파서 기술 관측</h3><p>기술 정보 수집은 AI를 호출하지 않습니다. 지원 형식만 관측하며 모델의 의미 분석과 별도로 저장합니다.</p><button type="button" :disabled="busy" @click="collect">기술 정보 수집</button><p v-if="error" role="alert">{{ error }}</p><p v-if="stale" role="status">원본 변경·누락으로 재확인이 필요한 저장 관측입니다.</p><pre v-if="observation">{{ JSON.stringify(observation,null,2) }}</pre><p v-else>저장된 관측 없음</p></section></template>
