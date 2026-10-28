<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { invoke } from '@tauri-apps/api/core';
const props=defineProps<{id:string;hasCredential?:boolean;allowExternal:boolean}>();
const emit=defineEmits<{changed:[]}>();
const key=ref(''),busy=ref(false),message=ref('');let alive=true;
onBeforeUnmount(()=>{alive=false;key.value='';});
async function act(action:string){
 if(busy.value)return;busy.value=true;message.value='';
 const secret=key.value;key.value='';
 try{
  const result=await invoke<{ok:boolean;data:{status:string}}>('model_credential',{id:props.id,action,key:action==='save'?secret:null,allowExternal:props.allowExternal});
  if(!alive)return;if(!result.ok)throw new Error();
  message.value=result.data.status;emit('changed');
 }catch{if(alive)message.value='자격 증명 작업에 실패했습니다.';}
 finally{if(alive)busy.value=false;}
}
</script>
<template>
 <section class="model-credential" aria-label="모델 자격 증명">
  <p>Windows 자격 증명: {{ hasCredential?'저장됨':'없음' }}</p>
  <form @submit.prevent="act('save')"><label>API 키 <input v-model="key" type="password" autocomplete="off" maxlength="1024" :disabled="busy" /></label><button :disabled="busy || !key">키 저장</button></form>
  <button type="button" :disabled="busy || !hasCredential" @click="act('delete')">키 삭제</button>
  <button type="button" :disabled="busy || !hasCredential || !allowExternal" @click="act('test')">인증 검사 (생성 호출 없음)</button>
  <p v-if="message" role="status">{{ message }}</p>
 </section>
</template>
