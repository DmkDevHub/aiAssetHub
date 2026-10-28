<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { validCoreHealth, coreErrorMessage } from '../services/coreHealth';

const desktop = isTauri();
const state = ref<'checking' | 'connected' | 'degraded' | 'failed'>('checking');
const busy = ref(false);
const database = ref('');
const version = ref('');
const errorMessage = ref('');
let active = true;
let timer: ReturnType<typeof setInterval> | undefined;

async function check(reconnect = false, background = false) {
  if (!desktop || busy.value) return;
  busy.value = true;
  if (!background) state.value = 'checking';
  try {
    const response = await invoke<unknown>(
      reconnect ? 'core_reconnect' : 'core_health');
    if (!active) return;
    if (!validCoreHealth(response)) throw 'CORE_PROTOCOL_ERROR';
    version.value = response.data.core.version;
    database.value = response.data.database?.status === 'ready' ? 'DB 연결됨'
      : response.data.database?.status === 'error' ? 'DB 연결 오류' : 'DB 미연결';
    state.value = response.data.database.status === 'error' ? 'degraded' : 'connected';
    errorMessage.value = response.data.database.status === 'error' ? coreErrorMessage(response.data.database.error_code) : '';
  } catch (code) {
    if (!active) return;
    state.value = 'failed';
    errorMessage.value = coreErrorMessage(code);
    version.value = database.value = '';
  } finally {
    busy.value = false;
  }
}
onMounted(() => {
  if (!desktop) return;
  void check();
  timer = setInterval(() => {
    if (state.value === 'connected' || state.value === 'degraded') void check(false, true);
  }, 5000);
});
onBeforeUnmount(() => { active = false; if (timer !== undefined) clearInterval(timer); });
</script>

<template>
  <section v-if="desktop" class="core-connection" aria-label="Core 연결">
    <p role="status">{{ state === 'checking' ? 'Core 연결 확인 중' : state !== 'failed' ? `Core 연결됨 · ${version} · ${database}` : 'Core 연결 끊김' }}</p>
    <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
    <button type="button" :disabled="busy" @click="check(state === 'failed' || state === 'degraded')">
      {{ state === 'failed' || state === 'degraded' ? '다시 연결' : '연결 확인' }}
    </button>
  </section>
</template>
