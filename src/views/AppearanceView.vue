<script setup lang="ts">
import { appearance, setTheme } from "../stores/appearance";
</script>

<template>
  <section class="page" aria-labelledby="appearance-title">
    <h1 id="appearance-title">화면 설정</h1>
    <p class="page-description">작업 공간의 테마를 선택하세요.</p>
    <fieldset class="theme-options">
      <legend>테마</legend>
      <label>
        <input type="radio" name="theme" value="dark"
          :checked="appearance.theme === 'dark'" @change="setTheme('dark')" />
        다크
      </label>
      <label>
        <input type="radio" name="theme" value="light"
          :checked="appearance.theme === 'light'" @change="setTheme('light')" />
        라이트
      </label>
    </fieldset>
    <p class="setting-note">화면을 이동해도 선택한 테마가 유지됩니다.</p>
  </section>
</template>
