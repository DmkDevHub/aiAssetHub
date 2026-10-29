<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {collectionsChanged} from '../stores/collections';
type Package={id:string;name:string;description:string;unit:string;version:string;purchase:{amount:string|null;currency:string;date:string};defaults:Record<string,string|null>;revision:number};
const props=defineProps<{assetId?:string}>();
const packages=ref<Package[]>([]),cursor=ref<string|null>(null),busy=ref(false),loaded=ref(false),conflict=ref(false),message=ref('');
const selected=ref<Package>(),name=ref(''),description=ref(''),unit=ref('distribution'),version=ref(''),amount=ref(''),currency=ref(''),purchaseDate=ref(''),confirmed=ref(false);
const memberIds=ref<string[]>([]),memberRevision=ref(0),snapshots=ref<{id:string;name:string;purchaseSnapshot:unknown;recordedAt:string}[]>([]);
let generation=0;onBeforeUnmount(()=>{generation++;});
function edit(p?:Package){selected.value=p;name.value=p?.name??'';description.value=p?.description??'';unit.value=p?.unit??'distribution';version.value=p?.version??'';amount.value=p?.purchase.amount??'';currency.value=p?.purchase.currency??'';purchaseDate.value=p?.purchase.date??'';confirmed.value=false;conflict.value=false;}
async function load(more=false){
 if(busy.value||!isTauri())return;const token=++generation;busy.value=true;message.value='';
 try{const r=await invoke<{ok:boolean;data:{items:Package[];next_cursor:string|null}}>('package_list',{afterId:more?cursor.value:null});if(token!==generation)return;if(!r.ok||!Array.isArray(r.data?.items))throw new Error();
 let membership:{ids:string[];revision:number;items:typeof snapshots.value}|undefined;
 if(props.assetId&&!more){const m=await invoke<{ok:boolean;data:NonNullable<typeof membership>}>('package_membership',{assetId:props.assetId});if(token!==generation)return;if(!m.ok)throw new Error();membership=m.data;}
 packages.value=more?[...packages.value,...r.data.items]:r.data.items;cursor.value=r.data.next_cursor;loaded.value=true;
 if(membership){memberIds.value=membership.ids;memberRevision.value=membership.revision;snapshots.value=membership.items;}
 if(!more)edit();
 }catch{if(token===generation)message.value='패키지 정보를 불러오지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
async function save(remove=false){
 if(busy.value||!loaded.value||conflict.value||!isTauri()||(remove&&!confirmed.value))return;const token=generation;busy.value=true;message.value='';
 try{const value={name:name.value,description:description.value,unit:unit.value,version:version.value,purchase:{amount:amount.value===''?null:amount.value,currency:currency.value,date:purchaseDate.value}};
 const args=remove?{packageId:selected.value!.id,expectedRevision:selected.value!.revision}:selected.value?{packageId:selected.value.id,expectedRevision:selected.value.revision,value}:{value};
 const r=await invoke<{ok:boolean;data:Package;error?:{code:string}}>(remove?'package_delete':selected.value?'package_update':'package_create',args);if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;message.value='다른 패키지 변경이 저장되었습니다. 초안을 확인하고 새로고침하세요.';return;}if(!r.ok)throw new Error();
 if(remove)packages.value=packages.value.filter(p=>p.id!==selected.value?.id);else packages.value=[...packages.value.filter(p=>p.id!==r.data.id),r.data];
 edit();message.value='패키지를 저장했습니다.';collectionsChanged();
 }catch{if(token===generation)message.value='저장하지 못했습니다. 이름·날짜·금액/통화를 확인하세요.';}
 finally{if(token===generation)busy.value=false;}
}
async function assign(){
 if(!props.assetId||busy.value||!loaded.value||conflict.value||!isTauri())return;const token=generation;busy.value=true;message.value='';
 try{const r=await invoke<{ok:boolean;data:{ids:string[];revision:number;items:typeof snapshots.value};error?:{code:string}}>('package_assign',{assetId:props.assetId,packageIds:[...memberIds.value],expectedRevision:memberRevision.value});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;message.value='다른 패키지 소속 변경이 저장되었습니다. 새로고침하세요.';return;}if(!r.ok)throw new Error();memberIds.value=r.data.ids;memberRevision.value=r.data.revision;snapshots.value=r.data.items;message.value='패키지 소속을 저장했습니다.';collectionsChanged();
 }catch{if(token===generation)message.value='패키지 소속을 저장하지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
watch(()=>props.assetId,()=>{generation++;busy.value=false;loaded.value=false;packages.value=[];memberIds.value=[];snapshots.value=[];edit();if(props.assetId)void load();},{immediate:true});
</script>
<template>
 <section class="package-manager" :aria-label="assetId?'에셋 패키지 소속':'배포·구매 패키지 관리'">
  <h3>{{ assetId?'패키지 소속':'패키지 관리' }}</h3><p>패키지는 배포·구매 단위입니다.</p>
  <button type="button" :disabled="busy" @click="load()">패키지 새로고침</button>
  <p v-if="loaded&&!packages.length">등록된 패키지가 없습니다.</p>
  <fieldset :disabled="busy||!loaded">
   <ul><li v-for="p in packages" :key="p.id"><label v-if="assetId"><input v-model="memberIds" type="checkbox" :value="p.id" />{{ p.name }}</label><button v-else type="button" @click="edit(p)">{{ p.name }}</button> · {{ p.unit==='purchase'?'구매 단위':'배포 단위' }} · {{ p.id }}</li></ul>
   <button v-if="cursor" type="button" @click="load(true)">패키지 더 보기</button>
   <template v-if="assetId"><p>최대 16개 패키지에 소속할 수 있습니다.</p><button type="button" :disabled="conflict" @click="assign">패키지 소속 저장</button><details v-for="s in snapshots" :key="s.id"><summary>{{ s.name }} 최초 소속 당시 기록</summary><p>{{ s.recordedAt }}</p><pre>{{ JSON.stringify(s.purchaseSnapshot,null,2) }}</pre></details></template>
   <template v-else>
    <button type="button" @click="edit()">새 패키지</button>
    <form @submit.prevent="save()"><label>패키지명 <input v-model="name" maxlength="128" required /></label><label>설명 <textarea v-model="description" maxlength="512" /></label><label>관리 단위 <select v-model="unit"><option value="distribution">배포 단위</option><option value="purchase">구매 단위</option></select></label><label>패키지 버전 <input v-model="version" maxlength="64" /></label><label>기록 금액 <input v-model="amount" maxlength="17" placeholder="미확인: 비움 / 무료: 0" /></label><label>통화 <input v-model="currency" maxlength="3" placeholder="KRW" /></label><label>구매일 <input v-model="purchaseDate" type="date" /></label><button :disabled="conflict||!name.trim()">{{ selected?'패키지 수정':'패키지 생성' }}</button></form>
    <template v-if="selected"><label><input v-model="confirmed" type="checkbox" />선택한 패키지 삭제 확인</label><button type="button" :disabled="!confirmed||conflict" @click="save(true)">패키지 삭제</button></template>
   </template>
  </fieldset><p role="status">{{ message }}</p>
 </section>
</template>
<style scoped>pre {white-space:pre-wrap;overflow-wrap:anywhere;}</style>
