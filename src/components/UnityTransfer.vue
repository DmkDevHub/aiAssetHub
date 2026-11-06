<script setup lang="ts">
import {computed,onBeforeUnmount,ref,watch} from 'vue';
import {metadata} from '../services/metadata';
type Target={id:string;projectPath:string;connected:boolean;playing?:boolean;compiling?:boolean};
type Plan={planId:string;targetId:string;action:'import'|'place';projectPath:string;expiresAt:number;items:{assetId:string;fileId:string;targetRelativePath:string;sha256:string}[];issues:string[];scene?:string;position?:number[];rotation?:number[];scale?:number[]};
type Operation={operationId:string;targetId:string;action:string;status:string;result:unknown;errorCode?:string;mayHaveSideEffects?:boolean;cancelRequested?:boolean};
const props=defineProps<{assetIds:readonly string[]}>();
const targets=ref<Target[]>([]),target=ref(''),plan=ref<Plan|null>(null),operation=ref<Operation|null>(null),imported=ref<Operation|null>(null);
const position=ref('0,0,0'),rotation=ref('0,0,0'),scale=ref('1,1,1'),name=ref('AI Asset Hub Sprite');
const rights=ref(false),compatibility=ref(false),busy=ref(false),error=ref('');
let generation=0,alive=true,timer:ReturnType<typeof setInterval>|undefined,polling=false,writing=false;
const available=computed(()=>targets.value.some(t=>t.id===target.value&&t.connected&&!t.playing&&!t.compiling));
function invalidate(){generation++;plan.value=null;rights.value=false;compatibility.value=false;error.value='';if(!writing)busy.value=false;}
watch([()=>props.assetIds.join(','),target,position,rotation,scale,name],invalidate);
watch(target,()=>{imported.value=null;});
onBeforeUnmount(()=>{alive=false;generation++;if(timer)clearInterval(timer);});
async function act<T>(action:()=>Promise<T>,apply:(value:T)=>void){if(busy.value)return;busy.value=true;error.value='';const epoch=generation;try{const r=await action();if(alive&&epoch===generation)apply(r);}catch{if(alive&&epoch===generation){error.value='Unity 작업을 완료하지 못했습니다. 연결·충돌·파일·씬 변경을 확인하고 계획을 다시 검토하세요.';plan.value=null;rights.value=false;compatibility.value=false;}}finally{if(alive&&epoch===generation)busy.value=false;}}
async function load(){await act(()=>metadata<{items:Target[]}>('unity.targets',{}),r=>{targets.value=r.items;plan.value=null;rights.value=false;compatibility.value=false;});}
function previewImport(){return act(()=>metadata<Plan>('unity.preview_import',{target_id:target.value,asset_ids:[...props.assetIds]}),r=>{plan.value=r;rights.value=false;compatibility.value=false;});}
function previewPlace(){if(!imported.value||imported.value.targetId!==target.value)return;return act(()=>metadata<Plan>('unity.preview_place',{target_id:target.value,import_operation_id:imported.value!.operationId,position:position.value.split(',').map(Number),rotation:rotation.value.split(',').map(Number),scale:scale.value.split(',').map(Number),name:name.value}),r=>{plan.value=r;rights.value=false;compatibility.value=false;});}
async function poll(){
 if(!operation.value||polling)return;polling=true;const id=operation.value.operationId;
 try{const r=await metadata<Operation>('unity.status',{operation_id:id});if(!alive||operation.value?.operationId!==id)return;operation.value=r;
  if(r.action==='import'&&['succeeded','partial'].includes(r.status))imported.value=r;
  if(!['queued'].includes(r.status)&&timer){clearInterval(timer);timer=undefined;}
 }catch{if(alive)error.value='Unity 작업 결과를 확인하지 못했습니다. 성공으로 간주하지 말고 상태를 다시 조회하세요.';if(timer)clearInterval(timer);timer=undefined;}
 finally{polling=false;}
}
function cancel(){if(!operation.value)return;const id=operation.value.operationId;return act(()=>metadata<Operation>('unity.cancel',{operation_id:id,confirmed:true}),r=>{if(operation.value?.operationId===id)operation.value=r;});}
async function execute(){if(busy.value||!plan.value||!rights.value||!compatibility.value||plan.value.expiresAt*1000<Date.now())return;
 const reviewed=plan.value;busy.value=true;writing=true;error.value='';
 try{const r=await metadata<Operation>(reviewed.action==='import'?'unity.import':'unity.place',{plan_id:reviewed.planId,request_id:crypto.randomUUID(),confirmed:true,rights_confirmed:true,compatibility_confirmed:true});if(!alive)return;
  if(plan.value?.planId===reviewed.planId)plan.value=null;rights.value=false;compatibility.value=false;operation.value=r;
  if(r.action==='import'&&['succeeded','partial'].includes(r.status))imported.value=r;
  if(timer)clearInterval(timer);if(r.status==='queued'){timer=setInterval(()=>{void poll();},500);void poll();}
 }catch{if(alive){plan.value=null;rights.value=false;compatibility.value=false;error.value='Unity 실행 결과를 확인하지 못했습니다. 작업 기록을 조회하고 다시 계획하세요.';}}
 finally{writing=false;if(alive)busy.value=false;}
}
</script>
<template>
 <details class="unity-transfer"><summary>선택 에셋 Unity 임포트·배치</summary>
  <p>최대 20개의 단일 PNG를 지원합니다. Unity 연결 설정에서 허용한 열린 프로젝트를 선택하세요.</p>
  <button type="button" :disabled="busy" @click="load">Unity 대상 조회</button>
  <label>Unity 대상 <select v-model="target" :disabled="busy"><option value="">대상 선택</option><option v-for="t in targets" :key="t.id" :value="t.id">{{t.projectPath}} · {{t.connected?'연결됨':'연결 안 됨'}}</option></select></label>
  <button type="button" :disabled="busy||!available||!assetIds.length||assetIds.length>20" @click="previewImport">PNG 임포트 미리보기</button>
  <fieldset :disabled="busy"><legend>Sprite 배치</legend>
   <label>객체 이름 <input v-model="name" maxlength="80"></label>
   <label>위치 XYZ <input v-model="position"></label><label>회전 XYZ (도) <input v-model="rotation"></label><label>크기 XYZ <input v-model="scale"></label>
   <button type="button" :disabled="!available||!imported||imported.targetId!==target" @click="previewPlace">Sprite 배치 미리보기</button>
  </fieldset>
  <div v-if="plan" class="unity-plan"><p>대상 {{plan.projectPath}} · {{plan.action==='import'?'PNG 임포트':'Sprite 배치'}} · 계획 만료 {{new Date(plan.expiresAt*1000).toLocaleTimeString()}}</p>
   <ul><li v-for="item in plan.items" :key="item.fileId">{{item.assetId}} → {{item.targetRelativePath}} · SHA256 {{item.sha256}}</li></ul>
   <p v-if="plan.action==='place'">씬 {{plan.scene||'저장되지 않은 활성 씬'}} · 위치 {{plan.position}} · 회전 {{plan.rotation}} · 크기 {{plan.scale}} · 씬은 저장하지 않습니다.</p>
   <label><input v-model="rights" type="checkbox" :disabled="busy">라이선스·사용 권한을 검토했습니다</label>
   <label><input v-model="compatibility" type="checkbox" :disabled="busy">호환성이 미확인임을 검토하고 실행을 승인합니다</label>
   <button type="button" :disabled="busy||!rights||!compatibility" @click="execute">{{plan.action==='import'?'검토한 임포트 실행':'검토한 배치 실행'}}</button>
   <button type="button" :disabled="busy" @click="invalidate">Unity 계획 취소</button>
  </div>
  <p v-if="error" role="alert">{{error}}</p>
  <div v-if="operation" role="status"><p>Unity 작업 {{operation.operationId}} · {{operation.status}}</p><p v-if="operation.errorCode">{{operation.errorCode}}</p><p v-if="operation.cancelRequested">취소를 요청했습니다. 이미 처리한 항목은 유지되며 Editor 결과를 기다립니다.</p><p v-if="operation.status==='unknown'">응답을 확정하지 못했습니다. 이미 적용되었을 수 있으므로 결과를 확인한 뒤 다시 계획하세요.</p><pre>{{JSON.stringify(operation.result,null,2)}}</pre><button type="button" @click="poll">Unity 작업 상태 조회</button><button v-if="['queued','unknown'].includes(operation.status)" type="button" :disabled="busy" @click="cancel">Unity 작업 취소 요청</button></div>
 </details>
</template>
<style scoped>.unity-transfer{margin-block:.5rem;overflow-wrap:anywhere}.unity-transfer label{display:block;margin:.4rem}fieldset{margin-block:.5rem}pre{white-space:pre-wrap}button{margin:.25rem}</style>
