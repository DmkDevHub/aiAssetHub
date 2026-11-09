<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { isTauri } from '@tauri-apps/api/core';
import { libraries, refreshLibraries, unregisterLibrary } from '../stores/libraries';
import { libraryUi } from '../stores/libraryUi';
import { assets, scanLibrary, refreshAssets } from '../stores/assets';

const desktop = isTauri();
const selectedId = ref(libraryUi.selectedFolderId ?? '');
const selected = computed(() => libraries.roots.find((item) => item.id === selectedId.value));
watch(() => libraries.roots, () => { if (!selected.value) selectedId.value = ''; });
watch(() => libraryUi.selectedFolderId, (id) => {
  if (id && libraries.roots.some(root => root.id === id)) selectedId.value = id;
});
</script>

<template>
  <section v-if="desktop" class="library-management" aria-label="등록 폴더 관리">
    <button type="button" class="refresh-libraries" :disabled="libraries.loading || libraries.mutating" @click="refreshLibraries">
      등록 폴더 새로고침
    </button>
    <button type="button" :disabled="assets.busy" @click="refreshAssets">파일 목록 새로고침</button>
    <label v-if="libraries.roots.length" class="manage-folder-picker">
      관리할 등록 폴더
      <select v-model="selectedId">
        <option value="">폴더 선택</option>
        <option v-for="root in libraries.roots" :key="root.id" :value="root.id">{{ root.name }} — {{ root.path }}</option>
      </select>
    </label>
    <p v-else-if="libraries.loaded && !libraries.loading && !libraries.error">등록된 폴더가 없습니다.</p>
    <template v-if="selected">
      <p class="picked-folder-path">{{ selected.path }}</p>
      <button type="button" class="scan-library" :disabled="assets.busy || libraries.mutating" @click="scanLibrary(selected.id)">파일 스캔</button>
      <button type="button" class="unregister-library" :disabled="assets.busy || libraries.loading || libraries.mutating"
        @click="unregisterLibrary(selected.id)">등록 해제</button>
      <p>등록을 해제해도 원본 파일은 유지됩니다.</p>
    </template>
    <p v-if="assets.notice" role="status">{{ assets.notice }}</p>
    <p v-if="assets.error" role="alert">{{ assets.error }}</p>
    <p v-if="libraries.loading" role="status">등록 폴더를 불러오는 중입니다.</p>
    <p v-if="libraries.mutating" role="status">등록 변경을 저장하는 중입니다.</p>
    <p v-if="libraries.notice" role="status">{{ libraries.notice }}</p>
    <p v-if="libraries.error" role="alert">{{ libraries.error }}</p>
  </section>
</template>
