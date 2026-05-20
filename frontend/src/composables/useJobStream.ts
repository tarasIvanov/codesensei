import { ref, watch, type Ref } from 'vue'

export interface ProgressFrame {
  kind: 'progress' | 'init' | 'complete'
  state?: 'queued' | 'running' | 'success' | 'failed' | 'cancelled'
  files_done?: number
  files_total?: number | null
  chunks_done?: number
  current_file?: string | null
  error_category?: string | null
  error_message?: string | null
  final_files?: number
  final_chunks?: number
}

export function useJobStream(
  jobId: Ref<string | null>,
  onFrame: (frame: ProgressFrame) => void,
): { fallbackToPolling: Ref<boolean>; close: () => void } {
  const fallbackToPolling = ref<boolean>(true)
  let socket: WebSocket | null = null

  function openSocket(id: string): void {
    closeSocket()
    try {
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${scheme}://${window.location.host}/api/jobs/${encodeURIComponent(id)}/stream`
      socket = new WebSocket(url)
    } catch {
      fallbackToPolling.value = true
      return
    }
    socket.onopen = () => {
      fallbackToPolling.value = false
    }
    socket.onmessage = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(typeof event.data === 'string' ? event.data : '') as ProgressFrame
        onFrame(parsed)
      } catch {
        /* swallow malformed frame */
      }
    }
    socket.onerror = () => {
      fallbackToPolling.value = true
    }
    socket.onclose = (event: CloseEvent) => {
      if (event.code !== 1000) {
        fallbackToPolling.value = true
      }
      socket = null
    }
  }

  function closeSocket(): void {
    if (socket !== null) {
      try {
        socket.close(1000, 'client_close')
      } catch {
        /* ignore */
      }
      socket = null
    }
  }

  watch(
    jobId,
    (next) => {
      if (next === null || next === '') {
        closeSocket()
        fallbackToPolling.value = true
        return
      }
      openSocket(next)
    },
    { immediate: true },
  )

  return { fallbackToPolling, close: closeSocket }
}
