# UI Redesign — Centered → Split Panel

**Date:** 2026-05-11
**Scope:** `static/index.html` only — no backend changes.

---

## Goal

Replace the current single-column, stacked-textarea layout with a polished Centered → Split panel design. The redesign improves perceived quality, makes the output easier to read, and gives the UI a clear sense of state.

---

## Layout & States

The page has three distinct states driven by CSS transitions and JS class toggling.

### ① Idle (default)

- Full-width page, input centered vertically and horizontally
- Heading: **"Summarize any link"** (removes "MVP" from title)
- Subtext: "YouTube · Podcasts · 小红书 · Webpages"
- URL input + Summarize button in a single pill-style row (`background: #121a30`, `border-radius: 12px`, button inside the pill)
- Four source badges below the input row (YouTube, Podcasts, 小红书, Webpages) — decorative, non-interactive
- No right panel visible

### ② Processing

Triggered on submit. JS adds a `.split-active` class to the layout wrapper.

- **Left panel** (`width: 320px`, fixed) slides in from the left via CSS `transition: width 0.35s ease`
  - Shows the submitted URL (truncated if needed)
  - Button becomes disabled, label → "Summarizing…", styled with muted teal
  - Source type badge (e.g. "YouTube") appears once detected
  - Progress bar (4px height, teal fill) + Chinese status message below it
- **Right panel** (flex: 1) fades in via `opacity: 0 → 1`, `transform: translateX(8px) → translateX(0)` over 0.3s
  - Shows a skeleton loader (3–4 shimmer bars) while waiting
- Page `<title>` updates to "Summarizing… — Link Summarizer"

### ③ Done

Triggered when SSE `result` event arrives.

- Left panel: progress bar replaced by `✓ 完成 · <elapsed>` status line; button re-enables with label "Summarize again"
- Right panel: skeleton replaced by:
  - **Summary section** — `<div>` with label "SUMMARY" and the summary text in readable prose style (`font-size: 15px`, `line-height: 1.75`)
  - **Transcript section** — collapsed by default. Label row "▶ Transcript" acts as a toggle; clicking expands a `<div>` with the full transcript text in a smaller, muted style
- Page `<title>` updates to "Done — Link Summarizer"

### Error state

- Left panel: error message in amber/red tone replaces progress area
- Right panel: hidden (remains in skeleton or cleared)
- Button re-enables with label "Try again"

---

## Visual Design

| Token | Value |
|---|---|
| Page background | `#0b1020` |
| Left panel background | `#0d1525` |
| Card / output background | `#0d1525` |
| Border | `#1e2d50` |
| Accent (teal) | `#5eead4` |
| Primary text | `#eef2ff` |
| Secondary text | `#9fb0d9` |
| Muted text | `#4a5980` |
| Button text | `#08111f` |
| Progress fill | `#5eead4` |
| Error | `#f87171` |

Typography: `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` (unchanged).

---

## Transitions

| Transition | Property | Duration | Easing |
|---|---|---|---|
| Idle → Split | left panel `width` | 350ms | ease |
| Idle → Split | right panel `opacity` | 300ms | ease |
| Idle → Split | right panel `transform` | 300ms | ease |
| Progress bar fill | `width` | 400ms | ease |

No external animation libraries.

---

## Responsive Behavior

- **≥ 768px**: side-by-side layout as described
- **< 768px**: single column — left panel full width, right panel appears below as a normal block (no split)

---

## Preserved Behavior

- All SSE event handling logic unchanged
- Chinese status/progress messages unchanged (`检测链接类型...`, `转录音频分段 N / M…`, `完成`, etc.)
- `STEP_PCT` mapping unchanged
- Error handling logic unchanged
- No sessionStorage / history — each page load starts fresh

---

## Out of Scope

- Backend changes
- Copy button on summary/transcript
- Dark/light mode toggle
- Markdown rendering in summary
- Persistent history across page loads
