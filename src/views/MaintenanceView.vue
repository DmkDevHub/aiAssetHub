<script setup lang="ts">
import {onBeforeUnmount,ref} from 'vue';
import {metadata} from '../services/metadata';
type Backup={id:string;manifestValid:boolean;createdAt?:string;sizeBytes?:number};
type Info={command:string;argsPrefix:string[];dataDirectory:string;environment:string|null};
const items=ref<Backup[]>([]),cursor=ref<string|null>(null),info=ref<Info|null>(null),chosen=ref(''),busy=ref(false),error=ref(''),notice=ref('');
let alive=true;onBeforeUnmount(()=>{alive=false;});
async function list(more=false){const r=await metadata<{items:Backup[];next_cursor:string|null}>('maintenance.list',{after_id:more?cursor.value:null});if(alive){items.value=more?[...items.value,...r.items]:r.items;cursor.value=r.next_cursor;}}
async function act(action:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await action();}catch{if(alive)error.value='백업 정보를 처리하지 못했습니다. 경로·권한·데이터 상태를 확인하세요.';}finally{if(alive)busy.value=false;}}
async function create(){await metadata('maintenance.backup',{confirmed:true});if(alive)notice.value='DB 백업을 생성했습니다. 원본 에셋과 OS 자격 증명은 백업에 포함되지 않습니다.';await list();}
async function load(){const r=await metadata<Info>('maintenance.info',{});if(alive)info.value=r;await list();}
function command(){if(!info.value||!chosen.value)return '';const i=info.value;return ['&',...[i.command,...i.argsPrefix,'--maintenance','restore','--data-dir',i.dataDirectory,'--environment',i.environment??'','--backup-id',chosen.value,'--confirmed'].map(s=>"'"+s.replaceAll("'","''")+"'")].join(' ');}
</script>
<template><section class="maintenance"><h1>DB 백업·복구</h1><p>백업에는 연락처·구매·원본 경로 등 개인 메타데이터가 포함될 수 있습니다. 현재 사용자 전용 위치에 저장합니다. 원본 파일·썸네일·OS에 저장한 API 키는 별도로 보존하세요.</p>
 <button :disabled="busy" @click="act(create)">현재 DB 백업 생성</button><button :disabled="busy" @click="act(load)">백업 목록·복구 안내 조회</button>
 <p v-if="notice" role="status">{{notice}}</p><p v-if="error" role="alert">{{error}}</p><ul><li v-for="item in items" :key="item.id"><label><input v-model="chosen" type="radio" :value="item.id" :disabled="busy||!item.manifestValid">{{item.id}} · {{item.createdAt}} · {{item.sizeBytes}} bytes · {{item.manifestValid?'검토 가능':'백업 메타데이터 오류'}}</label></li></ul>
 <button v-if="cursor" :disabled="busy" @click="act(()=>list(true))">이전 백업 더 보기</button>
 <div v-if="chosen&&info"><h2>앱 종료 후 명시 복구</h2><p>복구 시점 이후 DB 변경은 이전 상태로 돌아갑니다. 앱을 완전히 종료하고 PowerShell에서 아래 명령을 실행하세요. 실행 중이면 거부합니다. 기존 DB/WAL은 별도 pre-restore 폴더에 보존하며 AI 작업은 재개하지 않습니다.</p><p v-if="info.argsPrefix.length">개발 환경에서는 python-core 폴더와 런타임 의존성을 준비한 터미널에서 실행하세요.</p><pre>{{command()}}</pre></div>
 </section></template>
<style scoped>.maintenance{padding:1.5rem;max-width:70rem;margin:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}button{margin:.4rem}</style>
