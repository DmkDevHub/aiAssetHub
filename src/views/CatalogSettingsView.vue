<script setup lang="ts">
import CatalogManager from '../components/CatalogManager.vue';
import PackageManager from '../components/PackageManager.vue';
</script>

<template>
  <section>
    <h1>카탈로그</h1>
    <p>라이브러리에서 공통으로 사용하는 분류와 패키지를 관리합니다.</p>
    <CatalogManager class="settings-card" />
    <div class="settings-card"><PackageManager /></div>
  </section>
</template>
