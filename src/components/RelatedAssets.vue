<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {metadata} from '../services/metadata';
const props=defineProps<{assetId:string}>();
const emit=defineEmits<{choose:[candidate:{id:string;name:string}]}>();
type Candidate={id:string;name:string;score:number;confirmed:boolean;reasons:{kind:string;count?:number}[]};
type Result={items:Candidate[];vectorStatus:string;inferenceCalled:boolean;relationshipCreated:boolean};
const mode=ref('metadata'),limit=ref(10),result=ref<Result>(),busy=ref(false),error=ref('');let epoch=0;
onBeforeUnmount(()=>epoch++);
watch(()=>props.assetId,()=>{epoch++;result.value=undefined;busy.value=false;error.value='';});
const labels:Record<string,string>={shared_tag:'같은 사용자 태그',shared_group:'같은 그룹',shared_package:'같은 패키지',shared_creator:'같은 제작 주체',shared_type:'같은 분류',shared_style:'같은 스타일',shared_role:'같은 역할',shared_genre:'같은 장르',shared_view:'같은 시점',shared_dimension:'같은 차원',shared_engine:'같은 엔진 선언',stored_vector:'저장된 벡터 유사도'};
async function load(){if(busy.value)return;const token=++epoch;busy.value=true;error.value='';result.value=undefined;
 try{const r=await metadata<Result>('catalog.related',{asset_id:props.assetId,mode:mode.value,criteria:{},limit:limit.value});if(token!==epoch)return;
 if(!Array.isArray(r.items)||r.items.length>20||new Set(r.items.map(c=>c.id)).size!==r.items.length||r.items.some(c=>typeof c.id!=='string'||c.id===props.assetId||typeof c.name!=='string'||!Number.isFinite(c.score)||!Array.isArray(c.reasons)||c.confirmed!==false)||r.inferenceCalled!==false||r.relationshipCreated!==false)throw new Error();result.value=r;
 }catch{if(token===epoch)error.value='추천을 조회하지 못했습니다. 현재 등록 상태를 확인하거나 추천 개수를 줄여 다시 조회하세요.';}finally{if(token===epoch)busy.value=false;}}
</script>
<template><section class="related-recommendations" aria-label="관련 에셋 추천"><h4>관련 에셋 추천</h4>
 <p>저장된 공개 메타데이터와 유효한 벡터를 비교합니다. 추천은 미확정이며 초안에 추가한 뒤 관계를 저장해야 합니다.</p>
 <label>추천 기준<select v-model="mode" :disabled="busy" @change="result=undefined"><option value="metadata">메타데이터</option><option value="stored_vectors">저장 벡터</option><option value="hybrid">메타데이터+저장 벡터</option></select></label><label>추천 개수<input v-model.number="limit" type="number" min="1" max="20" :disabled="busy" /></label><button type="button" :disabled="busy" @click="load">관련 추천 조회</button>
 <p v-if="busy" role="status">저장 데이터 비교 중…</p><p v-if="error" role="alert">{{error}}</p><p v-if="result?.vectorStatus==='source-vector-unavailable'">현재 에셋의 유효한 저장 벡터가 없습니다. 벡터 생성은 임베딩 설정에서 별도로 실행하세요.</p>
 <ul><li v-for="row in result?.items??[]" :key="row.id">{{row.name}} · 미확정 추천 · 점수 {{row.score.toFixed(4)}}<span v-for="reason in row.reasons" :key="reason.kind"> · {{labels[reason.kind]||'같은 공개 속성'}}{{reason.count?` ${reason.count}개`:''}}</span><button type="button" @click="emit('choose',row)">관련 관계 초안에 추가</button></li></ul>
 <p v-if="result&&!result.items.length">현재 조건에서 추천할 준비된 에셋이 없습니다.</p><p>점수는 확률이나 권리·호환성 판정이 아닙니다.</p>
</section></template>
