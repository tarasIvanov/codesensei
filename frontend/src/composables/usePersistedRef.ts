import { ref, watch, type Ref } from 'vue'

export function usePersistedRef<T>(key: string, initial: T): Ref<T> {
  let stored: T | null = null
  try {
    const raw = localStorage.getItem(key)
    if (raw !== null) stored = JSON.parse(raw) as T
  } catch {
    /* ignore */
  }
  const state = ref<T>(stored ?? initial) as Ref<T>
  watch(
    state,
    (v) => {
      try {
        if (v === null || v === undefined) localStorage.removeItem(key)
        else localStorage.setItem(key, JSON.stringify(v))
      } catch {
        /* ignore */
      }
    },
    { deep: true },
  )
  return state
}

export function pushToRecentList<T>(
  key: string,
  value: T,
  cap = 10,
  eq: (a: T, b: T) => boolean = (a, b) => a === b,
): T[] {
  let list: T[] = []
  try {
    const raw = localStorage.getItem(key)
    if (raw) list = JSON.parse(raw) as T[]
  } catch {
    /* ignore */
  }
  list = [value, ...list.filter((x) => !eq(x, value))].slice(0, cap)
  try {
    localStorage.setItem(key, JSON.stringify(list))
  } catch {
    /* ignore */
  }
  return list
}

export function readList<T>(key: string): T[] {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    return JSON.parse(raw) as T[]
  } catch {
    return []
  }
}
