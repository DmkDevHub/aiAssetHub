<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { invoke,isTauri } from '@tauri-apps/api/core';
const props=defineProps<{selected:readonly {asset_id:string;result_id:string}[]}>();
const rebuildApproved=ref(false);
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
const work=ref<{status:string;processed:number;total:number;failed:number;error?:string;errors?:{assetId:string;code:string}[]}|null>(null);let timer:ReturnType<typeof setInterval>|undefined,alive=true,polling=false;
onBeforeUnmount(()=>{alive=false;if(timer)clearInterval(timer);});
async function generate(rebuild=false){
 if(busy.value || (!rebuild && (!props.selected.length || props.selected.length>100)) || (rebuild && !rebuildApproved.value))return;busy.value=true;error.value='';
 try{
  const r=await invoke<{ok:boolean;data:{jobId:string}}>(rebuild?'embedding_rebuild':'embedding_start',rebuild?{confirmed:true}:{selected:props.selected,confirmed:true});if(!r.ok)throw new Error();
  const poll=async()=>{if(polling)return;polling=true;try{
   const result=await invoke<{ok:boolean;data:NonNullable<typeof work.value>}>('embedding_work',{jobId:r.data.jobId});if(!alive)return;if(!result.ok)throw new Error();work.value=result.data;
   if(!['queued','running'].includes(result.data.status)){if(timer)clearInterval(timer);busy.value=false;await read();}
  }catch{if(timer)clearInterval(timer);error.value='임베딩 작업 상태를 확인하지 못했습니다.';busy.value=false;}finally{polling=false;}};
  timer=setInterval(()=>{void poll();},1000);void poll();
 }catch{error.value='선택된 활성 결과의 임베딩을 시작하지 못했습니다.';busy.value=false;}
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
  <p>선택된 현재 성공 결과의 설명·태그만 로컬 모델로 전송합니다. 원본 파일은 전송하지 않습니다.</p>
  <button type="button" :disabled="busy || !props.selected.length || props.selected.length>100" @click="generate(false)">선택 결과 임베딩 생성 (최대 100개)</button>
  <p v-if="work" role="status">{{ work.status }} · {{ work.processed }}/{{ work.total }} · 실패 {{ work.failed }}</p>
  <label><input v-model="rebuildApproved" type="checkbox" :disabled="busy" />현재 버전의 전체 활성 결과(최대 1000개)와 키워드 인덱스 재구축을 승인합니다.</label>
  <button type="button" :disabled="busy || !rebuildApproved || !status?.profile" @click="generate(true)">현재 버전 전체 재구축</button>
  <p>재구축은 모든 계산·검증이 성공한 뒤 한 번에 교체합니다. 이전 모델 버전의 벡터는 보존합니다.</p>
  <p v-if="work?.error" role="alert">작업 오류: {{ work.error }}</p>
  <ul v-if="work?.errors?.length"><li v-for="item in work.errors" :key="item.assetId">{{ item.assetId }} · {{ item.code }}</li></ul>
  <p>선택된 성공 결과 {{ props.selected.length }}개</p><p v-if="error" role="alert">{{ error }}</p>
 </details>
</template>
