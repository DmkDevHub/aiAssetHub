<script setup lang="ts">
import { computed, ref, watch } from "vue";
import LibraryTreePanel from "../components/LibraryTreePanel.vue";
import AssetGallery from "../components/AssetGallery.vue";
import AssetDetailsPanel from "../components/AssetDetailsPanel.vue";
import { libraryUi, selectLibraryFolder } from "../stores/libraryUi";
import type { AssetSummary } from "../types/assets";

const props = withDefaults(defineProps<{ items?: readonly AssetSummary[] }>(), { items: () => [] });
const selectedId = ref<string | null>(null);
const selectedAsset = computed(() => props.items.find((item) => item.id === selectedId.value) ?? null);
watch(selectedAsset, (asset) => { if (!asset) selectedId.value = null; });
</script>

<template>
  <div class="library-workspace" :style="{
    '--library-panel-width': `${libraryUi.panelWidth}px`,
    '--details-panel-width': libraryUi.detailsCollapsed ? 'auto' : '280px',
  }">
    <LibraryTreePanel :selected-id="libraryUi.selectedFolderId" @select="selectLibraryFolder" />
    <AssetGallery :items="items" :selected-id="selectedId" @select="selectedId = $event" />
    <AssetDetailsPanel :asset="selectedAsset" />
  </div>
</template>
