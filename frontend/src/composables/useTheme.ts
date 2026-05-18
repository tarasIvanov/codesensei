import { computed, inject, provide, ref, type InjectionKey, type Ref } from 'vue'

export type ThemeChoice = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'codesensei.theme'

export interface ThemeApi {
  choice: Ref<ThemeChoice>
  resolved: Ref<ResolvedTheme>
  set(next: ThemeChoice): void
  cycle(): void
}

const THEME_KEY: InjectionKey<ThemeApi> = Symbol('useTheme')

function readStored(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* localStorage unavailable */
  }
  return 'system'
}

function systemPrefers(): ResolvedTheme {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

function applyToDom(resolved: ResolvedTheme): void {
  document.documentElement.dataset.theme = resolved
}

export function provideTheme(): ThemeApi {
  const choice = ref<ThemeChoice>(readStored())
  const sysPref = ref<ResolvedTheme>(systemPrefers())
  const resolved = computed<ResolvedTheme>(() =>
    choice.value === 'system' ? sysPref.value : choice.value,
  )

  let mql: MediaQueryList | null = null
  try {
    mql = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (ev: MediaQueryListEvent) => {
      sysPref.value = ev.matches ? 'dark' : 'light'
      if (choice.value === 'system') applyToDom(resolved.value)
    }
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', handler)
    }
  } catch {
    /* matchMedia unavailable */
  }

  applyToDom(resolved.value)

  function set(next: ThemeChoice): void {
    choice.value = next
    try {
      if (next === 'system') localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* localStorage unavailable */
    }
    applyToDom(resolved.value)
  }

  function cycle(): void {
    const order: ThemeChoice[] = ['system', 'light', 'dark']
    const idx = order.indexOf(choice.value)
    set(order[(idx + 1) % order.length])
  }

  const api: ThemeApi = { choice, resolved, set, cycle }
  provide(THEME_KEY, api)
  return api
}

export function useTheme(): ThemeApi {
  const api = inject(THEME_KEY)
  if (!api) {
    throw new Error('useTheme() called before provideTheme() — wire it inside <AppShell />')
  }
  return api
}
