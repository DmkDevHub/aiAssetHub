<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';

const desktop = isTauri();
const state = ref<'checking' | 'connected' | 'failed'>('checking');
const busy = ref(false);
const database = ref('');
const version = ref('');

async function check(reconnect = false) {
  if (!desktop || busy.value) return;
  busy.value = true;
  state.value = 'checking';
  try {
    const response = await invoke<{ ok: boolean; data: { core: { status: string; version: string }; database: { status: string } } }>(
      reconnect ? 'core_reconnect' : 'core_health');
    if (!response.ok || response.data?.core?.status !== 'ready' || typeof response.data.core.version !== 'string') throw new Error();
    version.value = response.data.core.version;
    database.value = response.data.database?.status === 'ready' ? 'DB 연결됨'
      : response.data.database?.status === 'error' ? 'DB 연결 오류' : 'DB 미연결';
    state.value = 'connected';
  } catch {
    state.value = 'failed';
    version.value = database.value = '';
  } finally {
    busy.value = false;
  }
}
onMounted(() => { void check(); });
</script>

<template>
  <section v-if="desktop" class="core-connection" aria-label="Core 연결">
    <p role="status">{{ state === 'checking' ? 'Core 연결 확인 중' : state === 'connected' ? `Core 연결됨 · ${version} · ${database}` : 'Core에 연결할 수 없습니다.' }}</p>
    <button type="button" :disabled="busy" @click="check(state === 'failed')">
      {{ state === 'failed' ? '다시 연결' : '연결 확인' }}
    </button>
  </section>
</template>
