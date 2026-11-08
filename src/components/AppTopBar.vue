<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { workspace, setSearchQuery } from "../stores/workspace";

const route = useRoute();
const currentLocation = computed(() => String(route.meta.title ?? "라이브러리"));
const inSettings = computed(() => route.matched.some(record => record.path === '/settings'));
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
      <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <path d="m16 6 9 5v10l-9 5-9-5V11l9-5Zm-9 5 9 5 9-5m-9 5v10" />
      </svg>
      <span>AI Asset Hub</span>
    </RouterLink>

    <nav class="breadcrumbs" aria-label="현재 위치">
      <ol>
        <li><RouterLink to="/library" aria-current-value="false">작업 공간</RouterLink></li>
        <li aria-current="page">{{ currentLocation }}</li>
      </ol>
    </nav>

    <form v-show="!inSettings" class="topbar-search" role="search" aria-label="에셋 검색어 입력" @submit.prevent>
      <label class="visually-hidden" for="asset-search">에셋 검색어</label>
      <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m15.5 15.5 5 5" />
      </svg>
      <input id="asset-search" ref="searchInput" v-model="query"
        type="search" placeholder="에셋 검색" autocomplete="off" :spellcheck="false"
        @keydown.esc="handleEscape" />
      <button v-if="query" class="clear-search" type="button"
        aria-label="검색어 지우기" @click="clearSearch">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="m7 7 10 10M17 7 7 17" />
        </svg>
      </button>
    </form>

    <nav class="topbar-actions" aria-label="주 메뉴">
      <RouterLink to="/settings" :class="{ 'is-active': inSettings }">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="2.5" /><circle cx="15" cy="17" r="2.5" />
        </svg>설정
      </RouterLink>
    </nav>
  </header>
</template>
