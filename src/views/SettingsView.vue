<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';

const route = useRoute();
const tabs = computed(() => route.matched[0]?.children ?? []);
</script>

<template>
  <section class="settings-workspace" aria-labelledby="settings-title">
    <header class="settings-heading">
      <p class="section-label">AI Asset Hub</p>
      <p id="settings-title" class="settings-title">설정</p>
      <p>화면, 데이터, 연결 환경을 관리합니다.</p>
    </header>
    <nav class="settings-tabs" aria-label="설정 탭">
      <RouterLink v-for="tab in tabs" :key="tab.path" :to="`/settings/${tab.path}`">{{ tab.meta?.title }}</RouterLink>
    </nav>
    <div class="settings-content">
      <RouterView />
    </div>
  </section>
</template>
