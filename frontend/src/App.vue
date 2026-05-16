<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <main>
    <nav class="topnav">
      <RouterLink to="/">Health</RouterLink>
      <RouterLink to="/review">Review</RouterLink>
    </nav>
    <RouterView />
  </main>
</template>

<style scoped>
main {
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  max-width: 48rem;
  margin: 2rem auto;
  padding: 1rem;
  color: #0f172a;
}
.topnav {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #e5e7eb;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.95rem;
}
.topnav a {
  color: #2563eb;
  text-decoration: none;
}
.topnav a.router-link-active {
  color: #0f172a;
  font-weight: 600;
}
</style>
