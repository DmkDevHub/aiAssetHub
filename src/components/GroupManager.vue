<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {collectionUi,selectGroup,collectionsChanged} from '../stores/collections';
import {invoke,isTauri} from '@tauri-apps/api/core';
type Group={id:string;name:string;description:string;parentId:string|null;revision:number};
const props=defineProps<{assetId?:string}>();
const groups=ref<Group[]>([]),cursor=ref<string|null>(null),busy=ref(false),loaded=ref(false),error=ref(''),notice=ref('');
const selected=ref<Group>(),name=ref(''),description=ref(''),confirmDelete=ref(false),conflict=ref(false);
const memberIds=ref<string[]>([]),memberRevision=ref(0);
const parentId=ref<string|null>(null),dragged=ref<Group>(),pendingMove=ref<{group:Group;parentId:string|null}>();
let generation=0;onBeforeUnmount(()=>{generation++;});
function edit(g?:Group){selected.value=g;name.value=g?.name??'';description.value=g?.description??'';parentId.value=g?.parentId??null;confirmDelete.value=false;conflict.value=false;}
function propose(group?:Group,parent:string|null=null){if(!group||busy.value||props.assetId)return;pendingMove.value={group,parentId:parent};error.value='';}
function drop(parent:string|null){propose(dragged.value,parent);dragged.value=undefined;}
async function move(){
 if(!pendingMove.value||busy.value||conflict.value||!isTauri())return;
 const token=generation;busy.value=true;error.value='';const proposal=pendingMove.value;
 try{const r=await invoke<{ok:boolean;data:Group;error?:{code:string}}>('group_move',{groupId:proposal.group.id,parentId:proposal.parentId,expectedRevision:proposal.group.revision});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;error.value='그룹이 변경되었습니다. 새로고침하세요.';return;}if(!r.ok)throw new Error();
 groups.value=groups.value.map(g=>g.id===r.data.id?r.data:g);if(selected.value?.id===r.data.id)edit(r.data);pendingMove.value=undefined;notice.value='그룹을 이동했습니다.';
 }catch{if(token===generation)error.value='이동하지 못했습니다. 자기 연결·순환·대상을 확인하세요.';}
 finally{if(token===generation)busy.value=false;}
}
async function load(more=false){
 if(busy.value||!isTauri())return;
 const token=++generation;busy.value=true;error.value='';notice.value='';
 try{
  const r=await invoke<{ok:boolean;data:{items:Group[];next_cursor:string|null}}>('group_list',{afterId:more?cursor.value:null});if(token!==generation)return;if(!r.ok||!Array.isArray(r.data?.items))throw new Error();
  let membership:{ids:string[];revision:number}|undefined;
  if(props.assetId&&!more){const m=await invoke<{ok:boolean;data:{ids:string[];revision:number}}>('group_membership',{assetId:props.assetId});if(token!==generation)return;if(!m.ok)throw new Error();membership=m.data;}
  groups.value=more?[...groups.value,...r.data.items]:r.data.items;cursor.value=r.data.next_cursor;loaded.value=true;
  if(membership){memberIds.value=membership.ids;memberRevision.value=membership.revision;conflict.value=false;}
  if(!more){edit();pendingMove.value=undefined;}
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
  if(remove){const removed=selected.value?.id;groups.value=groups.value.filter(g=>g.id!==removed).map(g=>g.parentId===removed?{...g,parentId:null,revision:g.revision+1}:g);}
  else groups.value=[...groups.value.filter(g=>g.id!==r.data.id),r.data];
  edit();notice.value='저장했습니다.';collectionsChanged();if(remove)selectGroup(null);
 }catch{if(token===generation)error.value='그룹을 저장하지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
async function assign(){
 if(!props.assetId||busy.value||!loaded.value||conflict.value||!isTauri())return;
 const token=generation;busy.value=true;error.value='';
 try{const r=await invoke<{ok:boolean;data:{ids:string[];revision:number};error?:{code:string}}>('group_assign',{assetId:props.assetId,groupIds:[...memberIds.value],expectedRevision:memberRevision.value});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;error.value='다른 소속 변경이 저장되었습니다. 초안을 확인한 후 새로고침하세요.';return;}if(!r.ok)throw new Error();memberIds.value=r.data.ids;memberRevision.value=r.data.revision;notice.value='소속을 저장했습니다.';collectionsChanged();
 }catch{if(token===generation)error.value='그룹 소속을 저장하지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
watch(()=>props.assetId,()=>{generation++;busy.value=false;loaded.value=false;groups.value=[];memberIds.value=[];pendingMove.value=undefined;dragged.value=undefined;edit();if(props.assetId)void load();},{immediate:true});
</script>
<template>
 <section class="group-manager" :aria-label="assetId?'에셋 그룹 소속':'논리 그룹 관리'" @keydown.esc="pendingMove=undefined;dragged=undefined">
  <button v-if="!assetId" type="button" @click="selectGroup(null)">전체 그룹 필터 해제</button>
  <h3>{{ assetId?'그룹 소속':'사용자 그룹' }}</h3>
  <button type="button" :disabled="busy" @click="load()">그룹 새로고침</button>
  <p v-if="loaded&&!groups.length">등록된 그룹이 없습니다.</p>
  <fieldset :disabled="busy||!loaded">
   <button v-if="!assetId" class="group-root-drop" type="button" @dragover.prevent @drop.prevent.stop="drop(null)">최상위 그룹 (여기로 놓아 이동 준비)</button>
   <ul><li v-for="g in groups" :key="g.id" :data-group-id="g.id" :draggable="!assetId&&!busy" @dragstart="dragged=g" @dragend="dragged=undefined" @dragover.prevent @drop.prevent.stop="drop(g.id)">
    <label v-if="assetId"><input v-model="memberIds" type="checkbox" :value="g.id" />{{ g.name }}</label>
    <template v-else><button type="button" @click="edit(g)">{{ g.name }}</button><button type="button" :aria-pressed="collectionUi.groupId===g.id" @click="selectGroup(g.id)">{{ g.name }} 에셋 보기</button></template>
    <small>상위: {{ g.parentId?(groups.find(p=>p.id===g.parentId)?.name||g.parentId):'최상위' }}</small>
   </li></ul>
   <button v-if="cursor" type="button" @click="load(true)">그룹 더 보기</button>
   <template v-if="assetId"><p>최대 32개 그룹에 소속할 수 있습니다.</p><button type="button" :disabled="conflict" @click="assign">그룹 소속 저장</button></template>
   <template v-else>
    <button type="button" @click="edit()">새 그룹</button>
    <form @submit.prevent="save()"><label>그룹 이름 <input v-model="name" maxlength="128" required /></label><label>그룹 설명 <textarea v-model="description" maxlength="512" /></label><button :disabled="conflict||!name.trim()">{{ selected?'그룹 수정':'그룹 생성' }}</button></form>
    <template v-if="selected">
     <label>상위 그룹 <select v-model="parentId"><option :value="null">최상위</option><option v-if="parentId&&!groups.some(g=>g.id===parentId)" :value="parentId">{{ parentId }}</option><option v-for="g in groups.filter(g=>g.id!==selected?.id)" :key="g.id" :value="g.id">{{ g.name }}</option></select></label>
     <button type="button" @click="propose(selected,parentId)">그룹 이동 준비</button>
     <p>그룹 삭제는 소속을 해제하고 하위 그룹을 최상위로 옮깁니다.</p><label><input v-model="confirmDelete" type="checkbox" />선택한 그룹 삭제 확인</label><button type="button" :disabled="!confirmDelete||conflict" @click="save(true)">그룹 삭제</button>
    </template>
    <div v-if="pendingMove" class="group-move-review" role="group" aria-label="그룹 이동 검토"><p>{{ pendingMove.group.name }} → {{ pendingMove.parentId?(groups.find(g=>g.id===pendingMove?.parentId)?.name||pendingMove.parentId):'최상위' }}</p><button type="button" :disabled="conflict" @click="move">그룹 이동 적용</button><button type="button" @click="pendingMove=undefined">그룹 이동 취소</button></div>
   </template>
  </fieldset>
  <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
 </section>
</template>
