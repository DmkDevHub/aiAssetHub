<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { workspace, setSearchQuery } from "../stores/workspace";

const route = useRoute();
const currentLocation = computed(() => String(route.meta.title ?? "라이브러리"));
const query = computed({ get: () => workspace.searchQuery, set: setSearchQuery });
const searchInput = ref<HTMLInputElement | null>(null);

function clearSearch() {
  setSearchQuery("");
  searchInput.value?.focus();
}

function handleEscape(event: KeyboardEvent) {
  if (!event.isComposing) clearSearch();
}
</script>

<template>
  <header class="app-topbar">
    <RouterLink class="brand" to="/library" aria-label="AI Asset Hub 홈">
      AI Asset Hub
    </RouterLink>

    <RouterLink to="/settings/models">모델 관리</RouterLink>
    <nav class="breadcrumbs" aria-label="현재 위치">
      <ol>
        <li><RouterLink to="/library" aria-current-value="false">작업 공간</RouterLink></li>
        <li aria-current="page">{{ currentLocation }}</li>
      </ol>
    </nav>

    <form class="topbar-search" role="search" aria-label="에셋 검색어 입력" @submit.prevent>
      <label class="visually-hidden" for="asset-search">에셋 검색어</label>
      <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m15.5 15.5 5 5" />
      </svg>
      <input id="asset-search" ref="searchInput" v-model="query"
        type="search" placeholder="검색어 입력" autocomplete="off" :spellcheck="false"
        @keydown.esc="handleEscape" />
      <button v-if="query" class="clear-search" type="button"
        aria-label="검색어 지우기" @click="clearSearch">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="m7 7 10 10M17 7 7 17" />
        </svg>
      </button>
    </form>

    <nav class="topbar-actions" aria-label="주 메뉴">
      <RouterLink to="/settings/appearance">화면 설정</RouterLink>
    </nav>
  </header>
</template>
