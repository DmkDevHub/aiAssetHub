<script setup lang="ts">
import { ref, watch } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
const props = defineProps<{assetId: string}>();
const tags = ref<string[]>([]), input = ref(''), error = ref(''), busy = ref(false);
let generation = 0;
watch(() => props.assetId, async id => {
  const token = ++generation;
  tags.value = []; input.value = ''; error.value = ''; busy.value = true;
  if (!isTauri()) { busy.value = false; return; }
  try {
    const result = await invoke<{ok:boolean;data:{tags:string[]}}>('asset_annotations', {assetId:id});
    if (token !== generation) return;
    if (!result.ok || !Array.isArray(result.data?.tags)) throw new Error();
    tags.value = result.data.tags;
  } catch { if(token === generation) error.value = '사용자 정보를 불러오지 못했습니다.'; }
  finally { if(token === generation) busy.value = false; }
}, {immediate:true});
async function edit(add: string[], remove: string[]) {
  if (busy.value || !isTauri()) return;
  const token = generation;
  busy.value = true; error.value = '';
  try {
    const result = await invoke<{ok:boolean;data:{tags:string[]}}>('edit_asset_tags', {assetId:props.assetId,add,remove});
    if (token !== generation) return;
    if (!result.ok || !Array.isArray(result.data?.tags)) throw new Error();
    tags.value = result.data.tags; input.value = '';
  } catch { if(token === generation) error.value = '태그를 저장하지 못했습니다. 최대 32개, 각 64자까지 입력하세요.'; }
  finally { if(token === generation) busy.value = false; }
}
</script>
<template>
  <section aria-label="사용자 태그" class="user-annotations">
    <h3>사용자 태그</h3>
    <ul><li v-for="tag in tags" :key="tag">{{ tag }} <button type="button" :disabled="busy" :aria-label="`${tag} 태그 삭제`" @click="edit([], [tag])">삭제</button></li></ul>
    <form @submit.prevent="input.trim() && edit([input.trim()], [])">
      <label>새 태그 <input v-model="input" maxlength="64" :disabled="busy" /></label>
      <button :disabled="busy || !input.trim()">추가</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
