<script setup lang="ts">
import { libraryUi, setGalleryViewMode } from "../stores/libraryUi";
import type { AssetSummary } from "../types/assets";

withDefaults(defineProps<{ items?: readonly AssetSummary[]; selectedId?: string | null }>(), {
  items: () => [], selectedId: null,
});
defineEmits<{ select: [id: string] }>();
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
          @click="setGalleryViewMode('grid')">그리드</button>
        <button type="button" :aria-pressed="libraryUi.galleryViewMode === 'list'"
          @click="setGalleryViewMode('list')">목록</button>
      </div>
    </header>

    <div v-if="items.length === 0" class="gallery-empty" role="status">
      <span class="gallery-empty-mark" aria-hidden="true">◇</span>
      <h2>표시할 에셋이 없습니다.</h2>
      <p>라이브러리가 비어 있습니다.</p>
    </div>
    <ul v-else-if="libraryUi.galleryViewMode === 'grid'" class="asset-grid" aria-label="에셋 그리드">
      <li v-for="item in items" :key="item.id" class="asset-card" :data-asset-id="item.id"
        :class="{ 'is-selected': selectedId === item.id }">
        <div class="asset-format-mark" aria-hidden="true">{{ item.kind }}</div>
        <button type="button" class="asset-name asset-select" :title="item.name"
          :aria-pressed="selectedId === item.id" @click="$emit('select', item.id)">{{ item.name }}</button>
        <p class="asset-kind">{{ item.kind }}</p>
      </li>
    </ul>
    <div v-else class="asset-list-container">
      <table class="asset-list" aria-label="에셋 목록">
        <thead><tr><th scope="col">에셋명</th><th scope="col">유형</th></tr></thead>
        <tbody>
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
