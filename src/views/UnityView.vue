<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref} from 'vue';
import {metadata} from '../services/metadata';
type Target={id:string;projectPath:string;connected:boolean;editorVersion?:string;scene?:string;playing?:boolean;compiling?:boolean;errorCode?:string};
const targets=ref<Target[]>([]),path=ref(''),busy=ref(false),error=ref('');
let alive=true;onBeforeUnmount(()=>{alive=false;});
async function load(){const r=await metadata<{items:Target[]}>('unity.targets',{});if(alive)targets.value=r.items;}
async function act(action:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await action();}catch{if(alive)error.value='Unity 대상 정보를 처리하지 못했습니다. 프로젝트 경로와 연결 상태를 확인하세요.';}finally{if(alive)busy.value=false;}}
async function register(){await metadata('unity.target.save',{project_path:path.value,confirmed:true});if(alive)path.value='';await load();}
async function remove(id:string){await metadata('unity.target.remove',{target_id:id,confirmed:true});await load();}
onMounted(()=>{void act(load);});
</script>
<template>
 <section class="unity-settings" aria-labelledby="unity-title">
  <h1 id="unity-title">Unity 연결</h1>
  <p>Unity Package Manager에서 AI Asset Hub Editor Connector의 package.json을 로컬 패키지로 추가하세요. 현재 열린 프로젝트를 아래 허용 목록에 등록하면 연결 상태를 조회합니다.</p>
  <form @submit.prevent="act(register)"><label>Unity 프로젝트 경로 <input v-model="path" :disabled="busy" required maxlength="2048"></label><button :disabled="busy||!path.trim()">프로젝트 접근 허용</button></form>
  <button type="button" :disabled="busy" @click="act(load)">Unity 대상 새로 조회</button>
  <p v-if="error" role="alert">{{ error }}</p>
  <p v-if="!targets.length&&!busy">허용한 Unity 프로젝트가 없습니다.</p>
  <ul><li v-for="target in targets" :key="target.id"><strong>{{ target.projectPath }}</strong> · {{ target.connected?'연결됨':'연결 안 됨' }}
   <span v-if="target.connected"> · {{ target.editorVersion }} · 씬 {{ target.scene||'저장되지 않은 씬' }}<span v-if="target.playing"> · 플레이 중</span><span v-if="target.compiling"> · 컴파일 중</span></span>
   <button type="button" :disabled="busy" @click="act(()=>remove(target.id))">프로젝트 접근 해제</button>
  </li></ul>
 </section>
</template>
<style scoped>.unity-settings{padding:1.5rem;max-width:70rem;margin:auto;overflow-wrap:anywhere}.unity-settings li{margin-block:1rem}.unity-settings input{width:min(35rem,70%)}button{margin:.3rem}</style>
