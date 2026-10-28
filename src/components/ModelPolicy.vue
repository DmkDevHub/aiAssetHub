<script setup lang="ts">
import { ref, watch } from 'vue';
import { invoke } from '@tauri-apps/api/core';
type Policy={allowExternal:boolean;allowPaid:boolean;budgetUsd:string;maxRequests:number;reservedUsd:string;requestsUsed:number};
const props=defineProps<{id:string;enabled:boolean;policy?:Policy}>();
const emit=defineEmits<{changed:[]}>();
const enabled=ref(false),external=ref(false),paid=ref(false),budget=ref('0'),limit=ref(100),busy=ref(false),message=ref('');
watch(()=>[props.enabled,props.policy] as const,()=>{enabled.value=props.enabled;external.value=props.policy?.allowExternal??false;paid.value=props.policy?.allowPaid??false;budget.value=props.policy?.budgetUsd??'0';limit.value=props.policy?.maxRequests??100;},{immediate:true});
async function save(){
 if(busy.value)return;busy.value=true;message.value='';
 try{
  const result=await invoke<{ok:boolean;error?:{code:string}}>('configure_model',{policy:{id:props.id,enabled:enabled.value,allow_external:external.value,allow_paid:paid.value,budget_usd:budget.value,max_requests:limit.value}});
  if(!result.ok){message.value=result.error?.code==='BUDGET_EXCEEDED'?'예산 또는 호출 한도를 초과합니다.':'모델 상태·인증·전송 승인·유료 승인과 예산을 확인하세요.';return;}
  message.value='사용 정책을 저장했습니다. 분석은 실행하지 않았습니다.';emit('changed');
 }catch{message.value='사용 정책을 저장하지 못했습니다.';}
 finally{busy.value=false;}
}
</script>
<template>
 <form class="model-policy" aria-label="모델 사용 정책" @submit.prevent="save">
  <label><input v-model="enabled" type="checkbox" :disabled="busy" />모델 활성화</label>
  <label><input v-model="external" type="checkbox" :disabled="busy" />분석 시 외부 전송 허용 (이미지·텍스트·오디오 입력)</label>
  <label><input v-model="paid" type="checkbox" :disabled="busy" />유료 모델 사용 승인</label>
  <label>예산 하드리밋 USD <input v-model="budget" inputmode="decimal" :disabled="busy" /></label>
  <label>누적 호출 한도 <input v-model.number="limit" type="number" min="1" max="10000" :disabled="busy" /></label>
  <p>예약 상한 비용: {{ policy?.reservedUsd??'0' }} USD · 예약 호출: {{ policy?.requestsUsed??0 }}. 실제 청구액과 다를 수 있습니다.</p>
  <button :disabled="busy">사용 정책 저장</button><p v-if="message" role="status">{{ message }}</p>
 </form>
</template>
