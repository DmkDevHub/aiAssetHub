<script setup lang="ts">
import { ref, watch } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { refreshAssets } from '../stores/assets';
const props = defineProps<{assetIds: string[]}>();
const label = ref(''), action = ref('add'), busy = ref(false), message = ref('');
watch(() => props.assetIds.join(','), () => { message.value = ''; });
async function submit() {
  if(busy.value || !label.value.trim() || !isTauri()) return;
  const ids = [...props.assetIds];
  busy.value = true; message.value = '';
  try {
    const result = await invoke<{ok:boolean;data:{updated:number}}>('batch_asset_tags', {
      assetIds:ids,add:action.value==='add'?[label.value.trim()]:[],remove:action.value==='remove'?[label.value.trim()]:[]});
    if(!result.ok || result.data?.updated!==ids.length) throw new Error();
    await refreshAssets(); message.value = `${ids.length}개 에셋의 사용자 태그를 저장했습니다.`;
  } catch { message.value = '일괄 저장하지 못했습니다. 연결과 태그 제한을 확인하세요.'; }
  finally { busy.value = false; }
}
</script>
<template>
  <form class="bulk-tags" aria-label="선택 에셋 태그 편집" @submit.prevent="submit">
    <label>일괄 태그 <input v-model="label" maxlength="64" :disabled="busy" /></label>
    <select v-model="action" aria-label="일괄 태그 동작" :disabled="busy"><option value="add">추가</option><option value="remove">삭제</option></select>
    <button :disabled="busy || !label.trim() || assetIds.length>100">{{ assetIds.length }}개에 적용</button>
    <p v-if="assetIds.length>100">한 번에 최대 100개를 선택하세요.</p>
    <p v-if="message" role="status">{{ message }}</p>
  </form>
</template>
