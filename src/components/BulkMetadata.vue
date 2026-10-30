<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {metadata,catalogOptions,type CatalogOption} from '../services/metadata';
const props=defineProps<{assetIds:string[]}>();
type Target={assetId:string;before:Record<string,unknown>;after:Record<string,unknown>;conflicts:string[];changed:boolean};
type Preview={items:Target[];planToken:string;next_cursor:string|null;targetCount:number;changedCount:number;conflictCount:number};
const field=ref('tags'),action=ref('add'),choice=ref(''),label=ref(''),site=ref(''),product=ref(''),role=ref('creator');
const options=ref<CatalogOption[]>([]),preview=ref<Preview>(),rows=ref<Target[]>([]),busy=ref(false),message=ref('');
let generation=0;onBeforeUnmount(()=>generation++);
watch([()=>props.assetIds.join(','),field,action,choice,label,site,product,role],()=>{generation++;preview.value=undefined;rows.value=[];message.value='';});
watch(field,()=>{choice.value='';options.value=[];});
async function loadOptions(){if(busy.value)return;const token=generation;busy.value=true;try{const items=await catalogOptions(field.value==='classification'?'types':field.value);if(token===generation)options.value=items;}catch{if(token===generation)message.value='선택 목록을 불러오지 못했습니다.';}finally{busy.value=false;}}
function request(){let change:unknown;
 if(field.value==='tags')change={add:action.value==='add'?[label.value]:[],remove:action.value==='remove'?[label.value]:[]};
 else if(field.value==='groups')change={add:action.value==='add'?[choice.value]:[],remove:action.value==='remove'?[choice.value]:[]};
 else if(field.value==='creators'){const item={creator_id:choice.value,role:role.value};change={add:action.value==='add'?[item]:[],remove:action.value==='remove'?[item]:[]};}
 else if(field.value==='classification')change={primary:choice.value||null};
 else change={append:[{site:site.value,productName:product.value}]};
 return {asset_ids:[...props.assetIds],changes:{[field.value]:change}};
}
async function review(more=false){if(busy.value||!props.assetIds.length||props.assetIds.length>100)return;const token=generation;busy.value=true;message.value='';try{
 const result=await metadata<Preview>('bulk.preview',{request:request(),after_id:more?preview.value?.next_cursor:null,plan_token:more?preview.value?.planToken:null});if(token!==generation)return;
 preview.value=result;rows.value=more?[...rows.value,...result.items]:result.items;
 }catch{if(token===generation){preview.value=undefined;rows.value=[];message.value='검토 실패: 대상·참조·필드 제한 또는 버전 변경을 확인하세요.';}}finally{busy.value=false;}}
</script>
<template><details class="bulk-metadata"><summary>선택 에셋 일괄 메타데이터</summary><p>최대100개를 검토합니다. 원본 파일과 AI 결과는 변경하지 않습니다.</p>
 <label>변경 항목<select v-model="field" :disabled="busy"><option value="tags">사용자 태그</option><option value="groups">그룹 소속</option><option value="classification">대표 분류</option><option value="creators">제작 주체</option><option value="sources">공개 출처 추가</option></select></label>
 <label v-if="['tags','groups','creators'].includes(field)">동작<select v-model="action" :disabled="busy"><option value="add">추가</option><option value="remove">해제</option></select></label>
 <label v-if="field==='tags'">태그<input v-model="label" maxlength="64" :disabled="busy" /></label>
 <template v-if="['groups','classification','creators'].includes(field)"><button type="button" :disabled="busy" @click="loadOptions">선택 목록 조회</button><label>값<select v-model="choice" :disabled="busy"><option value="">{{field==='classification'?'미분류로 확정':'선택하세요'}}</option><option v-for="item in options" :key="item.id" :value="item.id">{{item.name}}</option></select></label></template>
 <label v-if="field==='creators'">역할<select v-model="role" :disabled="busy"><option value="creator">제작</option><option value="producer">프로듀싱</option><option value="distributor">배포</option></select></label>
 <template v-if="field==='sources'"><label>사이트<input v-model="site" maxlength="128" :disabled="busy" /></label><label>상품명<input v-model="product" maxlength="256" :disabled="busy" /></label><p>공개 출처를 추가하며 기존 URL·구매·라이선스 기록은 보존합니다.</p></template>
 <button type="button" :disabled="busy||!assetIds.length||assetIds.length>100" @click="review()">일괄 변경 검토</button>
 <template v-if="preview"><p>대상 {{preview.targetCount}}개 · 변경 {{preview.changedCount}}개 · 충돌 {{preview.conflictCount}}개</p><ol><li v-for="row in rows" :key="row.assetId"><p>{{row.assetId}} · {{row.conflicts.length?'충돌':'검토 가능'}}</p><p>이전: {{JSON.stringify(row.before)}}</p><p>이후: {{JSON.stringify(row.after)}}</p></li></ol><button v-if="preview.next_cursor" type="button" :disabled="busy" @click="review(true)">다음 변경 검토</button></template><p role="status">{{message}}</p></details></template>
