<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
const props = withDefaults(defineProps<{id:string;kind:string;exists?:boolean}>(),{exists:undefined});
const element = ref<HTMLElement>();
const url = ref('');
const status = ref('');
let active = true;
let observer: IntersectionObserver | undefined;
async function load() {
  observer?.disconnect();
  try {
    const response = await invoke<{ok:boolean;data:{status:string;url?:string}}>('asset_thumbnail',{assetId:props.id});
    if (!active) return;
    if (!response.ok) throw new Error();
    status.value = response.data.status;
    if (response.data.status === 'ready' && /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(response.data.url ?? '')) url.value = response.data.url!;
  } catch { if (active) status.value='unavailable'; }
}
onMounted(() => {
  if (!isTauri() || props.exists===false || !['PNG','JPG','JPEG'].includes(props.kind) || typeof IntersectionObserver === 'undefined') return;
  observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) void load(); });
  if (element.value) observer.observe(element.value);
});
onBeforeUnmount(() => { active=false; observer?.disconnect(); });
</script>
<template><div ref="element" class="asset-format-mark"><img v-if="url && exists!==false" :src="url" alt="" loading="lazy" style="max-width:100%;max-height:120px" /><span v-else>{{ exists===false || status==='missing' ? '파일 없음' : status==='unavailable' ? '미리보기 불가' : status==='too_large' ? '이미지 크기 제한' : status==='unsupported' || !['PNG','JPG','JPEG'].includes(kind) ? `미리보기 미지원 · ${kind}` : kind }}</span></div></template>
