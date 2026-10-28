<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
type Model = {id:string;provider:string;kind:string;modelId:string;modalities:string[];enabled:boolean;inspection?:{status?:string;checkedAt?:string;modalities?:string[];costClass?:string;metadataRequestAttempted?:boolean;authentication?:string}};
const items=ref<Model[]>([]), provider=ref(''), modelId=ref(''), kind=ref('local'), modality=ref('image');
const externalConsent=ref(false);
const busy=ref(false), error=ref(''), notice=ref('');
let alive=true;
onBeforeUnmount(()=>{alive=false;});
async function load() {
  if(!isTauri()) {error.value='데스크톱 앱에서 모델 정보를 조회할 수 있습니다.';return;}
  busy.value=true;error.value='';
  try {
    const result:Model[]=[];let cursor:string|null=null;const seen=new Set<string>();
    do {
      const response:{ok:boolean;data:{items:Model[];next_cursor:string|null}}=await invoke('list_models',{afterId:cursor});
      if(!alive)return;
      if(!response.ok || !Array.isArray(response.data?.items))throw new Error();
      for(const item of response.data.items){
        if(typeof item.id!=='string' || seen.has(item.id) || typeof item.modelId!=='string' || !Array.isArray(item.modalities))throw new Error();
        seen.add(item.id);result.push(item);
      }
      cursor=response.data.next_cursor;
      if(cursor!==null && (typeof cursor!=='string' || cursor!==result.at(-1)?.id || result.length>10000))throw new Error();
    }while(cursor);
    items.value=result;
  }catch{if(alive)error.value='모델 목록을 불러오지 못했습니다.';}
  finally{if(alive)busy.value=false;}
}
async function register() {
  if(busy.value || !isTauri())return;
  busy.value=true;error.value='';notice.value='';
  try{
    const response=await invoke<{ok:boolean}>('register_model',{providerName:provider.value,kind:kind.value,modelId:modelId.value,modalities:[modality.value]});
    if(!alive)return;
    if(!response.ok)throw new Error();
    notice.value='프로필을 저장했습니다. 모델 실행이나 외부 전송은 발생하지 않았습니다.';
  }catch{if(alive)error.value='모델 프로필을 저장하지 못했습니다.';}
  finally{if(alive)busy.value=false;}
  if(alive)await load();
}
async function inspect(id:string){
 if(busy.value)return;busy.value=true;error.value='';
 try{const result=await invoke<{ok:boolean}>('inspect_model',{id,allowExternal:externalConsent.value});if(!result.ok)throw new Error();}
 catch{if(alive)error.value='모델 상태를 확인하지 못했습니다.';}
 finally{if(alive)busy.value=false;}
 if(alive)await load();
}
onMounted(load);
</script>
<template>
  <section class="page models-page" aria-labelledby="models-title">
    <h1 id="models-title">모델 관리</h1>
    <p>모델 ID는 설치된 모델 또는 공급자의 실제 ID를 입력하세요. 등록만으로 연결·분석을 실행하지 않습니다.</p>
    <form class="model-registration" @submit.prevent="register">
      <label>공급자 <input v-model="provider" required maxlength="80" :disabled="busy" /></label>
      <label>구분 <select v-model="kind" :disabled="busy"><option value="local">로컬</option><option value="external">외부</option></select></label>
      <label>모델 ID <input v-model="modelId" required maxlength="160" :disabled="busy" /></label>
      <label>등록 입력 유형 <select v-model="modality" :disabled="busy"><option value="image">이미지</option><option value="text">텍스트</option><option value="audio">오디오</option></select></label>
      <button :disabled="busy">프로필 등록</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button type="button" :disabled="busy" @click="load">목록 새로고침</button>
    <p v-if="!busy && !items.length">등록된 모델이 없습니다.</p>
    <label><input v-model="externalConsent" type="checkbox" />외부 연결 검사 허용: OpenRouter로 모델 카탈로그 요청(IP·저장된 자격 증명)을 전송합니다. 에셋·프롬프트·생성 요청은 전송하지 않습니다.</label>
    <ul class="model-list"><li v-for="item in items" :key="item.id">
      <strong>{{ item.modelId }}</strong> · {{ item.provider }} · {{ item.kind==='local'?'로컬':'외부' }}
      <button v-if="item.kind==='local' || item.provider.toLowerCase()==='openrouter'" type="button" :disabled="busy" @click="inspect(item.id)">{{ item.kind==='local'?'로컬 사용 가능성 검사':'외부 연결 검사' }}</button>
      <p>확인 상태: {{ item.inspection?.status ?? '미검사' }} · {{ item.inspection?.checkedAt ?? '' }}</p>
      <p>확인된 입력: {{ item.inspection?.modalities?.join(', ') || '없음' }} · 추론 호출 없음</p>
      <p v-if="item.kind==='external'">비용 분류: {{ item.inspection?.costClass ?? '미확인' }} · 메타데이터 요청 시도: {{ item.inspection?.metadataRequestAttempted ? '시도함' : '시도 안 함' }} · 인증: {{ item.inspection?.authentication ?? '미확인' }}</p>
      <p>등록 입력: {{ item.modalities.join(', ') }} · {{ item.enabled?'활성':'비활성' }}</p>
    </li></ul>
  </section>
</template>
