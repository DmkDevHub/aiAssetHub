<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
const props=defineProps<{assetId:string}>();
type Entry={id:number;field:string;revision:number;action:string;before:unknown;after:unknown;createdAt:string;actor:string};
const items=ref<Entry[]>([]),cursor=ref<number|null>(null),busy=ref(false),loaded=ref(false),error=ref('');
let generation=0;onBeforeUnmount(()=>{generation++;});
watch(()=>props.assetId,()=>{generation++;items.value=[];cursor.value=null;busy.value=false;loaded.value=false;error.value='';});
async function load(more=false){
 if(busy.value||!isTauri())return;
 const token=generation;busy.value=true;error.value='';
 try {const r=await invoke<{ok:boolean;data:{items:Entry[];next_cursor:number|null}}>('asset_metadata_history',{assetId:props.assetId,beforeId:more?cursor.value:null});if(token!==generation)return;if(!r.ok||!Array.isArray(r.data?.items))throw new Error();items.value=more?[...items.value,...r.data.items]:r.data.items;cursor.value=r.data.next_cursor;loaded.value=true;}
 catch {if(token===generation)error.value='변경 이력을 불러오지 못했습니다.';}
 finally {if(token===generation)busy.value=false;}
}
</script>
<template>
 <section class="asset-metadata-history" aria-label="메타데이터 변경 이력">
  <h3>변경 이력</h3>
  <button type="button" :disabled="busy" @click="load()">{{ loaded?'변경 이력 새로고침':'변경 이력 보기' }}</button>
  <p v-if="loaded&&!items.length">기록된 변경이 없습니다.</p>
  <ol><li v-for="item in items" :key="item.id">
   <p>{{ item.createdAt }} · {{ item.actor }} · {{ item.field }} · {{ item.action }} · 버전 {{ item.revision }}</p>
   <details><summary>이전 값 / 새 값</summary><p>이전 값</p><pre>{{ JSON.stringify(item.before,null,2) }}</pre><p>새 값</p><pre>{{ JSON.stringify(item.after,null,2) }}</pre></details>
  </li></ol>
  <p>값이 큰 기록은 truncated 표시가 있는 미리보기로 제공됩니다. 원본 이력은 DB에 보존됩니다.</p>
  <button v-if="cursor" type="button" :disabled="busy" @click="load(true)">이전 변경 더 보기</button>
  <p v-if="error" role="alert">{{ error }}</p>
 </section>
</template>
<style scoped>
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
