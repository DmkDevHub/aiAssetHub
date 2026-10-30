<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {isTauri} from '@tauri-apps/api/core';
import {metadata,catalogOptions,type CatalogOption} from '../services/metadata';
import {collectionsChanged} from '../stores/collections';
type Assignment={primary:string|null;navigation:string[];facets:Record<string,string[]>;type_version:string;facet_version:string};
type State={value:Assignment;revision:number;source:string;status:string};
const props=defineProps<{assetId:string}>();const state=ref<State>(),draft=ref<Assignment>(),types=ref<CatalogOption[]>([]),facets=ref<CatalogOption[]>([]),busy=ref(false),error=ref(''),conflict=ref(false);let epoch=0;onBeforeUnmount(()=>epoch++);
const axes=[['role','역할'],['style','스타일'],['genre','장르'],['view','시점'],['dimension','차원'],['engine','엔진']] as const;
function cancel(){if(state.value)draft.value=structuredClone(JSON.parse(JSON.stringify(state.value.value)));if(draft.value)for(const [axis] of axes)if(!Array.isArray(draft.value.facets[axis]))draft.value.facets[axis]=[];}
async function load(){if(!isTauri())return;const token=++epoch;busy.value=true;error.value='';try{
 const result=await metadata<State>('catalog.classification',{asset_id:props.assetId});
 const [t,f]=await Promise.all([catalogOptions('types',result.value.type_version),catalogOptions('facets',result.value.facet_version)]);if(token!==epoch)return;
 state.value=result;types.value=t;facets.value=f;cancel();conflict.value=false;
 }catch{if(token===epoch)error.value='분류를 불러오지 못했습니다. 기존 초안은 유지됩니다.';}finally{if(token===epoch)busy.value=false;}}
async function save(){if(!draft.value||!state.value||busy.value||conflict.value)return;const token=epoch;busy.value=true;error.value='';try{
 const result=await metadata<State>('catalog.classification.save',{asset_id:props.assetId,value:JSON.parse(JSON.stringify(draft.value)),expected_revision:state.value.revision,confirmed:true});if(token!==epoch)return;state.value=result;cancel();collectionsChanged();
 }catch(e){if(token===epoch){conflict.value=e instanceof Error&&e.message==='METADATA_CONFLICT';error.value=conflict.value?'다른 분류가 저장되었습니다. 초안을 확인한 후 다시 조회하세요.':'분류를 저장하지 못했습니다. 초안을 유지합니다.';}}finally{if(token===epoch)busy.value=false;}}
watch(()=>props.assetId,()=>{epoch++;state.value=undefined;draft.value=undefined;busy.value=false;void load();},{immediate:true});
</script>
<template><section aria-label="분류 편집"><h3>사용자 분류</h3><button type="button" :disabled="busy" @click="load">분류 다시 조회</button><p v-if="error" role="alert">{{error}}</p>
 <form v-if="draft&&state" @submit.prevent="save"><p>근거: {{state.source||'미확인'}} · {{state.status}} · 엔진 선언은 호환성 검증이 아닙니다.</p><fieldset :disabled="busy">
 <label>대표 유형<select v-model="draft.primary"><option :value="null">미분류</option><option v-for="t in types" :key="t.id" :value="t.id">{{t.id}} {{t.name}}</option></select></label>
 <label>추가 탐색 분류<select v-model="draft.navigation" multiple><option v-for="t in types" :key="t.id" :value="t.id">{{t.id}} {{t.name}}</option></select></label>
 <fieldset v-for="[axis,label] in axes" :key="axis"><legend>{{label}}</legend><label v-for="term in facets.filter(t=>t.axis===axis)" :key="term.id"><input v-model="draft.facets[axis]" type="checkbox" :value="term.id" />{{term.name}}</label></fieldset>
 <button :disabled="conflict">분류 저장</button><button type="button" @click="cancel">분류 변경 취소</button></fieldset></form></section></template>
