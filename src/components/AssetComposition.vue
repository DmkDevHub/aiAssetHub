<script setup lang="ts">
import {ref, watch, onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
const props=defineProps<{assetId:string}>();
type FileLink={fileId:string;role:string};
type Candidate={id:string;name:string;fileId?:string;available:boolean};
type Snapshot={value:{files:FileLink[];components:string[]};revision:number;availability:string;files:(FileLink&{name:string;available:boolean;owned:boolean})[];components:{id:string;kind:string;stale:boolean}[]};
const snapshot=ref<Snapshot>(),files=ref<FileLink[]>([]),components=ref<string[]>([]),candidates=ref<Candidate[]>([]);
const kind=ref('file'),role=ref('dependency'),cursor=ref<string|null>(null),busy=ref(false),conflict=ref(false),message=ref('');
let generation=0;
onBeforeUnmount(()=>{generation++;});
async function load() {
 const token=++generation;snapshot.value=undefined;files.value=[];components.value=[];candidates.value=[];cursor.value=null;conflict.value=false;message.value='';busy.value=true;
 if(!isTauri()){busy.value=false;return;}
 try {const r=await invoke<{ok:boolean;data:Snapshot}>('get_asset_composition',{assetId:props.assetId});if(token!==generation)return;if(!r.ok)throw new Error();snapshot.value=r.data;files.value=r.data.value.files.map(f=>({...f}));components.value=[...r.data.value.components];}
 catch {if(token===generation)message.value='파일 구성을 불러오지 못했습니다.';}
 finally {if(token===generation)busy.value=false;}
}
async function find(more=false) {
 if(busy.value||!snapshot.value||!isTauri())return;
 const token=generation;busy.value=true;message.value='';
 try {const r=await invoke<{ok:boolean;data:{items:Candidate[];next_cursor:string|null}}>('asset_link_candidates',{assetId:props.assetId,kind:kind.value,afterId:more?cursor.value:null});if(token!==generation)return;if(!r.ok)throw new Error();candidates.value=r.data.items;cursor.value=r.data.next_cursor;}
 catch {if(token===generation)message.value='등록된 참조를 불러오지 못했습니다.';}
 finally {if(token===generation)busy.value=false;}
}
function add(c:Candidate) {
 if(kind.value==='file') {if(!files.value.some(f=>f.fileId===c.id&&f.role===role.value)&&files.value.length<16)files.value.push({fileId:c.id,role:role.value});}
 else if(!components.value.includes(c.id)&&components.value.length<16) {
   if(!files.value.some(f=>f.fileId===c.fileId)){message.value='구성 요소의 파일을 먼저 연결하세요.';return;}
   components.value.push(c.id);
 }
}
function owned(link:FileLink){return link.role==='source'&&snapshot.value?.files.some(f=>f.fileId===link.fileId&&f.owned);}
async function save(){
 if(!snapshot.value||busy.value||conflict.value||!isTauri())return;
 const token=generation;busy.value=true;message.value='';
 try {const r=await invoke<{ok:boolean;data:Snapshot;error?:{code:string}}>('save_asset_composition',{assetId:props.assetId,value:{files:files.value.map(f=>({...f})),components:[...components.value]},expectedRevision:snapshot.value.revision});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;message.value='다른 변경이 저장되었습니다. 초안을 확인한 후 다시 불러오세요.';return;}if(!r.ok)throw new Error();snapshot.value=r.data;message.value='저장했습니다.';}
 catch {if(token===generation)message.value='파일 구성을 저장하지 못했습니다. 등록 상태와 참조를 확인하세요.';}
 finally {if(token===generation)busy.value=false;}
}
watch(()=>props.assetId,load,{immediate:true});
</script>
<template>
 <section class="asset-composition" aria-label="파일 구성">
  <h3>파일 구성</h3>
  <p>등록된 파일과 관측된 구성 요소를 명시적으로 연결합니다. 파일 가용성은 마지막 스캔 기준입니다.</p>
  <p v-if="snapshot">가용성: {{ {available:'전체 가용',partial:'부분 가용',missing:'사용 불가'}[snapshot.availability] }}</p>
  <fieldset :disabled="busy||!snapshot">
   <ul><li v-for="(f,i) in files" :key="f.fileId+f.role">{{ snapshot?.files.find(s=>s.fileId===f.fileId)?.name || f.fileId }} · {{ f.role }} · {{ snapshot?.files.find(s=>s.fileId===f.fileId)?.available===false?'누락/사용 불가':'' }}
    <button type="button" :disabled="owned(f)" @click="files.splice(i,1)">연결 해제</button></li></ul>
   <ul><li v-for="(id,i) in components" :key="id">{{ id }} {{ snapshot?.components.find(c=>c.id===id)?.stale?'오래된 참조':'' }} <button type="button" @click="components.splice(i,1)">구성 요소 참조 해제</button></li></ul>
   <label>참조 종류 <select v-model="kind" @change="candidates=[];cursor=null"><option value="file">파일</option><option value="component">관측된 내부 구성 요소</option></select></label>
   <label>파일 역할 <select v-model="role"><option value="source">원본 구성</option><option value="dependency">의존 파일</option><option value="preview">미리보기</option><option value="evidence">근거</option></select></label>
   <button type="button" @click="find()">등록된 참조 찾기</button>
   <ul class="reference-candidates"><li v-for="c in candidates" :key="c.id">{{ c.name }} · {{ c.id }} <button type="button" :disabled="!c.available" @click="add(c)">참조 추가</button></li></ul>
   <button v-if="cursor" type="button" @click="find(true)">다음 참조</button>
   <button type="button" :disabled="conflict" @click="save">파일 구성 저장</button>
  </fieldset>
  <p role="status">{{ message }}</p>
  <button v-if="!busy&&(!snapshot||conflict)" type="button" @click="load">초안을 버리고 다시 불러오기</button>
 <button type="button" :disabled="busy" @click="load()">변경 취소 · 저장값 다시 조회</button></section>
</template>
