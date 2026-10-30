<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {metadata} from '../services/metadata';
import {collectionsChanged} from '../stores/collections';
const props=defineProps<{assetId:string;resultId:string}>();
type Value={primary:string|null;facets:Record<string,string[]>};
type Review={before:Value;after:Value;expectedRevision:number;planToken:string;hasChanges:boolean};
const review=ref<Review>(),approved=ref(false),busy=ref(false),message=ref('');let generation=0;
watch(()=>[props.assetId,props.resultId],()=>{generation++;review.value=undefined;approved.value=false;message.value='';});
onBeforeUnmount(()=>{generation++;});
async function preview(){if(busy.value)return;busy.value=true;message.value='';approved.value=false;const token=generation;try{const result=await metadata<Review>('analysis.review',{asset_id:props.assetId,result_id:props.resultId});if(token===generation)review.value=result;}catch{if(token===generation)message.value='이 제안을 검토하지 못했습니다. 저장된 결과와 사전을 확인하세요.';}finally{busy.value=false;}}
async function apply(){if(busy.value||!approved.value||!review.value?.hasChanges)return;busy.value=true;const token=generation;try{await metadata('analysis.review.apply',{asset_id:props.assetId,result_id:props.resultId,plan_token:review.value.planToken,expected_revision:review.value.expectedRevision,confirmed:true});if(token===generation){review.value=undefined;approved.value=false;message.value='분류 제안을 사용자 값으로 저장했습니다. 분류 탭에서 다시 조회할 수 있습니다.';collectionsChanged();}}catch{if(token===generation){review.value=undefined;approved.value=false;message.value='값이 바뀌었거나 저장에 실패했습니다. 다시 검토하세요.';}}finally{busy.value=false;}}
</script>
<template><section class="analysis-review" aria-label="AI 분류 제안 확정"><button type="button" :disabled="busy" @click="preview">분류 제안 검토</button><template v-if="review"><p>대표 유형: {{review.before.primary??'미분류'}} → {{review.after.primary??'미분류'}}</p><p>역할: {{review.before.facets.role?.join(', ')||'없음'}} → {{review.after.facets.role?.join(', ')||'없음'}}</p><p>스타일: {{review.before.facets.style?.join(', ')||'없음'}} → {{review.after.facets.style?.join(', ')||'없음'}}</p><p v-if="!review.hasChanges">적용할 변경이 없습니다.</p><label><input v-model="approved" type="checkbox" :disabled="busy||!review.hasChanges" />표시된 분류 변경을 사용자 값으로 확정합니다.</label><button type="button" :disabled="busy||!approved||!review.hasChanges" @click="apply">검토한 분류 적용</button></template><p v-if="message" role="status">{{message}}</p></section></template>
