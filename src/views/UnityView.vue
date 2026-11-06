<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref} from 'vue';
import {metadata} from '../services/metadata';
type Target={id:string;projectPath:string;connected:boolean;editorVersion?:string;scene?:string;playing?:boolean;compiling?:boolean;errorCode?:string};
const targets=ref<Target[]>([]),path=ref(''),busy=ref(false),error=ref('');
const packagePath=ref<string|null>(null);
type Operation={operationId:string;status:string;action:string;createdAt:string};
const operations=ref<Operation[]>([]),cursor=ref<string|null>(null),result=ref<unknown>(null);
let alive=true;onBeforeUnmount(()=>{alive=false;});
async function load(){const r=await metadata<{items:Target[];connectorPackagePath?:string|null}>('unity.targets',{});if(alive){targets.value=r.items;packagePath.value=r.connectorPackagePath??null;}}
async function act(action:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await action();}catch{if(alive)error.value='Unity 대상 정보를 처리하지 못했습니다. 프로젝트 경로와 연결 상태를 확인하세요.';}finally{if(alive)busy.value=false;}}
async function register(){await metadata('unity.target.save',{project_path:path.value,confirmed:true});if(alive)path.value='';await load();}
async function remove(id:string){await metadata('unity.target.remove',{target_id:id,confirmed:true});await load();}
async function history(more=false){const r=await metadata<{items:Operation[];next_cursor:string|null}>('unity.operations',{after_id:more?cursor.value:null});if(alive){operations.value=more?[...operations.value,...r.items]:r.items;cursor.value=r.next_cursor;}}
async function status(id:string){const r=await metadata('unity.status',{operation_id:id});if(alive)result.value=r;}
async function cancel(id:string){await metadata('unity.cancel',{operation_id:id,confirmed:true});await status(id);}
onMounted(()=>{void act(load);});
</script>
<template>
 <section class="unity-settings" aria-labelledby="unity-title">
  <h1 id="unity-title">Unity 연결</h1>
  <p>Unity Package Manager에서 AI Asset Hub Editor Connector의 package.json을 로컬 패키지로 추가하세요. 현재 열린 프로젝트를 아래 허용 목록에 등록하면 연결 상태를 조회합니다.</p>
  <p v-if="packagePath">로컬 패키지: <code>{{packagePath}}</code></p>
  <form @submit.prevent="act(register)"><label>Unity 프로젝트 경로 <input v-model="path" :disabled="busy" required maxlength="2048"></label><button :disabled="busy||!path.trim()">프로젝트 접근 허용</button></form>
  <button type="button" :disabled="busy" @click="act(load)">Unity 대상 새로 조회</button>
  <p v-if="error" role="alert">{{ error }}</p>
  <p v-if="!targets.length&&!busy">허용한 Unity 프로젝트가 없습니다.</p>
  <ul><li v-for="target in targets" :key="target.id"><strong>{{ target.projectPath }}</strong> · {{ target.connected?'연결됨':'연결 안 됨' }}
   <span v-if="target.connected"> · {{ target.editorVersion }} · 씬 {{ target.scene||'저장되지 않은 씬' }}<span v-if="target.playing"> · 플레이 중</span><span v-if="target.compiling"> · 컴파일 중</span></span>
   <button type="button" :disabled="busy" @click="act(()=>remove(target.id))">프로젝트 접근 해제</button>
  </li></ul>
  <h2>Unity 작업 기록</h2><p>재시작·연결 단절 후에는 실제 결과를 조회하세요. 씬 배치 ID는 해당 Editor 세션에서만 유효하며 씬을 자동 저장하지 않습니다.</p>
  <button type="button" :disabled="busy" @click="act(()=>history())">Unity 작업 기록 조회</button>
  <ol><li v-for="item in operations" :key="item.operationId">{{item.operationId}} · {{item.action}} · {{item.status}} · {{item.createdAt}}
   <button type="button" :disabled="busy" @click="act(()=>status(item.operationId))">이 작업 결과 조회</button>
   <button v-if="['queued','unknown'].includes(item.status)" type="button" :disabled="busy" @click="act(()=>cancel(item.operationId))">이 작업 취소 요청</button>
  </li></ol>
  <button v-if="cursor" type="button" :disabled="busy" @click="act(()=>history(true))">이전 Unity 작업 더 보기</button>
  <pre v-if="result" role="status">{{JSON.stringify(result,null,2)}}</pre>
 </section>
</template>
<style scoped>.unity-settings{padding:1.5rem;max-width:70rem;margin:auto;overflow-wrap:anywhere}.unity-settings li{margin-block:1rem}.unity-settings input{width:min(35rem,70%)}button{margin:.3rem}</style>
