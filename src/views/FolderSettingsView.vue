<script setup lang="ts">
import { onMounted } from 'vue';
import { isTauri } from '@tauri-apps/api/core';
import FolderSelection from '../components/FolderSelection.vue';
import LibraryManagement from '../components/LibraryManagement.vue';
import { libraries, refreshLibraries } from '../stores/libraries';

const desktop = isTauri();
onMounted(() => { if (!libraries.loaded) void refreshLibraries(); });
</script>

<template>
  <section>
    <h1>등록 폴더</h1>
    <p>에셋을 보관하는 폴더를 등록하고 파일 스캔을 실행할 수 있습니다.</p>
    <template v-if="desktop">
      <section class="settings-card" aria-labelledby="add-folder-title">
        <h2 id="add-folder-title">폴더 추가</h2>
        <FolderSelection />
      </section>
      <LibraryManagement class="settings-card" />
    </template>
    <p v-else>폴더 등록과 스캔은 데스크톱 앱에서 사용할 수 있습니다.</p>
  </section>
</template>
