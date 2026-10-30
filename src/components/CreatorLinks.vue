<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {isTauri} from '@tauri-apps/api/core';
import {metadata,catalogOptions,type CatalogOption} from '../services/metadata';
import {collectionsChanged} from '../stores/collections';
const props=defineProps<{subject:{kind:string;id:string}}>();type Link={creator_id:string;role:string};type State={links:Link[];items:{id:string;name:string;role:string;enabled:boolean}[];revision:number};
const state=ref<State>(),links=ref<Link[]>([]),options=ref<CatalogOption[]>([]),selected=ref(''),role=ref('creator'),busy=ref(false),error=ref(''),conflict=ref(false);let epoch=0;onBeforeUnmount(()=>epoch++);
function cancel(){links.value=state.value?.links.map(i=>({...i}))??[];}
async function load(){if(!isTauri())return;const token=++epoch;busy.value=true;error.value='';try{const [r,o]=await Promise.all([metadata<State>('creator.links',{subject:props.subject}),catalogOptions('creators')]);if(token!==epoch)return;state.value=r;options.value=o;cancel();conflict.value=false;}catch{if(token===epoch)error.value='제작 주체 연결을 조회하지 못했습니다.';}finally{if(token===epoch)busy.value=false;}}
function add(){if(selected.value&&!links.value.some(i=>i.creator_id===selected.value&&i.role===role.value)&&links.value.length<16)links.value.push({creator_id:selected.value,role:role.value});}
async function save(){if(!state.value||busy.value||conflict.value)return;const token=epoch;busy.value=true;error.value='';try{const r=await metadata<State>('creator.links.save',{subject:props.subject,links:links.value.map(i=>({...i})),expected_revision:state.value.revision});if(token!==epoch)return;state.value=r;cancel();collectionsChanged();}catch(e){if(token===epoch){conflict.value=e instanceof Error&&e.message==='METADATA_CONFLICT';error.value=conflict.value?'연결이 변경되었습니다. 초안을 유지하며 다시 조회가 필요합니다.':'연결을 저장하지 못했습니다. 초안을 유지합니다.';}}finally{if(token===epoch)busy.value=false;}}
watch(()=>`${props.subject.kind}:${props.subject.id}`,()=>{epoch++;state.value=undefined;links.value=[];busy.value=false;void load();},{immediate:true});
</script>
<template><section aria-label="제작 주체 역할 연결"><h3>제작 주체</h3><button type="button" :disabled="busy" @click="load">제작 연결 다시 조회</button><p v-if="error" role="alert">{{error}}</p>
 <fieldset :disabled="busy||!state"><label>공유 주체<select v-model="selected"><option value="">선택</option><option v-for="o in options" :key="o.id" :value="o.id">{{o.name}}</option></select></label>
 <label>제작 역할<select v-model="role"><option value="creator">제작자</option><option value="producer">제작사</option><option value="distributor">배포사</option></select></label><button type="button" @click="add">연결에 추가</button>
 <ul><li v-for="(link,index) in links" :key="`${link.creator_id}:${link.role}`">{{options.find(i=>i.id===link.creator_id)?.name||state?.items.find(i=>i.id===link.creator_id)?.name||link.creator_id}} · {{link.role}}<button type="button" @click="links.splice(index,1)">이 역할 해제</button></li></ul>
 <button type="button" :disabled="conflict" @click="save">제작 연결 저장</button><button type="button" @click="cancel">제작 연결 취소</button></fieldset></section></template>
