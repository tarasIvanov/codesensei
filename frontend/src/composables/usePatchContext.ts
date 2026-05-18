/**
 * Walk a unified-diff patch for a single file and return the lines ±N around
 * a target line number on the RHS (post-change) side.
 *
 * Contract: returns `null` when the patch does not cover `target_line` (the
 * line is outside every hunk's RHS range). Otherwise returns up to `2*context+1`
 * entries, clipped at hunk boundaries.
 *
 * Algorithm: parse `@@ -A,B +C,D @@` hunk headers, track the running RHS line
 * counter inside each hunk, collect a deque of (line, text, side) tuples that
 * fall in `[target - context, target + context]`. O(n) over the patch text.
 */

export type LineSide = 'context' | 'add' | 'remove'

export interface SnippetLine {
  line: number | null // null for `remove` lines (they have no RHS line)
  text: string
  side: LineSide
  is_target: boolean
}

export interface CodeContextSnippet {
  lines: SnippetLine[]
}

const HUNK_RE = /^@@\s-\d+(?:,\d+)?\s\+(\d+)(?:,\d+)?\s@@/

interface HunkLine {
  line: number | null
  text: string
  side: LineSide
}

export function usePatchContext(
  patch: string,
  target_line: number,
  context: number = 3,
): CodeContextSnippet | null {
  if (!patch || !Number.isFinite(target_line) || target_line <= 0) return null

  const rawLines = patch.split('\n')
  let rhsCursor = 0
  let inHunk = false
  const all: HunkLine[] = []
  let coversTarget = false

  for (const raw of rawLines) {
    const m = raw.match(HUNK_RE)
    if (m) {
      rhsCursor = Number.parseInt(m[1], 10)
      inHunk = true
      continue
    }
    if (!inHunk) continue
    if (raw.startsWith('+')) {
      const entry: HunkLine = { line: rhsCursor, text: raw.slice(1), side: 'add' }
      if (rhsCursor === target_line) coversTarget = true
      all.push(entry)
      rhsCursor += 1
    } else if (raw.startsWith('-')) {
      all.push({ line: null, text: raw.slice(1), side: 'remove' })
    } else if (raw.startsWith(' ')) {
      const entry: HunkLine = { line: rhsCursor, text: raw.slice(1), side: 'context' }
      if (rhsCursor === target_line) coversTarget = true
      all.push(entry)
      rhsCursor += 1
    } else if (raw.startsWith('\\')) {
      // "\ No newline at end of file" — ignore
      continue
    } else {
      // any other prefix means we left the hunk body (rare)
      inHunk = false
    }
  }

  if (!coversTarget) return null

  const targetIdx = all.findIndex((l) => l.line === target_line)
  if (targetIdx === -1) return null

  // Walk outward, collecting up to `context` RHS-side lines on each side.
  // RHS-side = side ∈ {add, context}. Skip removes for the count but keep them
  // if they fall between collected lines (so the visual hunk reads naturally).
  const before: HunkLine[] = []
  let beforeCount = 0
  for (let i = targetIdx - 1; i >= 0 && beforeCount < context; i--) {
    before.unshift(all[i])
    if (all[i].side !== 'remove') beforeCount += 1
  }

  const after: HunkLine[] = []
  let afterCount = 0
  for (let i = targetIdx + 1; i < all.length && afterCount < context; i++) {
    after.push(all[i])
    if (all[i].side !== 'remove') afterCount += 1
  }

  const lines: SnippetLine[] = [
    ...before.map((l) => ({ ...l, is_target: false })),
    { ...all[targetIdx], is_target: true },
    ...after.map((l) => ({ ...l, is_target: false })),
  ]

  return { lines }
}
