<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {collectionUi} from '../stores/collections';
type Field={value:string|null;source:string;status:string;packageIds:string[]};
type Snapshot={fields:Record<string,Field>;overrides:Record<string,string|null>;revision:number;packageVersions:{id:string;revision:number}[]};
const props=defineProps<{assetId:string}>();
const labels:Record<string,string>={engine:'엔진',sourceUrl:'출처 URL',licenseLabel:'선언 라이선스명'};
const modes=ref<Record<string,string>>({}),values=ref<Record<string,string>>({}),snapshot=ref<Snapshot>(),busy=ref(false),dirty=ref(false),conflict=ref(false),message=ref('');
let generation=0;onBeforeUnmount(()=>{generation++;});
async function load(){
 const token=++generation;busy.value=true;message.value='';snapshot.value=undefined;modes.value={};values.value={};dirty.value=false;conflict.value=false;
 if(!isTauri()){busy.value=false;return;}
 try{const r=await invoke<{ok:boolean;data:Snapshot}>('package_effective',{assetId:props.assetId});if(token!==generation)return;if(!r.ok||!r.data?.fields)throw new Error();snapshot.value=r.data;
 for(const key of Object.keys(labels)){modes.value[key]=key in r.data.overrides?(r.data.overrides[key]===null?'clear':'set'):'inherit';values.value[key]=r.data.overrides[key]??'';}
 }catch{if(token===generation)message.value='상속 메타데이터를 불러오지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
async function save(){
 if(!snapshot.value||busy.value||conflict.value||!isTauri())return;const token=generation;busy.value=true;message.value='';
 const value:Record<string,string|null>={};for(const key of Object.keys(labels)){if(modes.value[key]==='clear')value[key]=null;else if(modes.value[key]==='set')value[key]=values.value[key]??'';}
 try{const r=await invoke<{ok:boolean;data:Snapshot;error?:{code:string}}>('package_override',{assetId:props.assetId,value,expectedRevision:snapshot.value.revision,expectedPackages:snapshot.value.packageVersions});if(token!==generation)return;
 if(r.error?.code==='METADATA_CONFLICT'){conflict.value=true;message.value='공유 정보 또는 개별 예외가 변경되었습니다. 초안을 확인한 후 다시 불러오세요.';return;}if(!r.ok)throw new Error();snapshot.value=r.data;for(const key of Object.keys(labels)){modes.value[key]=key in r.data.overrides?(r.data.overrides[key]===null?'clear':'set'):'inherit';values.value[key]=r.data.overrides[key]??'';}dirty.value=false;message.value='개별 예외를 저장했습니다.';
 }catch{if(token===generation)message.value='개별 예외를 저장하지 못했습니다.';}
 finally{if(token===generation)busy.value=false;}
}
watch(()=>props.assetId,load,{immediate:true});
watch(()=>collectionUi.revision,()=>{if(dirty.value||busy.value){conflict.value=true;message.value='공유 정보가 변경되었습니다. 초안을 확인하고 다시 불러오세요.';}else void load();});
</script>
<template>
 <section class="asset-package-metadata" aria-label="패키지 상속과 개별 예외">
  <h3>패키지 상속·개별 예외</h3><button type="button" :disabled="busy" @click="load">초안을 버리고 상속 정보 다시 불러오기</button>
  <p v-if="snapshot?.fields.assetVersion">에셋 버전: {{ snapshot.fields.assetVersion.value||'미확인' }} · {{ snapshot.fields.assetVersion.status }} (개별 버전은 관리 정보에서 편집)</p>
  <form @submit.prevent="save"><fieldset :disabled="busy||!snapshot">
   <div v-for="(label,key) in labels" :key="key"><p>{{ label }}: {{ snapshot?.fields[key]?.value||'미확인' }} · {{ snapshot?.fields[key]?.source }} / {{ snapshot?.fields[key]?.status }}</p><p v-if="snapshot?.fields[key]?.packageIds.length">근거 패키지: {{ snapshot.fields[key]?.packageIds.join(', ') }}</p>
    <label>{{ label }} 적용 <select v-model="modes[key]" @change="dirty=true"><option value="inherit">패키지 상속</option><option value="set">개별 값</option><option value="clear">개별 미확인</option></select></label>
    <input v-if="modes[key]==='set'" v-model="values[key]" :aria-label="`${label} 개별 값`" :maxlength="key==='sourceUrl'?512:key==='engine'?128:256" @input="dirty=true" />
   </div><p>여러 패키지 값이 다르면 conflict로 표시합니다. 선언된 엔진·라이선스명은 호환성·이용 권한 검증을 의미하지 않습니다.</p><button :disabled="conflict">개별 예외 저장</button>
  </fieldset></form><p role="status">{{ message }}</p>
 </section>
</template>
