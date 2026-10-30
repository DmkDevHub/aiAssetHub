<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {isTauri} from '@tauri-apps/api/core';
import {collectionUi} from '../stores/collections';
import {navigation,navigateMode,selectCatalog,type NavigationMode} from '../stores/navigation';
import {catalogOptions,type CatalogOption} from '../services/metadata';
const modes:{id:NavigationMode;name:string}[]=[{id:'folders',name:'폴더'},{id:'groups',name:'그룹'},{id:'packages',name:'패키지'},{id:'types',name:'분류'}];
const items=ref<CatalogOption[]>([]),busy=ref(false),error=ref('');let epoch=0;onBeforeUnmount(()=>epoch++);
async function load(){const token=++epoch;items.value=[];error.value='';busy.value=false;if(navigation.mode==='folders'||!isTauri())return;busy.value=true;
 try{const result=await catalogOptions(navigation.mode);if(token===epoch)items.value=result;}
 catch{if(token===epoch)error.value='탐색 목록을 불러오지 못했습니다. 선택은 유지됩니다.';}finally{if(token===epoch)busy.value=false;}}
watch([()=>navigation.mode,()=>collectionUi.revision],()=>{void load();},{immediate:true});
</script>
<template><section aria-label="탐색 영역">
 <div role="group" aria-label="탐색 종류"><button v-for="mode in modes" :key="mode.id" type="button" :aria-pressed="navigation.mode===mode.id" @click="navigateMode(mode.id)">{{mode.name}}</button></div>
 <template v-if="navigation.mode!=='folders'"><button type="button" :disabled="busy" @click="load">탐색 새로고침</button><button type="button" @click="selectCatalog(null)">현재 탐색 전체</button>
 <p v-if="error" role="alert">{{error}}</p><p v-else-if="busy" role="status">목록 조회 중…</p>
 <ul role="tree" aria-label="논리 탐색"><li v-for="item in items" :key="item.id" role="treeitem" tabindex="0" :aria-selected="navigation.selected[navigation.mode]===item.id" @keydown.enter="selectCatalog(item.id)"><button type="button" @click="selectCatalog(item.id)">{{item.parentId?'↳ ':''}}{{item.name}}</button></li></ul>
 <p v-if="!busy&&!error&&!items.length">표시할 항목이 없습니다.</p></template>
</section></template>
