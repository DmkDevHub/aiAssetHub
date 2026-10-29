<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { invoke,isTauri } from '@tauri-apps/api/core';
type Entry={id:string;host:string;hostFingerprint:string|null;tool:string;outcome:string;createdAt:string;requestId:string|null;targetIds:string[];targetCount:number;errorCode:string|null;durationMs:number};
type Connection={brokerReady:boolean;transport:string;readOnly:boolean;configuration:{command:string;args:string[];cwd:string}};
const connection=ref<Connection|null>(null),items=ref<Entry[]>([]),cursor=ref<string|null>(null),busy=ref(false),error=ref('');
let alive=true;onBeforeUnmount(()=>{alive=false;});
async function load(more=false){
 if(busy.value || (more && !cursor.value))return;
 if(!isTauri()){error.value='데스크톱 앱에서 MCP 정보를 조회할 수 있습니다.';return;}
 busy.value=true;error.value='';
 try{
  if(!more){const r=await invoke<{ok:boolean;data:Connection}>('mcp_connection');if(!alive)return;if(!r.ok)throw new Error();connection.value=r.data;}
  const r=await invoke<{ok:boolean;data:{items:Entry[];next_cursor:string|null}}>('mcp_audit',{afterId:more?cursor.value:null});
  if(!alive)return;if(!r.ok || !Array.isArray(r.data?.items))throw new Error();
  items.value=more?[...items.value,...r.data.items]:r.data.items;cursor.value=r.data.next_cursor;
 }catch{if(alive)error.value='MCP 정보를 불러오지 못했습니다. 다시 조회해 주세요.';}
 finally{if(alive)busy.value=false;}
}
onMounted(()=>{void load();});
</script>
<template>
 <section class="mcp-settings" aria-labelledby="mcp-title">
  <h1 id="mcp-title">MCP 연결·감사 로그</h1>
  <p>외부 도구에 에셋 조회 기능 5개를 제공합니다. 조회로 분석·임베딩을 실행하지 않습니다.</p>
  <button type="button" :disabled="busy" @click="load(false)">연결 정보·로그 새로 조회</button>
  <p v-if="connection" role="status">Core 조회 채널: {{ connection.brokerReady?'준비됨':'연결 불가' }} · {{ connection.transport }} · 읽기 전용</p>
  <div v-if="connection"><h2>Host의 stdio 실행 정보</h2><p>Host 설정의 command·args·cwd에 아래 값을 사용합니다. 앱을 켜 둔 상태에서 연결하세요.</p>
   <pre class="mcp-configuration">{{ JSON.stringify(connection.configuration,null,2) }}</pre>
  </div>
  <p v-if="error" role="alert">{{ error }}</p>
  <h2>최근 호출</h2><p>Host 이름은 자기 신고값입니다. 검색어·파일 경로·인증 비밀값은 기록하지 않습니다.</p>
  <p v-if="!busy && !items.length && !error">기록된 MCP 호출이 없습니다.</p>
  <ol class="mcp-audit"><li v-for="entry in items" :key="entry.id">
   <strong>{{ entry.tool }}</strong> · {{ entry.outcome }} · {{ entry.createdAt }} · {{ entry.durationMs }}ms
   <p>Host {{ entry.host }}<span v-if="entry.hostFingerprint"> ({{ entry.hostFingerprint }})</span> · 요청 {{ entry.requestId ?? '확인 불가' }}</p>
   <p v-if="entry.errorCode">오류 {{ entry.errorCode }}</p>
   <p>대상 {{ entry.targetCount }}개<span v-if="entry.targetCount>5"> (처음 5개 표시)</span>: {{ entry.targetIds.join(', ') || '없음' }}</p>
  </li></ol>
  <button v-if="cursor" type="button" :disabled="busy" @click="load(true)">이전 호출 더 보기</button>
 </section>
</template>
<style scoped>
.mcp-settings{padding:1.5rem;max-width:70rem;margin:auto}.mcp-configuration{white-space:pre-wrap;overflow-wrap:anywhere;padding:1rem;background:var(--surface)}.mcp-audit{padding-left:1.5rem}.mcp-audit li{margin-block:1rem;overflow-wrap:anywhere}
</style>
