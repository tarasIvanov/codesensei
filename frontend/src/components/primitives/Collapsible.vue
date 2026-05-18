<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{ defaultOpen?: boolean }>(), { defaultOpen: true })
const emit = defineEmits<{ (e: 'toggle', open: boolean): void }>()

const open = ref(props.defaultOpen)

function toggle(): void {
  open.value = !open.value
  emit('toggle', open.value)
}

function onKey(ev: KeyboardEvent): void {
  if (ev.key === 'Enter' || ev.key === ' ') {
    ev.preventDefault()
    toggle()
  }
}
</script>

<template>
  <div>
    <button
      type="button"
      class="focus-ring w-full text-left cursor-pointer"
      :aria-expanded="open"
      @click="toggle"
      @keydown="onKey"
    >
      <slot name="header" :open="open" :toggle="toggle" />
    </button>
    <Transition name="collapse">
      <div v-show="open">
        <slot name="body" />
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.collapse-enter-active,
.collapse-leave-active {
  transition:
    max-height 200ms ease,
    opacity 150ms ease;
  overflow: hidden;
}
.collapse-enter-from,
.collapse-leave-to {
  max-height: 0;
  opacity: 0;
}
.collapse-enter-to,
.collapse-leave-from {
  max-height: 2000px;
  opacity: 1;
}
</style>
