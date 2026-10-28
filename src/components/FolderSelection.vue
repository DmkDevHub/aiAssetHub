<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { folderDraft, setPickedFolderPath } from '../stores/folderDraft';
import { libraries, registerLibrary } from '../stores/libraries';

const desktop = isTauri();
const busy = ref(false);
const status = ref('');
const error = ref('');
let active = true;
const messages: Record<string, string> = {
  FOLDER_PICKER_BUSY: '폴더 선택 창이 이미 열려 있습니다.',
  FOLDER_LOCAL_ONLY: '이 PC의 로컬 드라이브 폴더를 선택하세요. 네트워크 위치는 사용할 수 없습니다.',
  FOLDER_ROOT_NOT_ALLOWED: '드라이브 전체 대신 에셋이 있는 하위 폴더를 선택하세요.',
  FOLDER_UNAVAILABLE: '폴더를 확인할 수 없습니다. 위치와 접근 권한을 확인하세요.',
};

async function pickFolder() {
  if (!desktop || busy.value) return;
  busy.value = true;
  status.value = error.value = '';
  try {
    const result = await invoke<{ path: string } | null>('select_library_folder');
    if (!active) return;
    if (result === null) { status.value = '폴더 선택을 취소했습니다.'; return; }
    if (!result || typeof result.path !== 'string' || !/^[A-Za-z]:[\\/]/.test(result.path)
      || result.path.includes('\0') || result.path.length > 32767) throw 'FOLDER_PICK_FAILED';
    setPickedFolderPath(result.path);
    status.value = '폴더를 선택했습니다.';
  } catch (code) {
    if (!active) return;
    error.value = typeof code === 'string' && Object.hasOwn(messages, code) ? messages[code]!
      : '폴더 선택 창을 열지 못했습니다. 다시 시도하세요.';
  } finally { busy.value = false; }
}

function clearSelection() {
  if (busy.value) return;
  setPickedFolderPath(null);
  status.value = '폴더 선택을 지웠습니다.';
  error.value = '';
}
onBeforeUnmount(() => { active = false; });
</script>

<template>
  <section v-if="desktop" class="folder-selection" aria-label="라이브러리 폴더 선택">
    <button type="button" class="pick-folder" :disabled="busy" @click="pickFolder">
      {{ busy ? '폴더 선택 중…' : '폴더 선택' }}
    </button>
    <template v-if="folderDraft.path">
      <p class="picked-folder-label">선택한 폴더</p>
      <p class="picked-folder-path">{{ folderDraft.path }}</p>
      <button type="button" class="register-library" :disabled="busy || !libraries.loaded || libraries.loading || libraries.mutating"
        @click="registerLibrary(folderDraft.path)">선택 폴더 등록</button>
      <button type="button" class="clear-folder-selection" :disabled="busy" @click="clearSelection">선택 지우기</button>
    </template>
    <p v-if="status" role="status">{{ status }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
