<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
const props=defineProps<{selectedIds:string[];folderId:string|null}>();
const open=ref(false),busy=ref(false),error=ref(''),mode=ref('selected'),scope=ref('folder'),model=ref('');
const preview=ref<{targetCount:number;missingCount:number;planToken:string}|null>(null);
watch([mode,scope,model,()=>props.selectedIds.join(','),()=>props.folderId],()=>{preview.value=null;});
const models=ref<{id:string;modelId:string;enabled:boolean;selected?:boolean;inspection?:{modalities?:string[]}}[]>([]);
const trigger=ref<HTMLButtonElement>(),panel=ref<HTMLElement>();let alive=true;
onBeforeUnmount(()=>{alive=false;});
async function show(){
 open.value=true;preview.value=null;error.value='';model.value='';models.value=[];busy.value=true;
 await nextTick();panel.value?.querySelector<HTMLElement>('select')?.focus();
 if(!isTauri()){busy.value=false;error.value='데스크톱 Core 연결이 필요합니다.';return;}
 try{
  let cursor:string|null=null;const rows:typeof models.value=[];const seen=new Set<string>();
  do{
   const result:{ok:boolean;data:{items:typeof models.value;next_cursor:string|null}}=await invoke('list_models',{afterId:cursor});
   if(!alive)return;if(!result.ok || !Array.isArray(result.data?.items))throw new Error();
   for(const item of result.data.items){if(typeof item.id!=='string'||seen.has(item.id))throw new Error();seen.add(item.id);rows.push(item);}
   cursor=result.data.next_cursor;if(cursor!==null && (cursor!==rows.at(-1)?.id || rows.length>10000))throw new Error();
  }while(cursor);
  models.value=rows;model.value=rows.find(m=>m.selected)?.id??'';
 }catch{if(alive)error.value='모델 목록을 불러오지 못했습니다.';}
 finally{if(alive)busy.value=false;}
}
async function review(){
 if(busy.value || !model.value)return;busy.value=true;error.value='';preview.value=null;
 try{
  const result=await invoke<{ok:boolean;data:{targetCount:number;missingCount:number;planToken:string}}>('preview_analysis',{plan:{mode:mode.value,scope:scope.value,library_id:null,folder_parts:[],selected_ids:mode.value==='selected'?props.selectedIds:[],model_id:model.value}});
  if(!result.ok || !Number.isSafeInteger(result.data?.targetCount))throw new Error();
  preview.value=result.data;
 }catch{error.value='대상을 확인하지 못했습니다. 분석 범위와 모델을 확인하세요.';}
 finally{busy.value=false;}
}
async function close(){open.value=false;await nextTick();trigger.value?.focus();}
function keys(event:KeyboardEvent){
 if(event.key==='Escape'){event.preventDefault();void close();return;}
 if(event.key!=='Tab')return;
 const controls=[...panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled),select:not(:disabled),input:not(:disabled)')??[]];
 const first=controls[0],last=controls.at(-1);
 if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
 else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
}
</script>
<template>
 <button ref="trigger" type="button" class="analysis-open" @click="show">AI 분석</button>
 <div v-if="open" class="analysis-overlay">
  <section ref="panel" role="dialog" aria-modal="true" aria-labelledby="analysis-title" class="analysis-dialog" @keydown="keys">
   <h2 id="analysis-title">수동 AI 분석</h2>
   <p>대상·모델·전송 범위·비용을 확인한 뒤 분석 시작을 눌러야 실행됩니다. 이 창을 여는 것만으로 AI를 호출하지 않습니다.</p>
   <label>대상 모드 <select v-model="mode" :disabled="busy"><option value="all">전체</option><option value="unanalyzed">미분석</option><option value="completed">완료 재분석</option><option value="failed">실패 재시도</option><option value="selected">선택 {{ props.selectedIds.length }}개</option></select></label>
   <label>분석 범위 <select v-model="scope" :disabled="busy"><option value="folder">현재 폴더 (하위 포함)</option><option value="library">현재 라이브러리</option><option value="all">전체 라이브러리</option></select></label>
   <label>모델 <select v-model="model" :disabled="busy"><option value="">모델을 선택하세요</option><option v-for="item in models" :key="item.id" :value="item.id" :disabled="!item.enabled || !item.inspection?.modalities?.includes('image')">{{ item.modelId }}{{ item.enabled?'':' (비활성)' }}</option></select></label>
   <p v-if="error" role="alert">{{ error }}</p>
   <button type="button" :disabled="busy || !model" @click="review">대상 확인</button>
   <p v-if="preview" role="status">대상 {{ preview.targetCount }}개 · 인덱스상 원본 누락 {{ preview.missingCount }}개</p>
   <button type="button" disabled>분석 시작 (대상 확인 필요)</button>
   <button type="button" @click="close">닫기</button>
  </section>
 </div>
</template>
