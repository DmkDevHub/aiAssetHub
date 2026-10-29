<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
const props=defineProps<{assetId:string}>();
type Link={targetId:string;kind:string};
type Candidate={id:string;name:string;relations:string[]};
type Snapshot={value:Link[];revision:number;items:(Link&{name:string;available:boolean})[]};
const labels:Record<string,string>={related:'관련',original_of:'현재가 대상의 원본',variant_of:'현재가 대상의 변형본',derived_from:'현재가 대상의 파생본'};
const incomingLabels:Record<string,string>={related:'관련',original_of:'이 에셋이 현재의 원본',variant_of:'이 에셋이 현재의 변형본',derived_from:'이 에셋이 현재의 파생본'};
const snapshot=ref<Snapshot>(),links=ref<Link[]>([]),candidates=ref<Candidate[]>([]),kind=ref('related');
const incoming=ref(false),cursor=ref<string|null>(null),busy=ref(false),conflict=ref(false),message=ref('');
let generation=0;onBeforeUnmount(()=>{generation++;});
async function load(){
 const token=++generation;snapshot.value=undefined;links.value=[];candidates.value=[];cursor.value=null;conflict.value=false;message.value='';busy.value=true;
 if(!isTauri()){busy.value=false;return;}
 try {const r=await invoke<{ok:boolean;data:Snapshot}>('get_asset_relations',{assetId:props.assetId});if(token!==generation)return;if(!r.ok)throw new Error();snapshot.value=r.data;links.value=r.data.value.map(l=>({...l}));}
 catch {if(token===generation)message.value='관계를 불러오지 못했습니다.';}
 finally {if(token===generation)busy.value=false;}
}
async function find(more=false){
 if(busy.value||!snapshot.value||!isTauri())return;
 const token=generation;busy.value=true;message.value='';
 try {const r=await invoke<{ok:boolean;data:{items:Candidate[];next_cursor:string|null}}>('asset_link_candidates',{assetId:props.assetId,kind:incoming.value?'incoming':'asset',afterId:more?cursor.value:null});if(token!==generation)return;if(!r.ok)throw new Error();candidates.value=r.data.items;cursor.value=r.data.next_cursor;}
 catch {if(token===generation)message.value='관계 대상을 불러오지 못했습니다.';}
 finally {if(token===generation)busy.value=false;}
}
function add(c:Candidate){if(links.value.length<16&&!links.value.some(l=>l.targetId===c.id&&l.kind===kind.value))links.value.push({targetId:c.id,kind:kind.value});}
async function save(){
 if(!snapshot.value||busy.value||conflict.value||!isTauri())return;
 const token=generation;busy.value=true;message.value='';
 try {const r=await invoke<{ok:boolean;data:Snapshot;error?:{code:string}}>('save_asset_relations',{assetId:props.assetId,value:links.value.map(l=>({...l})),expectedRevision:snapshot.value.revision});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;message.value='다른 변경이 저장되었습니다. 초안을 확인한 후 다시 불러오세요.';return;}if(!r.ok)throw new Error();snapshot.value=r.data;message.value='저장했습니다.';}
 catch {if(token===generation)message.value='관계를 저장하지 못했습니다. 대상·자기 연결·파생 순환을 확인하세요.';}
 finally {if(token===generation)busy.value=false;}
}
watch(()=>props.assetId,load,{immediate:true});
</script>
<template>
 <section class="asset-relations" aria-label="에셋 관계">
  <h3>에셋 관계</h3>
  <fieldset :disabled="busy||!snapshot">
   <p>현재 에셋 → 대상 에셋 방향으로 저장합니다. 관련은 양쪽에서 조회할 수 있습니다.</p>
   <ul><li v-for="(link,i) in links" :key="link.targetId+link.kind">{{ labels[link.kind] }} → {{ snapshot?.items.find(s=>s.targetId===link.targetId)?.name || link.targetId }}
    {{ snapshot?.items.find(s=>s.targetId===link.targetId)?.available===false?'사용 불가':'' }} <button type="button" @click="links.splice(i,1)">관계 해제</button></li></ul>
   <label>관계 <select v-model="kind"><option v-for="(label,id) in labels" :key="id" :value="id">{{ label }}</option></select></label>
   <label><input v-model="incoming" type="checkbox" @change="candidates=[];cursor=null" /> 다른 에셋 → 현재 에셋 관계 조회</label>
   <button type="button" @click="find()">등록 에셋 찾기</button>
   <ul class="relation-candidates"><li v-for="c in candidates" :key="c.id">{{ c.name }} · {{ c.id }}
    <span v-if="incoming">→ 현재: {{ c.relations.map(r=>incomingLabels[r]).join(', ') }}</span>
    <button v-else type="button" @click="add(c)">관계 추가</button></li></ul>
   <button v-if="cursor" type="button" @click="find(true)">다음 에셋</button>
   <button type="button" :disabled="conflict" @click="save">관계 저장</button>
  </fieldset>
  <p role="status">{{ message }}</p>
  <button v-if="!busy&&(!snapshot||conflict)" type="button" @click="load">초안을 버리고 다시 불러오기</button>
 </section>
</template>
