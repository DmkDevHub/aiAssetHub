<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue';
import {collectionsChanged} from '../stores/collections';
import { invoke, isTauri } from '@tauri-apps/api/core';
const props = defineProps<{assetId:string}>();
type Management = {favorite:boolean;rating:number|null;status:string;notes:string;assetVersion:string;createdDate:string;modifiedDate:string};
const value = ref<Management>({favorite:false,rating:null,status:'unreviewed',notes:'',assetVersion:'',createdDate:'',modifiedDate:''});
const busy=ref(false), loaded=ref(false), conflict=ref(false), message=ref(''), revision=ref(0);
let generation=0;
onBeforeUnmount(()=>{generation++;});
async function load() {
  const token=++generation; loaded.value=false; conflict.value=false; message.value=''; busy.value=true;
  value.value={favorite:false,rating:null,status:'unreviewed',notes:'',assetVersion:'',createdDate:'',modifiedDate:''};revision.value=0;
  if(!isTauri()){busy.value=false;return;}
  try {
    const result=await invoke<{ok:boolean;data:{value:Management;revision:number}}>('get_asset_management',{assetId:props.assetId});
    if(token!==generation)return;
    if(!result.ok)throw new Error();
    value.value=result.data.value; revision.value=result.data.revision; loaded.value=true;
  } catch {if(token===generation)message.value='관리 정보를 불러오지 못했습니다.';}
  finally {if(token===generation)busy.value=false;}
}
async function save() {
  if(!loaded.value||busy.value||conflict.value||!isTauri())return;
  const token=generation;busy.value=true;message.value='';
  try {
    const result=await invoke<{ok:boolean;data:{value:Management;revision:number};error?:{code:string}}>('save_asset_management',{assetId:props.assetId,value:{...value.value},expectedRevision:revision.value});
    if(token!==generation)return;
    if(result.error?.code==='METADATA_CONFLICT'){conflict.value=true;message.value='다른 변경이 저장되었습니다. 초안을 확인한 후 다시 불러오세요.';return;}
    if(!result.ok)throw new Error();
    value.value=result.data.value;revision.value=result.data.revision;message.value='저장했습니다.';collectionsChanged();
  } catch {if(token===generation)message.value='저장하지 못했습니다. 입력값을 확인하세요.';}
  finally {if(token===generation)busy.value=false;}
}
watch(()=>props.assetId,load,{immediate:true});
</script>
<template>
  <section class="asset-management" aria-label="에셋 관리 정보">
    <h3>관리 정보</h3>
    <form @submit.prevent="save">
      <fieldset :disabled="busy||!loaded">
        <label><input v-model="value.favorite" type="checkbox" /> 즐겨찾기</label>
        <label>평점 <select v-model="value.rating"><option :value="null">미평가</option><option v-for="n in 5" :key="n" :value="n">{{ n }}</option></select></label>
        <label>상태 <select v-model="value.status"><option value="unreviewed">미검토</option><option value="reviewing">검토 중</option><option value="approved">사용 승인</option><option value="archived">보관</option></select></label>
        <label>메모 <textarea v-model="value.notes" maxlength="1024" /></label>
        <label>에셋 버전 <input v-model="value.assetVersion" maxlength="64" /></label>
        <label>에셋 생성일 <input v-model="value.createdDate" type="date" /></label>
        <label>에셋 수정일 <input v-model="value.modifiedDate" type="date" /></label>
        <p>날짜는 사용자가 기록하는 에셋 정보입니다. 파일의 생성·수정 시각은 바뀌지 않습니다.</p>
        <button :disabled="conflict">관리 정보 저장</button>
      </fieldset>
    </form>
    <p role="status">{{ message }}</p>
    <button v-if="!busy&&(!loaded||conflict)" type="button" @click="load">초안을 버리고 다시 불러오기</button>
  </section>
</template>
