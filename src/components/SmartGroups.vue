<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue';
import {metadata,type JsonObject} from '../services/metadata';
import {smartUi} from '../stores/smartGroups';
const props=defineProps<{query:string;criteria:JsonObject}>();
type Definition={schema:string;query:string;criteria:JsonObject;include_groups:string[]};
type Row={id:string;name:string;revision:number};
type Detail=Row&{description:string;definition:Definition};
const rows=ref<Row[]>([]),editing=ref<string|null>(null),name=ref(''),description=ref(''),revision=ref(0),refs=ref<string[]>([]);
const definition=ref<Definition>({schema:'smart-group.v1',query:'',criteria:{},include_groups:[]});
const busy=ref(false),error=ref(''),notice=ref(''),conflict=ref(false);let epoch=0;onBeforeUnmount(()=>epoch++);
async function load(){let cursor:string|null=null;const token=epoch;const list:Row[]=[];
 do{const page:{items:Row[];next_cursor:string|null}=await metadata('catalog.smart.list',{after_id:cursor});if(token!==epoch)return;list.push(...page.items);if(list.length>32)throw new Error();cursor=page.next_cursor;}while(cursor);rows.value=list;}
function capture(){definition.value={schema:'smart-group.v1',query:props.query,criteria:JSON.parse(JSON.stringify(props.criteria)),include_groups:[]};notice.value='현재 검색 조건을 초안에 담았습니다.';}
function fresh(){epoch++;editing.value=null;revision.value=0;name.value='';description.value='';refs.value=[];conflict.value=false;error.value='';capture();}
async function edit(id:string){const token=++epoch;busy.value=true;error.value='';try{const r=await metadata<Detail>('catalog.smart.get',{group_id:id});if(token!==epoch)return;editing.value=id;name.value=r.name;description.value=r.description;definition.value=r.definition;refs.value=[...r.definition.include_groups];revision.value=r.revision;conflict.value=false;}catch{if(token===epoch)error.value='조건을 불러오지 못했습니다.';}finally{if(token===epoch)busy.value=false;}}
async function save(){if(busy.value||conflict.value)return;const token=epoch;busy.value=true;error.value='';try{const r=await metadata<Detail>('catalog.smart.save',{group_id:editing.value,name:name.value,description:description.value,definition:{...definition.value,include_groups:[...refs.value]},expected_revision:revision.value});if(token!==epoch)return;editing.value=r.id;revision.value=r.revision;definition.value=r.definition;smartUi.revision++;notice.value='스마트 그룹 조건을 저장했습니다.';await load();}catch(e){if(token===epoch){conflict.value=e instanceof Error&&e.message==='METADATA_CONFLICT';error.value='저장하지 못했습니다. 참조·순환 또는 다른 변경을 확인하고 다시 불러오세요.';}}finally{if(token===epoch)busy.value=false;}}
async function remove(){if(!editing.value||busy.value||conflict.value)return;const token=epoch,id=editing.value;busy.value=true;error.value='';try{await metadata('catalog.smart.delete',{group_id:id,expected_revision:revision.value});if(token!==epoch)return;if(smartUi.groupId===id)smartUi.groupId=null;smartUi.revision++;fresh();await load();notice.value='저장 조건을 삭제했습니다.';}catch{if(token===epoch)error.value='다른 스마트 그룹이 참조하거나 변경되어 삭제하지 못했습니다.';}finally{busy.value=false;}}
async function refresh(){busy.value=true;error.value='';try{await load();}catch{error.value='스마트 그룹 목록을 불러오지 못했습니다.';}finally{busy.value=false;}}
onMounted(capture);
</script>
<template><details class="smart-groups"><summary>스마트 그룹</summary><section aria-label="스마트 그룹 관리">
 <p>현재 인덱스에서 저장 조건을 동적으로 평가합니다.</p><button type="button" :disabled="busy" @click="refresh">스마트 그룹 불러오기</button><button type="button" :disabled="busy" @click="smartUi.groupId=null">스마트 그룹 필터 해제</button>
 <ul><li v-for="row in rows" :key="row.id">{{row.name}} <button type="button" :disabled="busy" :aria-pressed="smartUi.groupId===row.id" @click="smartUi.groupId=row.id">이 조건으로 탐색</button><button type="button" :disabled="busy" @click="edit(row.id)">조건 편집</button></li></ul>
 <button type="button" :disabled="busy" @click="fresh">새 스마트 그룹</button>
 <form @submit.prevent="save"><fieldset :disabled="busy"><label>스마트 그룹 이름<input v-model="name" maxlength="128" required /></label><label>스마트 그룹 설명<input v-model="description" maxlength="512" /></label>
 <p>저장할 검색어: {{definition.query||'전체'}} · 조건 {{Object.keys(definition.criteria).length}}개</p><button type="button" @click="capture">현재 검색 조건으로 교체</button>
 <label>함께 만족할 스마트 그룹<select v-model="refs" multiple><option v-for="row in rows.filter(r=>r.id!==editing)" :key="row.id" :value="row.id">{{row.name}}</option></select></label>
 <button :disabled="conflict">스마트 그룹 저장</button><button type="button" @click="editing?edit(editing):fresh()">스마트 그룹 변경 취소</button></fieldset></form>
 <button v-if="editing" type="button" :disabled="busy||conflict" @click="remove">스마트 그룹 삭제</button><p v-if="error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
</section></details></template>
