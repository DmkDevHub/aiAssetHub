<script setup lang="ts">
import LibraryTreePanel from "../components/LibraryTreePanel.vue";
import AssetGallery from "../components/AssetGallery.vue";
import { libraryUi, selectLibraryFolder } from "../stores/libraryUi";
</script>

<template>
  <div class="library-workspace" :style="{ '--library-panel-width': `${libraryUi.panelWidth}px` }">
    <LibraryTreePanel :selected-id="libraryUi.selectedFolderId" @select="selectLibraryFolder" />
    <AssetGallery />
  </div>
</template>
