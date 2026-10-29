<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
type Group={id:string;name:string;description:string;parentId:string|null;revision:number};
const props=defineProps<{assetId?:string}>();
const groups=ref<Group[]>([]),cursor=ref<string|null>(null),busy=ref(false),loaded=ref(false),error=ref(''),notice=ref('');
const selected=ref<Group>(),name=ref(''),description=ref(''),confirmDelete=ref(false),conflict=ref(false);
const memberIds=ref<string[]>([]),memberRevision=ref(0);
let generation=0;onBeforeUnmount(()=>{generation++;});
function edit(g?:Group){selected.value=g;name.value=g?.name??'';description.value=g?.description??'';confirmDelete.value=false;conflict.value=false;}
async function load(more=false){
 if(busy.value||!isTauri())return;
 const token=++generation;busy.value=true;error.value='';notice.value='';
 try{
  const r=await invoke<{ok:boolean;data:{items:Group[];next_cursor:string|null}}>('group_list',{afterId:more?cursor.value:null});if(token!==generation)return;if(!r.ok||!Array.isArray(r.data?.items))throw new Error();
  let membership:{ids:string[];revision:number}|undefined;
  if(props.assetId&&!more){const m=await invoke<{ok:boolean;data:{ids:string[];revision:number}}>('group_membership',{assetId:props.assetId});if(token!==generation)return;if(!m.ok)throw new Error();membership=m.data;}
  groups.value=more?[...groups.value,...r.data.items]:r.data.items;cursor.value=r.data.next_cursor;loaded.value=true;
  if(membership){memberIds.value=membership.ids;memberRevision.value=membership.revision;conflict.value=false;}
  if(!more)edit();
 }catch{if(token===generation)error.value='그룹 정보를 불러오지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
async function save(remove=false){
 if(busy.value||!loaded.value||conflict.value||!isTauri()||(remove&&!confirmDelete.value))return;
 const token=generation;busy.value=true;error.value='';notice.value='';
 try{
  const command=remove?'group_delete':selected.value?'group_update':'group_create';
  const args=remove?{groupId:selected.value!.id,expectedRevision:selected.value!.revision}:selected.value?{groupId:selected.value.id,expectedRevision:selected.value.revision,value:{name:name.value,description:description.value}}:{value:{name:name.value,description:description.value}};
  const r=await invoke<{ok:boolean;data:Group;error?:{code:string}}>(command,args);if(token!==generation)return;
  if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;error.value='다른 변경이 저장되었습니다. 초안을 확인한 후 새로고침하세요.';return;}if(!r.ok)throw new Error();
  if(remove)groups.value=groups.value.filter(g=>g.id!==selected.value?.id);
  else groups.value=[...groups.value.filter(g=>g.id!==r.data.id),r.data];
  edit();notice.value='저장했습니다.';
 }catch{if(token===generation)error.value='그룹을 저장하지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
async function assign(){
 if(!props.assetId||busy.value||!loaded.value||conflict.value||!isTauri())return;
 const token=generation;busy.value=true;error.value='';
 try{const r=await invoke<{ok:boolean;data:{ids:string[];revision:number};error?:{code:string}}>('group_assign',{assetId:props.assetId,groupIds:[...memberIds.value],expectedRevision:memberRevision.value});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;error.value='다른 소속 변경이 저장되었습니다. 초안을 확인한 후 새로고침하세요.';return;}if(!r.ok)throw new Error();memberIds.value=r.data.ids;memberRevision.value=r.data.revision;notice.value='소속을 저장했습니다.';
 }catch{if(token===generation)error.value='그룹 소속을 저장하지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
watch(()=>props.assetId,()=>{generation++;busy.value=false;loaded.value=false;groups.value=[];memberIds.value=[];edit();if(props.assetId)void load();},{immediate:true});
</script>
<template>
 <section class="group-manager" :aria-label="assetId?'에셋 그룹 소속':'논리 그룹 관리'">
  <h3>{{ assetId?'그룹 소속':'사용자 그룹' }}</h3>
  <button type="button" :disabled="busy" @click="load()">그룹 새로고침</button>
  <p v-if="loaded&&!groups.length">등록된 그룹이 없습니다.</p>
  <fieldset :disabled="busy||!loaded">
   <ul><li v-for="g in groups" :key="g.id" :data-group-id="g.id">
    <label v-if="assetId"><input v-model="memberIds" type="checkbox" :value="g.id" />{{ g.name }}</label>
    <button v-else type="button" @click="edit(g)">{{ g.name }}</button>
   </li></ul>
   <button v-if="cursor" type="button" @click="load(true)">그룹 더 보기</button>
   <template v-if="assetId"><p>최대 32개 그룹에 소속할 수 있습니다.</p><button type="button" :disabled="conflict" @click="assign">그룹 소속 저장</button></template>
   <template v-else>
    <button type="button" @click="edit()">새 그룹</button>
    <form @submit.prevent="save()"><label>그룹 이름 <input v-model="name" maxlength="128" required /></label><label>그룹 설명 <textarea v-model="description" maxlength="512" /></label><button :disabled="conflict||!name.trim()">{{ selected?'그룹 수정':'그룹 생성' }}</button></form>
    <template v-if="selected"><p>그룹 삭제는 소속만 해제합니다.</p><label><input v-model="confirmDelete" type="checkbox" />선택한 그룹 삭제 확인</label><button type="button" :disabled="!confirmDelete||conflict" @click="save(true)">그룹 삭제</button></template>
   </template>
  </fieldset>
  <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
 </section>
</template>
