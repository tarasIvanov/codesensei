import { inject, provide, ref, type InjectionKey, type Ref } from 'vue'

export type ToastCategory = 'success' | 'info' | 'error'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface Toast {
  id: number
  category: ToastCategory
  message: string
  action?: ToastAction
  createdAt: number
}

export interface ToastApi {
  items: Ref<Toast[]>
  push(input: Omit<Toast, 'id' | 'createdAt'>): number
  dismiss(id: number): void
}

const TOAST_KEY: InjectionKey<ToastApi> = Symbol('useToast')
const MAX_VISIBLE = 4

export function provideToastQueue(): ToastApi {
  const items = ref<Toast[]>([])
  let nextId = 1

  function push(input: Omit<Toast, 'id' | 'createdAt'>): number {
    const toast: Toast = {
      id: nextId++,
      category: input.category,
      message: input.message,
      action: input.action,
      createdAt: Date.now(),
    }
    items.value = [toast, ...items.value]
    if (items.value.length > MAX_VISIBLE) {
      const droppableIdx = [...items.value].reverse().findIndex((t) => t.category !== 'error')
      if (droppableIdx === -1) {
        items.value = items.value.slice(0, MAX_VISIBLE)
        if (import.meta.env?.DEV) {
          console.warn('[toast] queue full of error toasts — dropping newest non-error overflow')
        }
      } else {
        const realIdx = items.value.length - 1 - droppableIdx
        items.value = items.value.filter((_, i) => i !== realIdx)
      }
    }
    return toast.id
  }

  function dismiss(id: number): void {
    items.value = items.value.filter((t) => t.id !== id)
  }

  const api: ToastApi = { items, push, dismiss }
  provide(TOAST_KEY, api)
  return api
}

export function useToast(): ToastApi {
  const api = inject(TOAST_KEY)
  if (!api) {
    throw new Error('useToast() called before provideToastQueue() — wire it inside <AppShell />')
  }
  return api
}
