<script setup lang="ts">
import { watch } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { appearance } from "./stores/appearance";

watch(() => appearance.theme, (theme) => {
  document.documentElement.dataset.theme = theme;
}, { immediate: true });

function focusMainContent() {
  document.getElementById("main-content")?.focus();
}
</script>

<template>
  <a class="skip-link" href="#main-content" @click.prevent="focusMainContent">본문으로 이동</a>
  <div class="app-shell">
    <header class="app-header">
      <p class="brand">AI Asset Hub</p>
      <nav aria-label="주 메뉴">
        <RouterLink to="/library">라이브러리</RouterLink>
        <RouterLink to="/settings/appearance">화면 설정</RouterLink>
      </nav>
    </header>
    <main id="main-content" tabindex="-1">
      <RouterView />
    </main>
  </div>
</template>
