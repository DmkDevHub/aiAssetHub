<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {collectionsChanged} from '../stores/collections';
const props=defineProps<{packageId:string;revision:number;defaults:Record<string,string|null>}>();
const emit=defineEmits<{saved:[value:{id:string;revision:number;defaults:Record<string,string|null>}]}>();
const engine=ref(''),sourceUrl=ref(''),licenseLabel=ref(''),busy=ref(false),conflict=ref(false),message=ref('');
let generation=0;onBeforeUnmount(()=>{generation++;});
watch(()=>[props.packageId,props.revision],()=>{generation++;engine.value=props.defaults.engine??'';sourceUrl.value=props.defaults.sourceUrl??'';licenseLabel.value=props.defaults.licenseLabel??'';busy.value=false;conflict.value=false;message.value='';},{immediate:true});
async function save(){
 if(busy.value||conflict.value||!isTauri())return;const token=generation;busy.value=true;message.value='';
 try{const r=await invoke<{ok:boolean;data:{id:string;revision:number;defaults:Record<string,string|null>};error?:{code:string}}>('package_defaults',{packageId:props.packageId,expectedRevision:props.revision,value:{engine:engine.value||null,sourceUrl:sourceUrl.value||null,licenseLabel:licenseLabel.value||null}});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;message.value='패키지가 변경되었습니다. 초안을 확인하고 다시 불러오세요.';return;}if(!r.ok)throw new Error();emit('saved',r.data);collectionsChanged();message.value='공유 기본값을 저장했습니다.';
 }catch{if(token===generation)message.value='공유 기본값을 저장하지 못했습니다. HTTPS 출처와 입력값을 확인하세요.';}
 finally{if(token===generation)busy.value=false;}
}
</script>
<template>
 <form class="package-defaults" aria-label="패키지 공유 기본값" @submit.prevent="save">
  <h4>공유 기본값</h4><p>선언된 메타데이터입니다. 호환성·이용 권한의 검증 결과는 별도로 관리합니다.</p>
  <fieldset :disabled="busy"><label>엔진 <input v-model="engine" maxlength="128" /></label><label>출처 URL <input v-model="sourceUrl" maxlength="512" /></label><label>선언 라이선스명 <input v-model="licenseLabel" maxlength="256" /></label><button :disabled="conflict">공유 기본값 저장</button></fieldset><p role="status">{{ message }}</p>
 </form>
</template>
