<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
import type { AssetSummary } from '../types/assets';
const props=defineProps<{asset:AssetSummary}>();
interface Metadata {availability:string;path?:string;size?:number;modified?:number;width?:number;height?:number}
const metadata=ref<Metadata|null>(null);
const message=ref('');
let generation=0;
watch(()=>props.asset.id,async ()=>{
  const token=++generation;
  metadata.value=null; message.value='';
  if (!isTauri() || !props.asset.path) return;
  message.value='파일 정보를 확인하는 중입니다.';
  try {
    const response=await invoke<{ok:boolean;data:Metadata}>('get_asset',{assetId:props.asset.id});
    if(token!==generation)return;
    if(!response.ok || !['present','missing','unavailable'].includes(response.data?.availability))throw new Error();
    if(response.data.availability==='present' && (typeof response.data.path!=='string' || !Number.isSafeInteger(response.data.size) || response.data.size! < 0 || !Number.isFinite(response.data.modified)))throw new Error();
    metadata.value=response.data;
    message.value=response.data.availability==='present'?'':response.data.availability==='missing'?'파일이 없습니다.':'파일 정보를 읽을 수 없습니다.';
  }catch{if(token===generation)message.value='파일 정보를 읽을 수 없습니다.';}
},{immediate:true});
onBeforeUnmount(()=>{generation++;});
</script>
<template>
  <p v-if="message" role="status">{{ message }}</p>
  <dl v-if="metadata">
    <template v-if="metadata.path"><dt>경로</dt><dd>{{ metadata.path }}</dd></template>
    <template v-if="metadata.availability==='present'">
      <dt>크기</dt><dd>{{ metadata.size }} 바이트</dd>
      <dt>수정 시각</dt><dd>{{ metadata.modified === undefined ? '' : new Date(metadata.modified).toLocaleString('ko-KR') }}</dd>
      <template v-if="metadata.width && metadata.height"><dt>해상도</dt><dd>{{ metadata.width }} × {{ metadata.height }}</dd></template>
    </template>
  </dl>
</template>
