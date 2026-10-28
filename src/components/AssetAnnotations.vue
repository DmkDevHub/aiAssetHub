<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { refreshAssets } from '../stores/assets';
const title = ref(''), description = ref(''), notice = ref('');
const props = defineProps<{assetId: string}>();
const tags = ref<string[]>([]), input = ref(''), error = ref(''), busy = ref(false);
let generation = 0;
onBeforeUnmount(() => { generation++; });
watch(() => props.assetId, async id => {
  const token = ++generation;
  tags.value = []; input.value = ''; title.value = ''; description.value = ''; notice.value = ''; error.value = ''; busy.value = true;
  if (!isTauri()) { busy.value = false; return; }
  try {
    const result = await invoke<{ok:boolean;data:{tags:string[];title?:string;description?:string}}>('asset_annotations', {assetId:id});
    if (token !== generation) return;
    if (!result.ok || !Array.isArray(result.data?.tags)) throw new Error();
    tags.value = result.data.tags; title.value = result.data.title ?? ''; description.value = result.data.description ?? '';
  } catch { if(token === generation) error.value = '사용자 정보를 불러오지 못했습니다.'; }
  finally { if(token === generation) busy.value = false; }
}, {immediate:true});
async function edit(add: string[], remove: string[]) {
  if (busy.value || !isTauri()) return;
  const token = generation;
  busy.value = true; error.value = '';
  try {
    const result = await invoke<{ok:boolean;data:{tags:string[];title?:string;description?:string}}>('edit_asset_tags', {assetId:props.assetId,add,remove});
    if (token !== generation) return;
    if (!result.ok || !Array.isArray(result.data?.tags)) throw new Error();
    tags.value = result.data.tags; input.value = ''; await refreshAssets();
  } catch { if(token === generation) error.value = '태그를 저장하지 못했습니다. 최대 32개, 각 64자까지 입력하세요.'; }
  finally { if(token === generation) busy.value = false; }
}
async function save() {
  if (busy.value || !isTauri()) return;
  const token = generation; busy.value = true; error.value = ''; notice.value = '';
  try {
    const result = await invoke<{ok:boolean}>('save_asset_annotation', {assetId:props.assetId,title:title.value,description:description.value});
    if(token !== generation) return;
    if(!result.ok) throw new Error();
    notice.value = '저장했습니다.'; await refreshAssets();
  } catch { if(token===generation) error.value = '사용자 정보를 저장하지 못했습니다.'; }
  finally { if(token===generation) busy.value = false; }
}
</script>
<template>
  <section aria-label="사용자 태그" class="user-annotations">
    <form class="annotation-form" @submit.prevent="save">
      <label>표시명 <input v-model="title" maxlength="128" :disabled="busy" placeholder="비워 두면 파일명 사용" /></label>
      <label>사용자 설명 <textarea v-model="description" maxlength="1024" :disabled="busy" /></label>
      <button :disabled="busy">정보 저장</button>
      <p v-if="notice" role="status">{{ notice }}</p>
    </form>
    <h3>사용자 태그</h3>
    <ul><li v-for="tag in tags" :key="tag">{{ tag }} <button type="button" :disabled="busy" :aria-label="`${tag} 태그 삭제`" @click="edit([], [tag])">삭제</button></li></ul>
    <form class="tag-form" @submit.prevent="input.trim() && edit([input.trim()], [])">
      <label>새 태그 <input v-model="input" maxlength="64" :disabled="busy" /></label>
      <button :disabled="busy || !input.trim()">추가</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
