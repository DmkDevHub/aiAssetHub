<script setup lang="ts">
import { ref } from 'vue';
import { invoke,isTauri } from '@tauri-apps/api/core';
const props=defineProps<{selected:readonly {asset_id:string;result_id:string}[]}>();
const model=ref(''),prefix=ref('plain'),busy=ref(false),error=ref('');
const status=ref<{profile:{modelName:string;dimension:number;version:string}|null;readyCount:number}|null>(null);
async function read(){
 if(!isTauri() || busy.value)return;busy.value=true;error.value='';
 try{const r=await invoke<{ok:boolean;data:NonNullable<typeof status.value>}>('embedding_status');if(!r.ok)throw new Error();status.value=r.data;}
 catch{error.value='임베딩 준비 상태를 확인하지 못했습니다.';}finally{busy.value=false;}
}
async function configure(){
 if(!isTauri() || busy.value)return;busy.value=true;error.value='';
 try{const r=await invoke<{ok:boolean}>('embedding_configure',{modelName:model.value,prefixScheme:prefix.value});if(!r.ok)throw new Error();}
 catch{error.value='모델의 임베딩 지원과 차원을 확인하지 못했습니다.';}finally{busy.value=false;}
 await read();
}
</script>
<template>
 <details class="embedding-tools"><summary>의미 검색 준비</summary>
  <p>로컬 Ollama 임베딩 모델을 사용합니다. 설정은 메타데이터만 확인하며 임베딩을 생성하지 않습니다.</p>
  <form @submit.prevent="configure"><label>실제 임베딩 모델 ID <input v-model="model" required maxlength="160" :disabled="busy" /></label>
   <label>텍스트 규격 <select v-model="prefix" :disabled="busy"><option value="plain">일반</option><option value="embeddinggemma">EmbeddingGemma 검색 규격</option></select></label><button :disabled="busy">모델 확인·저장</button></form>
  <button type="button" :disabled="busy" @click="read">임베딩 준비 상태 확인</button>
  <p v-if="status?.profile">{{ status.profile.modelName }} · {{ status.profile.dimension }}차원 · 버전 {{ status.profile.version }} · 준비 {{ status.readyCount }}개</p>
  <p v-else-if="status">임베딩 모델이 설정되지 않았습니다.</p>
  <p>선택된 성공 결과 {{ props.selected.length }}개</p><p v-if="error" role="alert">{{ error }}</p>
 </details>
</template>
