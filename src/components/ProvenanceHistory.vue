<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {metadata} from '../services/metadata';
import {isTauri} from '@tauri-apps/api/core';
const props=defineProps<{assetId:string}>();type Event={id:string;field:string;action:string;actor:string;revision:number;createdAt:string;before:unknown;after:unknown};const items=ref<Event[]>([]),cursor=ref<string|null>(null),busy=ref(false),error=ref(''),privateApproved=ref(false);let epoch=0;onBeforeUnmount(()=>epoch++);
function changePrivacy(){epoch++;items.value=[];cursor.value=null;busy.value=false;}
async function load(more=false){if(busy.value||!isTauri())return;const token=epoch;busy.value=true;error.value='';try{const r=await metadata<{items:Event[];next_cursor:string|null}>('provenance.history',{subject:{kind:'asset',id:props.assetId},after_id:more?cursor.value:null,include_private:privateApproved.value,confirmed:privateApproved.value});if(token!==epoch)return;items.value=more?[...items.value,...r.items]:r.items;cursor.value=r.next_cursor;}catch{if(token===epoch)error.value='제작·권리 이력을 조회하지 못했습니다. 기존 행은 유지됩니다.';}finally{if(token===epoch)busy.value=false;}}
watch(()=>props.assetId,()=>{epoch++;items.value=[];cursor.value=null;busy.value=false;privateApproved.value=false;void load();},{immediate:true});
</script>
<template><section aria-label="제작·권리 변경 이력"><h3>제작·권리 변경 이력</h3><label><input v-model="privateApproved" type="checkbox" @change="changePrivacy" />민감 원문 포함 조회 승인</label><button type="button" :disabled="busy" @click="load()">이력 다시 조회</button><button v-if="cursor" type="button" :disabled="busy" @click="load(true)">제작 이력 더 보기</button><p v-if="error" role="alert">{{error}}</p><ol><li v-for="item in items" :key="item.id"><p>{{item.field}} · {{item.action}} · {{item.actor}} · 버전 {{item.revision}} · {{item.createdAt}}</p><pre>{{JSON.stringify(item.before,null,2)}} → {{JSON.stringify(item.after,null,2)}}</pre></li></ol></section></template>
