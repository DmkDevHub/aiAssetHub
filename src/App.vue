<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";
import { RouterView } from "vue-router";
import AppTopBar from "./components/AppTopBar.vue";
import AppStatusBar from "./components/AppStatusBar.vue";
import CoreConnection from "./components/CoreConnection.vue";
import { appearance } from "./stores/appearance";
import { resetLibrarySession } from './stores/libraries';
import { resetAssets } from './stores/assets';

onBeforeUnmount(resetLibrarySession);
onBeforeUnmount(resetAssets);

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
    <AppTopBar />
    <main id="main-content" tabindex="-1">
      <RouterView />
    </main>
    <AppStatusBar />
    <CoreConnection />
  </div>
</template>
