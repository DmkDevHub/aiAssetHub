<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { refreshAssets } from '../stores/assets';
const title = ref(''), description = ref(''), notice = ref('');
const tagsRevision=ref(0);
const aliases = ref(''), originalName = ref(''), revision = ref(0), conflict = ref(false);
const props = defineProps<{assetId: string; userTags?: readonly string[]}>();
const tags = ref<string[]>([]), input = ref(''), error = ref(''), busy = ref(false), loaded = ref(false);
let generation = 0;
onBeforeUnmount(() => { generation++; });
async function load(id: string) {
  const token = ++generation; loaded.value = false;
  tags.value = []; input.value = ''; title.value = ''; description.value = ''; notice.value = ''; error.value = ''; busy.value = true;
  aliases.value = ''; originalName.value = ''; revision.value = 0; conflict.value = false;
  if (!isTauri()) { busy.value = false; return; }
  try {
    const result = await invoke<{ok:boolean;data:{tags:string[];title?:string;description?:string;aliases?:string[];originalName?:string;revision?:number;tagsRevision?:number}}>('asset_annotations', {assetId:id});
    if (token !== generation) return;
    if (!result.ok || !Array.isArray(result.data?.tags)) throw new Error();
    loaded.value = true; tags.value = result.data.tags; title.value = result.data.title ?? ''; description.value = result.data.description ?? '';
    aliases.value = (result.data.aliases ?? []).join('\n'); originalName.value = result.data.originalName ?? '';
    revision.value = result.data.revision ?? 0; tagsRevision.value=result.data.tagsRevision ?? 0;
  } catch { if(token === generation) error.value = '사용자 정보를 불러오지 못했습니다.'; }
  finally { if(token === generation) busy.value = false; }
}
watch(() => props.assetId, load, {immediate:true});
watch(() => props.userTags, value => { if(value) tags.value = [...value]; });
async function edit(add: string[], remove: string[]) {
  if (busy.value || !loaded.value || conflict.value || !isTauri()) return;
  const token = generation;
  busy.value = true; error.value = '';
  try {
    const result = await invoke<{ok:boolean;data:{tags:string[];tagsRevision?:number};error?:{code:string}}>('edit_asset_tags', {assetId:props.assetId,add,remove,expectedRevision:tagsRevision.value});
    if (token !== generation) return;
    if(result.error?.code==='METADATA_CONFLICT'){conflict.value=true;error.value='다른 태그 변경이 저장되었습니다. 초안을 확인한 후 다시 불러오세요.';return;}
    if (!result.ok || !Array.isArray(result.data?.tags)) throw new Error();
    tagsRevision.value=result.data.tagsRevision ?? tagsRevision.value;
    tags.value = result.data.tags; input.value = ''; await refreshAssets();
  } catch { if(token === generation) error.value = '태그를 저장하지 못했습니다. 최대 32개·합계 512자, 각 64자까지 입력하세요.'; }
  finally { if(token === generation) busy.value = false; }
}
async function save() {
  if (busy.value || !loaded.value || conflict.value || !isTauri()) return;
  const token = generation; busy.value = true; error.value = ''; notice.value = '';
  try {
    const result = await invoke<{ok:boolean;data?:{revision:number;aliases:string[]};error?:{code:string}}>('save_asset_annotation', {
      assetId:props.assetId,title:title.value,description:description.value,
      aliases:aliases.value.split('\n').map(value => value.trim()).filter(Boolean),expectedRevision:revision.value,
    });
    if(token !== generation) return;
    if(result.error?.code === 'METADATA_CONFLICT') {
      conflict.value = true; error.value = '다른 변경이 저장되었습니다. 초안을 확인한 후 다시 불러오세요.'; return;
    }
    if(!result.ok) throw new Error();
    revision.value = result.data?.revision ?? revision.value;
    if (Array.isArray(result.data?.aliases)) aliases.value = result.data.aliases.join('\n');
    notice.value = '저장했습니다.'; await refreshAssets();
  } catch { if(token===generation) error.value = '사용자 정보를 저장하지 못했습니다.'; }
  finally { if(token===generation) busy.value = false; }
}
</script>
<template>
  <section aria-label="사용자 수정 정보와 태그" class="user-annotations">
    <h3>사용자 수정 정보</h3>
    <p>사용자가 저장한 표시명·별칭·설명·태그입니다. AI 결과와 별도로 보존됩니다. 실제 파일명은 변경하지 않습니다.</p>
    <p class="original-name">원본 이름: {{ originalName || '미확인' }}</p>
    <form class="annotation-form" @submit.prevent="save">
      <label>표시명 <input v-model="title" maxlength="128" :disabled="busy || !loaded" placeholder="비워 두면 파일명 사용" /></label>
      <label>사용자 설명 <textarea v-model="description" maxlength="1024" :disabled="busy || !loaded" /></label>
      <label>별칭 (한 줄에 하나) <textarea v-model="aliases" class="alias-input" maxlength="1039" :disabled="busy || !loaded" /></label>
      <p>별칭은 최대 16개·각 64자·합계 512자입니다.</p>
      <button :disabled="busy || !loaded || conflict">정보 저장</button>
      <button v-if="conflict" type="button" @click="load(assetId)">초안을 버리고 다시 불러오기</button>
      <p v-if="notice" role="status">{{ notice }}</p>
    </form>
    <button v-if="!loaded && !busy" type="button" @click="load(assetId)">사용자 정보 다시 불러오기</button>
    <h3>사용자 태그</h3>
    <ul><li v-for="tag in tags" :key="tag">{{ tag }} <button type="button" :disabled="busy || !loaded || conflict" :aria-label="`${tag} 태그 삭제`" @click="edit([], [tag])">삭제</button></li></ul>
    <form class="tag-form" @submit.prevent="input.trim() && edit([input.trim()], [])">
      <label>새 태그 <input v-model="input" maxlength="64" :disabled="busy || !loaded" /></label>
      <button :disabled="busy || !loaded || conflict || !input.trim()">추가</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
