<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {collectionsChanged} from '../stores/collections';
const props=defineProps<{assetIds:string[]}>();
type Plan={assetIds:string[];add:string[];remove:string[];revisions:number[];groupVersions:{id:string;revision:number}[]};
type Target={assetId:string;before:string[];after:string[];revision:number};
const groups=ref<{id:string;name:string}[]>([]),groupCursor=ref<string|null>(null),groupId=ref(''),action=ref('add');
const plan=ref<Plan>(),targets=ref<Target[]>([]),cursor=ref<string|null>(null),busy=ref(false),message=ref('');
let generation=0;onBeforeUnmount(()=>{generation++;});
watch([()=>props.assetIds.join(','),groupId,action],()=>{generation++;plan.value=undefined;targets.value=[];cursor.value=null;busy.value=false;message.value='';});
async function loadGroups(more=false){
 if(busy.value||!isTauri())return;const token=generation;busy.value=true;
 try{const r=await invoke<{ok:boolean;data:{items:{id:string;name:string}[];next_cursor:string|null}}>('group_list',{afterId:more?groupCursor.value:null});if(token!==generation)return;if(!r.ok)throw new Error();groups.value=more?[...groups.value,...r.data.items]:r.data.items;groupCursor.value=r.data.next_cursor;}
 catch{if(token===generation)message.value='그룹 목록을 불러오지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
async function preview(more=false){
 if(busy.value||!groupId.value||!isTauri()||props.assetIds.length>100)return;const token=generation;busy.value=true;message.value='';
 try{const r=await invoke<{ok:boolean;data:{plan:Plan;items:Target[];next_cursor:string|null}}>('group_batch_preview',{assetIds:[...props.assetIds],add:action.value==='add'?[groupId.value]:[],remove:action.value==='remove'?[groupId.value]:[],afterId:more?cursor.value:null});if(token!==generation)return;if(!r.ok)throw new Error();
 if(more&&JSON.stringify(plan.value)!==JSON.stringify(r.data.plan)){plan.value=undefined;targets.value=[];throw new Error();}plan.value=r.data.plan;targets.value=more?[...targets.value,...r.data.items]:r.data.items;cursor.value=r.data.next_cursor;
 }catch{if(token===generation){plan.value=undefined;message.value='변경 검토에 실패했습니다. 대상과 소속을 다시 확인하세요.';}}
 finally{if(token===generation)busy.value=false;}
}
async function apply(){
 if(busy.value||!plan.value||!isTauri())return;const token=generation;busy.value=true;message.value='';
 try{const r=await invoke<{ok:boolean;data:{updated:number};error?:{code:string}}>('group_batch_apply',{plan:plan.value,confirmed:true});if(token!==generation)return;if(!r.ok)throw new Error();message.value=`${r.data.updated}개 에셋의 소속을 저장했습니다.`;plan.value=undefined;collectionsChanged();}
 catch{if(token===generation){plan.value=undefined;message.value='저장하지 못했습니다. 소속 변경 충돌 여부를 다시 검토하세요.';}}
 finally{if(token===generation)busy.value=false;}
}
</script>
<template>
 <section class="bulk-groups" aria-label="선택 에셋 그룹 일괄 편집">
  <button type="button" :disabled="busy" @click="loadGroups()">일괄 그룹 목록 불러오기</button>
  <button v-if="groupCursor" type="button" :disabled="busy" @click="loadGroups(true)">일괄 그룹 더 보기</button>
  <label>일괄 그룹 <select v-model="groupId" :disabled="busy"><option value="">그룹 선택</option><option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option></select></label>
  <label>소속 동작 <select v-model="action" :disabled="busy"><option value="add">추가</option><option value="remove">해제</option></select></label>
  <button type="button" :disabled="busy||!groupId||assetIds.length>100" @click="preview()">{{ assetIds.length }}개 소속 변경 검토</button>
  <p v-if="assetIds.length>100">한 번에 최대 100개를 선택하세요.</p>
  <template v-if="plan"><ul><li v-for="t in targets" :key="t.assetId">{{ t.assetId }} · 이전 {{ t.before.join(', ')||'없음' }} → 이후 {{ t.after.join(', ')||'없음' }} · 버전 {{ t.revision }}</li></ul><button v-if="cursor" type="button" :disabled="busy" @click="preview(true)">다음 변경 검토</button><button type="button" :disabled="busy" @click="apply">검토한 소속 변경 적용</button><button type="button" :disabled="busy" @click="plan=undefined;targets=[]">소속 변경 취소</button></template>
  <p role="status">{{ message }}</p>
 </section>
</template>
