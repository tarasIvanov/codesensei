<script setup lang="ts">
import { provideTheme } from './composables/useTheme'
import { provideToastQueue } from './composables/useToast'
import AppShell from './components/AppShell.vue'

provideTheme()
provideToastQueue()
</script>

<template>
  <AppShell />
</template>
