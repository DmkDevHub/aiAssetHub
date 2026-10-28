<script setup lang="ts">
import LibraryTreePanel from "../components/LibraryTreePanel.vue";
import { libraryUi, selectLibraryFolder } from "../stores/libraryUi";
</script>

<template>
  <div class="library-workspace" :style="{ '--library-panel-width': `${libraryUi.panelWidth}px` }">
    <LibraryTreePanel :selected-id="libraryUi.selectedFolderId" @select="selectLibraryFolder" />
    <section class="page" aria-labelledby="library-title">
      <h1 id="library-title">라이브러리</h1>
      <p class="page-description">로컬 에셋 작업 공간</p>
    </section>
  </div>
</template>
