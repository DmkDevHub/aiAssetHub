<script setup lang="ts">
import { libraryUi, setGalleryViewMode } from "../stores/libraryUi";
import type { AssetSummary } from "../types/assets";
import { executeUiCommand } from "../stores/operations";
import type { GalleryViewMode } from "../stores/libraryUi";
import AssetThumbnail from './AssetThumbnail.vue';

withDefaults(defineProps<{ items?: readonly AssetSummary[]; selectedId?: string | null }>(), {
  items: () => [], selectedId: null,
});
defineEmits<{ select: [id: string] }>();

function changeView(mode: GalleryViewMode) {
  if (libraryUi.galleryViewMode === mode) return;
  return executeUiCommand('gallery.view', () => setGalleryViewMode(mode));
}

function moveAssetFocus(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const buttons = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('.asset-select')];
  const index = buttons.indexOf(event.target as HTMLElement);
  if (index < 0) return;
  let target: number;
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') target = Math.min(index + 1, buttons.length - 1);
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') target = Math.max(index - 1, 0);
  else if (event.key === 'Home') target = 0;
  else if (event.key === 'End') target = buttons.length - 1;
  else return;
  event.preventDefault();
  buttons[target]?.focus();
}
</script>

<template>
  <section class="page asset-gallery" aria-labelledby="library-title">
    <header class="gallery-header">
      <div>
        <h1 id="library-title">라이브러리</h1>
        <p class="gallery-count">{{ items.length }}개 에셋</p>
      </div>
      <div class="gallery-view-controls" role="group" aria-label="에셋 보기 방식">
        <button type="button" :aria-pressed="libraryUi.galleryViewMode === 'grid'"
          @click="changeView('grid')">그리드</button>
        <button type="button" :aria-pressed="libraryUi.galleryViewMode === 'list'"
          @click="changeView('list')">목록</button>
      </div>
    </header>

    <div v-if="items.length === 0" class="gallery-empty" role="status">
      <span class="gallery-empty-mark" aria-hidden="true">◇</span>
      <h2>표시할 에셋이 없습니다.</h2>
      <p>라이브러리가 비어 있습니다.</p>
    </div>
    <ul v-else-if="libraryUi.galleryViewMode === 'grid'" class="asset-grid" aria-label="에셋 그리드" @keydown="moveAssetFocus">
      <li v-for="item in items" :key="item.id" class="asset-card" :data-asset-id="item.id"
        :class="{ 'is-selected': selectedId === item.id }">
        <AssetThumbnail :id="item.id" :kind="item.kind" />
        <button type="button" class="asset-name asset-select" :title="item.name"
          :aria-pressed="selectedId === item.id" @click="$emit('select', item.id)">{{ item.name }}</button>
        <p class="asset-kind">{{ item.kind }}</p>
      </li>
    </ul>
    <div v-else class="asset-list-container">
      <table class="asset-list" aria-label="에셋 목록">
        <thead><tr><th scope="col">에셋명</th><th scope="col">유형</th></tr></thead>
        <tbody @keydown="moveAssetFocus">
          <tr v-for="item in items" :key="item.id" :data-asset-id="item.id"
            :class="{ 'is-selected': selectedId === item.id }">
            <td><button type="button" class="asset-name asset-select" :title="item.name"
              :aria-pressed="selectedId === item.id" @click="$emit('select', item.id)">{{ item.name }}</button></td>
            <td>{{ item.kind }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
