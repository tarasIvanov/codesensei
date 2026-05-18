<script setup lang="ts">
import { computed } from 'vue'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const props = withDefaults(
  defineProps<{
    variant?: Variant
    size?: Size
    loading?: boolean
    disabled?: boolean
    as?: 'button' | 'a'
    href?: string
    type?: 'button' | 'submit' | 'reset'
  }>(),
  { variant: 'primary', size: 'md', loading: false, disabled: false, as: 'button', type: 'button' },
)

const emit = defineEmits<{ (e: 'click', ev: MouseEvent): void }>()

const isDisabled = computed(() => props.disabled || props.loading)

const sizeClasses = computed(() =>
  props.size === 'sm' ? 'px-2.5 py-1 text-sm' : 'px-4 py-2 text-base',
)

const variantStyle = computed<Record<string, string>>(() => {
  switch (props.variant) {
    case 'primary':
      return {
        backgroundColor: 'var(--color-brand-600)',
        color: 'var(--color-neutral-0)',
        borderColor: 'transparent',
      }
    case 'secondary':
      return {
        backgroundColor: 'var(--color-bg-elevated)',
        color: 'var(--color-text)',
        borderColor: 'var(--color-border)',
      }
    case 'danger':
      return {
        backgroundColor: 'var(--color-danger-bg)',
        color: 'var(--color-danger-fg)',
        borderColor: 'transparent',
      }
    case 'ghost':
    default:
      return {
        backgroundColor: 'transparent',
        color: 'var(--color-text)',
        borderColor: 'transparent',
      }
  }
})

function onClick(ev: MouseEvent): void {
  if (isDisabled.value) {
    ev.preventDefault()
    return
  }
  emit('click', ev)
}
</script>

<template>
  <component
    :is="as === 'a' ? 'a' : 'button'"
    :type="as === 'a' ? undefined : type"
    :href="as === 'a' ? href : undefined"
    :disabled="as === 'a' ? undefined : isDisabled"
    :aria-busy="loading ? 'true' : undefined"
    :aria-disabled="isDisabled ? 'true' : undefined"
    class="focus-ring inline-flex items-center justify-center gap-2 border font-medium transition-colors duration-150 cursor-pointer select-none"
    :class="[
      sizeClasses,
      isDisabled ? 'opacity-50 pointer-events-none cursor-not-allowed' : 'hover:brightness-110',
    ]"
    :style="{
      ...variantStyle,
      borderRadius: 'var(--radius-sm)',
    }"
    @click="onClick"
  >
    <svg
      v-if="loading"
      class="animate-spin h-4 w-4 -ml-1"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" opacity="0.25" />
      <path
        d="M22 12a10 10 0 0 1-10 10"
        stroke="currentColor"
        stroke-width="3"
        stroke-linecap="round"
      />
    </svg>
    <slot />
  </component>
</template>
