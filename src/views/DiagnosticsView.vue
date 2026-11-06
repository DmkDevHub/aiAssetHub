<script setup lang="ts">
import {onBeforeUnmount,ref,watch} from 'vue';
import {metadata} from '../services/metadata';
const kind=ref('analysis'),items=ref<Record<string,unknown>[]>([]),cursor=ref<string|null>(null),budget=ref<unknown>(null),busy=ref(false),error=ref('');
let epoch=0,alive=true;onBeforeUnmount(()=>{alive=false;epoch++;});watch(kind,()=>{epoch++;items.value=[];cursor.value=null;busy.value=false;error.value='';});
async function load(more=false){if(busy.value)return;const generation=++epoch;busy.value=true;error.value='';try{
 const r=await metadata<{items:Record<string,unknown>[];next_cursor:string|null}>('diagnostics.read',{kind:kind.value,after_id:more?cursor.value:null});
 if(!alive||epoch!==generation)return;items.value=more?[...items.value,...r.items]:r.items;cursor.value=r.next_cursor;
 }catch{if(alive&&epoch===generation)error.value='진단 기록을 불러오지 못했습니다.';}finally{if(alive&&epoch===generation)busy.value=false;}}
async function costs(){if(busy.value)return;busy.value=true;error.value='';try{const r=await metadata('diagnostics.budget',{});if(alive)budget.value=r;}catch{if(alive)error.value='비용 감사 정보를 불러오지 못했습니다.';}finally{if(alive)busy.value=false;}}
</script>
<template><section class="diagnostics"><h1>진단·사용량·비용 감사</h1><p>원본·API 키·분석 원문을 포함하지 않는 작업 기록입니다. 조회로 AI를 실행하지 않습니다.</p>
 <label>기록 종류 <select v-model="kind"><option value="analysis">분석 실행</option><option value="unity">Unity 작업</option><option value="audit">호출 감사</option></select></label>
 <button :disabled="busy" @click="load()">작업 기록 조회</button><ol><li v-for="item in items" :key="String(item.id)"><pre>{{JSON.stringify(item,null,2)}}</pre></li></ol>
 <button v-if="cursor" :disabled="busy" @click="load(true)">이전 기록 더 보기</button>
 <h2>비용 예약·공급자 보고 사용량</h2><p>예약 상한은 청구액이 아닙니다. 공급자 보고 비용이 없으면 미확인으로 유지합니다. 실제 청구는 공급자 명세를 확인하세요.</p><button :disabled="busy" @click="costs">비용 예약 조회</button><pre v-if="budget">{{JSON.stringify(budget,null,2)}}</pre><p v-if="error" role="alert">{{error}}</p></section></template>
<style scoped>.diagnostics{padding:1.5rem;max-width:70rem;margin:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}button{margin:.4rem}</style>
