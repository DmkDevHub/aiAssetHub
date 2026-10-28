<script setup lang="ts">
import { computed } from 'vue';
import { isTauri } from '@tauri-apps/api/core';
import { libraries, refreshLibraries, unregisterLibrary } from '../stores/libraries';
import { libraryUi } from '../stores/libraryUi';

const desktop = isTauri();
const selected = computed(() => libraries.roots.find((item) => item.id === libraryUi.selectedFolderId));
</script>

<template>
  <section v-if="desktop" class="library-management" aria-label="등록 폴더 관리">
    <button type="button" class="refresh-libraries" :disabled="libraries.loading || libraries.mutating" @click="refreshLibraries">
      등록 폴더 새로고침
    </button>
    <template v-if="selected">
      <p>{{ selected.name }}</p>
      <button type="button" class="unregister-library" :disabled="libraries.loading || libraries.mutating"
        @click="unregisterLibrary(selected.id)">등록 해제</button>
      <p>등록을 해제해도 원본 파일은 유지됩니다.</p>
    </template>
    <p v-if="libraries.loading" role="status">등록 폴더를 불러오는 중입니다.</p>
    <p v-if="libraries.mutating" role="status">등록 변경을 저장하는 중입니다.</p>
    <p v-if="libraries.notice" role="status">{{ libraries.notice }}</p>
    <p v-if="libraries.error" role="alert">{{ libraries.error }}</p>
  </section>
</template>
