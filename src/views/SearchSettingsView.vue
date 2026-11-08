<script setup lang="ts">
import EmbeddingTools from '../components/EmbeddingTools.vue';
</script>

<template>
  <section>
    <h1>검색 인덱스</h1>
    <p>의미 검색에 사용할 로컬 임베딩 모델과 인덱스를 관리합니다.</p>
    <EmbeddingTools scope="settings" class="settings-card" />
  </section>
</template>
