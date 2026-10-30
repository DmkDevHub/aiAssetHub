<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { receiveOperation } from '../stores/operations';
import { refreshAssets } from '../stores/assets';
import { invoke, isTauri } from '@tauri-apps/api/core';
const props=defineProps<{selectedIds:string[];folderId:string|null}>();
const open=ref(false),busy=ref(false),error=ref(''),mode=ref('selected'),scope=ref('folder'),model=ref('');
const inputKind=ref('image');
const preview=ref<{targetCount:number;missingCount:number;planToken:string;eligibleCount?:number;unsupportedCount?:number;unknownFormatCount?:number;overLimitCount?:number;estimatedUpperBoundUsd?:string;externalTransfer?:boolean;paid?:boolean;snapshot?:{analysisContract?:{version:string;inputSchema:string;outputSchema:string;reviewInputFingerprint:string}}}|null>(null);
const retrySelection=ref<string[]|null>(null),retryContext=ref<{library_id:string|null;folder_parts:string[]}|null>(null),cancelMessage=ref('');
watch([mode,()=>props.selectedIds.join(',')],()=>{retrySelection.value=null;});
watch([scope,()=>props.folderId],()=>{retryContext.value=null;});
const jobs=ref<{id:string;status:string;total:number;createdAt:string}[]>([]);
const external=ref(false),paid=ref(false),startId=ref(''),jobId=ref('');
watch([mode,scope,model,inputKind,()=>props.selectedIds.join(','),()=>props.folderId],()=>{preview.value=null;startId.value='';external.value=false;paid.value=false;});
const models=ref<{id:string;modelId:string;enabled:boolean;kind?:string;selected?:boolean;inspection?:{modalities?:string[]}}[]>([]);
watch(inputKind,()=>{const required=['threeD','animation'].includes(inputKind.value)?'image':inputKind.value;const current=models.value.find(m=>m.id===model.value);if(current&&(!current.inspection?.modalities?.includes(required)||(required==='audio'&&current.kind!=='external')))model.value='';});
const trigger=ref<HTMLButtonElement>(),panel=ref<HTMLElement>();let alive=true;
const progress=ref<{status:string;total:number;processed:number;succeeded:number;failed:number;canceled:number;needsRecovery:boolean;partialSuccess?:boolean;errors?:{assetId:string;code:string}[]}|null>(null);
let timer:ReturnType<typeof setInterval>|undefined,polling=false,finished='';
onMounted(()=>{timer=setInterval(()=>{if(jobId.value)void poll();},1000);});
onBeforeUnmount(()=>{alive=false;if(timer)clearInterval(timer);});
async function poll(){
 if(polling || !jobId.value || finished===jobId.value)return;polling=true;
 try{
  const result=await invoke<{ok:boolean;data:NonNullable<typeof progress.value>}>('analysis_status',{jobId:jobId.value});
  if(!alive)return;if(!result.ok || !Number.isSafeInteger(result.data?.processed) || !Number.isSafeInteger(result.data.total) || result.data.processed<0 || result.data.processed>result.data.total || result.data.succeeded+result.data.failed+result.data.canceled!==result.data.processed)throw new Error();progress.value=result.data;
  const state=result.data.needsRecovery?'failed':result.data.status==='completed'?'succeeded':result.data.status==='failed'?'failed':result.data.status==='canceled'?'cancelled':'running';
  receiveOperation({id:jobId.value,kind:'analysis.run',state,progress:{processed:result.data.processed,total:result.data.total},...(state==='failed'?{errorCode:result.data.needsRecovery?'CORE_UNAVAILABLE':'COMMAND_FAILED'}:{})});
  if(['completed','failed','canceled'].includes(result.data.status)){finished=jobId.value;await refreshAssets();}
 }catch{if(alive)error.value='분석 상태를 불러오지 못했습니다. 연결을 확인하세요.';}
 finally{polling=false;}
}
async function loadJobs(){
 if(busy.value || !isTauri())return;busy.value=true;error.value='';
 try{const result=await invoke<{ok:boolean;data:{items:typeof jobs.value}}>('analysis_jobs');if(!result.ok || !Array.isArray(result.data?.items))throw new Error();jobs.value=result.data.items;}
 catch{error.value='분석 작업 목록을 불러오지 못했습니다.';}
 finally{busy.value=false;}
}
function track(id:string){jobId.value=id;finished='';progress.value=null;void poll();}
async function show(){
 open.value=true;inputKind.value='image';retrySelection.value=null;retryContext.value=null;preview.value=null;error.value='';model.value='';models.value=[];busy.value=true;
 await nextTick();panel.value?.querySelector<HTMLElement>('select')?.focus();
 if(!isTauri()){busy.value=false;error.value='데스크톱 Core 연결이 필요합니다.';return;}
 try{
  let cursor:string|null=null;const rows:typeof models.value=[];const seen=new Set<string>();
  do{
   const result:{ok:boolean;data:{items:typeof models.value;next_cursor:string|null}}=await invoke('list_models',{afterId:cursor});
   if(!alive)return;if(!result.ok || !Array.isArray(result.data?.items))throw new Error();
   for(const item of result.data.items){if(typeof item.id!=='string'||seen.has(item.id))throw new Error();seen.add(item.id);rows.push(item);}
   cursor=result.data.next_cursor;if(cursor!==null && (cursor!==rows.at(-1)?.id || rows.length>10000))throw new Error();
  }while(cursor);
  models.value=rows;model.value=rows.find(m=>m.selected)?.id??'';
 }catch{if(alive)error.value='모델 목록을 불러오지 못했습니다.';}
 finally{if(alive)busy.value=false;}
}
function requestPlan(){
 let library:string|null=null,parts:string[]=[];
 if(scope.value!=='all' && retryContext.value){library=retryContext.value.library_id;parts=retryContext.value.folder_parts;}
 else if(scope.value!=='all'){
  if(!props.folderId)throw new Error();
  if(props.folderId.startsWith('folder:')){
   const path=JSON.parse(props.folderId.slice(7)) as string[];library=path[0]??null;
   if(scope.value==='folder')parts=path.slice(1);
  }else library=props.folderId;
 }
 return {mode:mode.value,scope:scope.value,library_id:library,folder_parts:parts,selected_ids:mode.value==='selected'?(retrySelection.value??props.selectedIds):[],model_id:model.value,...(inputKind.value!=='image'?{input_kind:inputKind.value}:{})};
}
async function review(){
 if(busy.value || !model.value)return;busy.value=true;error.value='';preview.value=null;startId.value='';external.value=false;paid.value=false;
 try{
  const result=await invoke<{ok:boolean;data:{targetCount:number;missingCount:number;planToken:string}}>('preview_analysis',{plan:requestPlan()});
  if(!result.ok || !Number.isSafeInteger(result.data?.targetCount))throw new Error();
  preview.value=result.data;
 }catch{error.value='대상을 확인하지 못했습니다. 분석 범위와 모델을 확인하세요.';}
 finally{busy.value=false;}
}
async function cancel(){
 if(busy.value || !jobId.value)return;busy.value=true;cancelMessage.value='';
 try{
  const result=await invoke<{ok:boolean;data:{cancelRequested:boolean}}>('cancel_analysis',{jobId:jobId.value});
  if(!result.ok)throw new Error();cancelMessage.value='취소 요청을 보냈습니다. 실제 중단 상태를 확인 중입니다.';finished='';void poll();
 }catch{error.value='취소 요청에 실패했습니다.';}
 finally{busy.value=false;}
}
async function retry(){
 if(busy.value || !jobId.value)return;error.value='';
 try{
  const result=await invoke<{ok:boolean;data:{plan:ReturnType<typeof requestPlan>}}>('retry_analysis_plan',{jobId:jobId.value});
  if(!result.ok)throw new Error();const plan=result.data.plan;
  await show();mode.value=plan.mode;scope.value=plan.scope;model.value=plan.model_id;inputKind.value=plan.input_kind??'image';await nextTick();
  retrySelection.value=plan.selected_ids;retryContext.value={library_id:plan.library_id,folder_parts:plan.folder_parts};await review();
 }catch{error.value='이전 작업을 재검토하지 못했습니다.';}
}
async function start(){
 if(busy.value || !(preview.value?.eligibleCount??preview.value?.targetCount))return;busy.value=true;error.value='';
 try{
  startId.value ||= crypto.randomUUID();
  const result=await invoke<{ok:boolean;data:{jobId:string};error?:{code:string}}>('start_analysis',{request:{plan:requestPlan(),plan_token:preview.value.planToken,request_id:startId.value,confirmed:true,confirm_external:external.value,confirm_paid:paid.value}});
  if(!result.ok || typeof result.data?.jobId!=='string'){if(result.error?.code==='ANALYSIS_PLAN_CHANGED')preview.value=null;throw new Error();}
  jobId.value=result.data.jobId;progress.value=null;finished='';void poll();
 }catch{error.value='분석 요청을 저장하지 못했습니다. 대상·모델·비용을 다시 확인하세요.';}
 finally{busy.value=false;}
}
async function close(){open.value=false;await nextTick();trigger.value?.focus();}
function keys(event:KeyboardEvent){
 if(event.key==='Escape'){event.preventDefault();void close();return;}
 if(event.key!=='Tab')return;
 const controls=[...panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled),select:not(:disabled),input:not(:disabled)')??[]];
 const first=controls[0],last=controls.at(-1);
 if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
 else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
}
</script>
<template>
 <button ref="trigger" type="button" class="analysis-open" @click="show">AI 분석</button>
 <button type="button" :disabled="busy" @click="loadJobs">최근 분석 작업 확인</button>
 <p v-if="error && !open" role="alert">{{ error }}</p>
 <p v-if="progress && !open" role="status">분석 {{ progress.status }} · {{ progress.processed }}/{{ progress.total }} · 성공 {{ progress.succeeded }} · 실패 {{ progress.failed }}</p>
 <ul v-if="jobs.length" class="analysis-job-list" aria-label="최근 20개 분석 작업"><li v-for="job in jobs" :key="job.id"><button type="button" @click="track(job.id)">{{ job.createdAt }} · {{ job.status }} · {{ job.total }}개</button></li></ul>
 <p v-if="progress?.partialSuccess" role="status">일부 대상만 성공했습니다. 실패/취소 대상과 이전 성공 결과를 확인하세요.</p><p v-if="cancelMessage" role="status">{{ cancelMessage }}</p>
 <button v-if="jobId && (!progress || ['queued','running'].includes(progress.status))" type="button" :disabled="busy" @click="cancel">{{ progress?.needsRecovery?'중단 작업 취소/정리':'분석 취소 요청' }}</button>
 <button v-if="progress && ['completed','failed','canceled'].includes(progress.status)" type="button" :disabled="busy" @click="retry">같은 조건으로 재검토</button>
 <div v-if="open" class="analysis-overlay">
  <section ref="panel" role="dialog" aria-modal="true" aria-labelledby="analysis-title" class="analysis-dialog" @keydown="keys">
   <h2 id="analysis-title">수동 AI 분석</h2>
   <p>대상·모델·전송 범위·비용을 확인한 뒤 분석 시작을 눌러야 실행됩니다. 이 창을 여는 것만으로 AI를 호출하지 않습니다.</p>
   <p>이미지는 PNG/JPEG, 오디오는 최대 60초 PCM WAV와 검증된 OpenRouter 오디오 모델을 지원합니다. 로컬 오디오 추론과 3D 표면 렌더는 미지원이며 OBJ/glTF/GLB의 제한된 와이어프레임만 분석합니다. 검색·태그 필터는 분석 범위를 제한하지 않습니다.</p>
   <label>대상 모드 <select v-model="mode" :disabled="busy"><option value="all">전체</option><option value="unanalyzed">미분석</option><option value="completed">완료 재분석</option><option value="failed">실패 재시도</option><option value="selected">선택 {{ (retrySelection??props.selectedIds).length }}개</option></select></label>
   <label>분석 범위 <select v-model="scope" :disabled="busy"><option value="folder">현재 폴더 (하위 포함)</option><option value="library">현재 라이브러리</option><option value="all">전체 라이브러리</option></select></label>
   <label>모델 <select v-model="model" :disabled="busy"><option value="">모델을 선택하세요</option><option v-for="item in models" :key="item.id" :value="item.id" :disabled="!item.enabled || (inputKind==='audio'&&item.kind!=='external') || !item.inspection?.modalities?.includes(['threeD','animation'].includes(inputKind)?'image':inputKind)">{{ item.modelId }}{{ item.enabled?'':' (비활성)' }}</option></select></label>
   <label>분석 입력 <select v-model="inputKind" :disabled="busy"><option value="image">이미지</option><option value="audio">오디오 (외부 전송 필요)</option><option value="threeD">3D 와이어프레임</option><option value="animation">2D 애니메이션</option><option value="text">텍스트·코드·선언 데이터 (최대 4KB)</option></select></label>
   <p v-if="retryContext">이전 작업 범위 기준: {{ retryContext.library_id??'전체' }} / {{ retryContext.folder_parts.join('/') }}</p>
   <p v-if="error" role="alert">{{ error }}</p>
   <button type="button" :disabled="busy || !model || (mode==='selected' && (retrySelection??props.selectedIds).length>200)" @click="review">대상 확인</button>
   <p v-if="mode==='selected' && (retrySelection??props.selectedIds).length>200">선택 분석은 한 번에 최대 200개입니다. 범위 분석은 최대 1000개입니다.</p>
   <p v-if="preview" role="status">대상 {{ preview.targetCount }}개 · 원본 확인 실패 {{ preview.missingCount }}개</p>
   <p v-if="preview">{{ inputKind==='text'?'UTF-8 텍스트':inputKind==='audio'?'PCM WAV':inputKind==='threeD'?'OBJ/glTF/GLB':inputKind==='animation'?'GIF/APNG':'PNG/JPEG' }} 후보 {{ preview.eligibleCount??preview.targetCount }}개 · 미지원 {{ preview.unsupportedCount??0 }}개 · 크기 초과 {{ preview.overLimitCount??0 }}개. 실제 디코드·권한 검증은 실행 시 다시 수행합니다.</p>
   <p v-if="preview">미지원 중 형식 미확인 {{ preview.unknownFormatCount??0 }}개. 다중 파일 AI 분석은 아직 지원하지 않습니다. 이미지의 분류·역할·스타일은 미확정 제안입니다.</p>
   <p v-if="preview?.snapshot?.analysisContract">분석 계약 {{ preview.snapshot.analysisContract.version }} · 입력 {{ preview.snapshot.analysisContract.inputSchema }} · 출력 {{ preview.snapshot.analysisContract.outputSchema }} · 검토 입력 지문 {{ preview.snapshot.analysisContract.reviewInputFingerprint }}</p>
   <p v-if="preview">비용 상한 추정: {{ preview.estimatedUpperBoundUsd??'미확인' }} USD. 실제 청구와 다를 수 있습니다. 전송: {{ preview.externalTransfer?(inputKind==='text'?'선택 UTF-8 파일 내용 전체(최대 4KB)·고정 프롬프트를 외부 전송':inputKind==='audio'?'선택 PCM WAV 원본 전체(최대 60초)·분석 프롬프트를 외부 공급자로 전송':inputKind==='animation'?'처음 최대 8프레임의 파생 JPEG·고정 프롬프트만 외부 전송':inputKind==='threeD'?'3D의 512px 파생 와이어프레임 JPEG·고정 프롬프트만 외부 전송':'선택 이미지의 최대 512px 파생 JPEG·분석 프롬프트를 외부 공급자로 전송'):'이 PC의 로컬 Ollama만 사용' }}</p>
   <label v-if="preview?.externalTransfer"><input v-model="external" type="checkbox" />이 분석의 외부 전송을 승인합니다.</label>
   <label v-if="preview?.paid"><input v-model="paid" type="checkbox" />표시된 상한 내 유료 사용을 승인합니다.</label>
   <button type="button" class="analysis-start" :disabled="busy || !(preview?.eligibleCount??preview?.targetCount) || (preview?.externalTransfer && !external) || (preview?.paid && !paid)" @click="start">분석 시작</button>
   <p v-if="jobId" role="status">분석 요청 저장됨: {{ jobId }}</p>
   <p v-if="progress" role="status">{{ progress.status }} · {{ progress.processed }}/{{ progress.total }} · 성공 {{ progress.succeeded }} · 실패 {{ progress.failed }} · 취소 {{ progress.canceled }}</p>
   <ul v-if="progress?.errors?.length" aria-label="처음 10개 분석 오류"><li v-for="item in progress.errors" :key="item.assetId">{{ item.assetId }} · {{ item.code }}</li></ul>
   <button type="button" @click="close">닫기</button>
  </section>
 </div>
</template>
