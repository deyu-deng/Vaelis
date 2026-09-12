import { afterEach, describe, expect, it } from 'vitest'

import { setRuntimeI18nLocale } from '@/i18n'

import {
  buildToolView,
  clampForDisplay,
  countDiffLineStats,
  failureRowLabel,
  inlineDiffFromResult,
  MAX_TOOL_RENDER_CHARS,
  type ToolPart
} from './fallback-model'

describe('failureRowLabel (WP-UI-NO-INTERNALS)', () => {
  const view = { subtitle: 'curl 127.0.0.1:5030/health', title: 'Searched files' }

  it('collapses a failed row to the one-line label and hides the internals', () => {
    const head = failureRowLabel('error', view, 'Tool did not succeed')

    expect(head.title).toBe('Tool did not succeed')
    expect(head.subtitle).toBe('')
    // The raw command/error is still reachable through the tooltip.
    expect(head.tooltip).toBe('Searched files · curl 127.0.0.1:5030/health')
  })

  it('passes success rows through untouched (C3 dispatch card stays)', () => {
    const head = failureRowLabel('success', view, 'Tool did not succeed')

    expect(head).toEqual({ subtitle: view.subtitle, title: view.title, tooltip: '' })
  })

  it('keeps a warning row as-is', () => {
    expect(failureRowLabel('warning', view, 'x').title).toBe('Searched files')
  })
})

const part = (overrides: Partial<ToolPart>): ToolPart => ({
  args: {},
  isError: false,
  result: {},
  toolCallId: 'call_1',
  toolName: 'vision_analyze',
  type: 'tool-call',
  ...overrides
})

afterEach(() => {
  setRuntimeI18nLocale('en')
})

describe('buildToolView image handling', () => {
  // vision_analyze reports the input image as a local path; an <img> pointed at
  // a bare path resolves against the renderer origin and 404s, so we render the
  // tool codicon instead of a broken image.
  it('drops bare filesystem paths', () => {
    expect(buildToolView(part({ args: { path: '/Users/me/shot.png' } }), '').imageUrl).toBe('')
    expect(buildToolView(part({ result: { image_path: '/tmp/out.jpg' } }), '').imageUrl).toBe('')
  })

  it('keeps fetchable data URLs', () => {
    const dataUrl = 'data:image/png;base64,AAAA'

    expect(buildToolView(part({ result: { image_url: dataUrl } }), '').imageUrl).toBe(dataUrl)
  })

  it('keeps remote http(s) image URLs', () => {
    const url = 'https://example.com/pic.webp'

    expect(buildToolView(part({ result: { url } }), '').imageUrl).toBe(url)
  })
})

describe('buildToolView terminal exit-code status', () => {
  const terminal = (result: Record<string, unknown>) => buildToolView(part({ result, toolName: 'terminal' }), '')

  // A non-zero exit code with real output is not a failure (grep no-match,
  // diff differences, piped commands surfacing the last stage's code, etc.) —
  // it should render as success so the card isn't painted red.
  it('treats non-zero exit with output as success', () => {
    expect(terminal({ exit_code: 7, output: 'node ... 5174 (LISTEN)' }).status).toBe('success')
    expect(terminal({ exit_code: 1, stdout: 'partial results' }).status).toBe('success')
  })

  // No output + non-zero exit is a genuine failure worth flagging.
  it('treats non-zero exit with no output as error', () => {
    expect(terminal({ exit_code: 127, output: '' }).status).toBe('error')
    expect(terminal({ exit_code: 1 }).status).toBe('error')
  })

  it('treats zero exit as success', () => {
    expect(terminal({ exit_code: 0, output: 'done' }).status).toBe('success')
  })

  // Explicit error signals still win regardless of output presence.
  it('keeps explicit error signals red even with output', () => {
    expect(terminal({ error: 'boom', exit_code: 0, output: 'partial' }).status).toBe('error')
    expect(buildToolView(part({ isError: true, result: { output: 'x' }, toolName: 'terminal' }), '').status).toBe(
      'error'
    )
  })
})

describe('buildToolView browser_navigate title', () => {
  it('shows failed title when navigate returns success=false', () => {
    const view = buildToolView(
      part({
        toolName: 'browser_navigate',
        args: { url: 'https://hermes-agent.nousresearch.com/docs' },
        result: { success: false, error: 'Command timed out after 60 seconds' }
      }),
      ''
    )

    expect(view.status).toBe('error')
    // WP-FE-TESTROT: the row label is host + path by design (see `hostnameOf`),
    // so the page is identifiable — the assertion was the stale half.
    expect(view.title).toBe('Failed to open hermes-agent.nousresearch.com/docs')
  })

  it('shows opened title on success', () => {
    const view = buildToolView(
      part({
        toolName: 'browser_navigate',
        args: { url: 'https://hermes-agent.nousresearch.com/docs' },
        result: { success: true, url: 'https://hermes-agent.nousresearch.com/docs', title: 'Docs' }
      }),
      ''
    )

    expect(view.status).toBe('success')
    expect(view.title).toBe('Opened hermes-agent.nousresearch.com/docs')
  })
})

describe('buildToolView file edit diffs', () => {
  const patchDiff = '--- a/src/demo.ts\n+++ b/src/demo.ts\n@@ -1 +1 @@\n-old\n+new'

  it('reads inline_diff and diff fields from patch results', () => {
    expect(inlineDiffFromResult({ inline_diff: patchDiff })).toBe(patchDiff)
    expect(inlineDiffFromResult({ diff: patchDiff })).toBe(patchDiff)
  })

  it('suppresses raw patch args when a diff is available', () => {
    const view = buildToolView(
      part({
        args: { context: 'src/demo.ts', mode: 'replace', new_string: 'new', path: 'src/demo.ts' },
        result: { diff: patchDiff, success: true },
        toolName: 'patch'
      }),
      patchDiff
    )

    expect(view.title).toBe('demo.ts')
    expect(view.subtitle).toBe('src/demo.ts')
    expect(view.detail).toBe('')
    expect(view.inlineDiff).toBe(patchDiff)
  })

  it('shows path subtitle instead of patch args JSON while pending', () => {
    const view = buildToolView(
      part({
        args: { context: 'src/demo.ts', mode: 'replace', new_string: 'new', path: 'src/demo.ts' },
        result: undefined,
        toolName: 'patch'
      }),
      ''
    )

    expect(view.title).toBe('demo.ts')
    expect(view.subtitle).toBe('src/demo.ts')
    expect(view.detail).toBe('')
  })
})

describe('buildToolView title actions', () => {
  it('marks the pending action separately from the rest of the title', () => {
    const read = buildToolView(part({ args: { path: '/tmp/demo.txt' }, result: undefined, toolName: 'read_file' }), '')

    const web = buildToolView(
      part({ args: { url: 'https://example.com/docs' }, result: undefined, toolName: 'web_extract' }),
      ''
    )

    const terminal = buildToolView(
      part({ args: { command: 'npm test -- --runInBand' }, result: undefined, toolName: 'terminal' }),
      ''
    )

    const code = buildToolView(
      part({ args: { code: 'print("hello")' }, result: undefined, toolName: 'execute_code' }),
      ''
    )

    expect(read.title).toBe('Reading demo.txt')
    expect(read.titleAction).toEqual({ prefix: '', text: 'Reading', suffix: ' demo.txt' })
    expect(web.title).toBe('Reading example.com/docs')
    expect(web.titleAction).toEqual({ prefix: '', text: 'Reading', suffix: ' example.com/docs' })
    expect(terminal.title).toBe('Running npm test -- --runInBand')
    expect(terminal.titleAction).toEqual({ prefix: '', text: 'Running', suffix: ' npm test -- --runInBand' })
    expect(code.title).toBe('Scripting print("hello")')
    expect(code.titleAction).toEqual({ prefix: '', text: 'Scripting', suffix: ' print("hello")' })
  })

  it('does not mark completed tool titles as pending actions', () => {
    const view = buildToolView(part({ args: { url: 'https://example.com/docs' }, toolName: 'web_extract' }), '')

    expect(view.title).toBe('Read example.com/docs')
    expect(view.titleAction).toBeUndefined()
  })

  it('uses the filename for completed read_file rows', () => {
    const view = buildToolView(
      part({ args: { path: './package.json' }, result: { content: '1|{"name":"demo"}' }, toolName: 'read_file' }),
      ''
    )

    expect(view.title).toBe('Read package.json')
    expect(view.subtitle).toBe('')
    expect(view.titleAction).toBeUndefined()
  })

  it('adds a compact line range to line-scoped read_file rows', () => {
    const view = buildToolView(
      part({
        args: { limit: 10, offset: 25, path: './src/main.ts' },
        result: { content: '25|function toggleDock() {\n26|  dock.classList.toggle("hidden");\n34|}' },
        toolName: 'read_file'
      }),
      ''
    )

    expect(view.title).toBe('Read main.ts L25-34')
    expect(view.subtitle).toBe('')
  })

  it('uses the requested positive offset/limit for read_file row line ranges', () => {
    const view = buildToolView(
      part({
        args: { limit: 5, offset: 1, path: './package.json' },
        result: {
          content:
            '1|{\n2|  "name": "bb-rainbows",\n3|  "private": true,\n4|  "version": "0.0.1",\n5|  "type": "module",\n6|  "description": "extra"'
        },
        toolName: 'read_file'
      }),
      ''
    )

    expect(view.title).toBe('Read package.json L1-5')
  })

  it('uses inherited backend context for live read_file rows', () => {
    const view = buildToolView(
      part({
        args: { context: 'package.json L1-5', path: './package.json' },
        result: undefined,
        toolName: 'read_file'
      }),
      ''
    )

    expect(view.title).toBe('Reading package.json L1-5')
    expect(view.titleAction).toEqual({ prefix: '', text: 'Reading', suffix: ' package.json L1-5' })
  })

  it('uses returned line numbers for negative-offset read_file rows', () => {
    const view = buildToolView(
      part({
        args: { limit: 2, offset: -2, path: './src/main.ts' },
        result: { content: '99|lastLine();\n100|done();' },
        toolName: 'read_file'
      }),
      ''
    )

    expect(view.title).toBe('Read main.ts L99-100')
  })

  it('renders compact terminal titles for session 20260624_231846_bdbd1e commands', () => {
    const rows = [
      [
        'cd /Users/brooklyn/www/bb-rainbows && pnpm run lint 2>&1 | tail -20; echo "lint_exit=${PIPESTATUS[0]}"',
        'Ran pnpm run lint'
      ],
      [
        'cd /Users/brooklyn/www/bb-rainbows && pnpm run build 2>&1 | tail -20; echo "build_exit=${PIPESTATUS[0]}"',
        'Ran pnpm run build'
      ],
      [
        'which node pnpm corepack; node -v; echo "---"; corepack --version 2>&1; echo "---pnpm via corepack---"; pnpm --version 2>&1 | tail -5',
        'Ran which node pnpm corepack + 3 commands'
      ],
      [
        'echo "--- proto pnpm direct ---"; ~/.proto/tools/node/24.11.0/bin/pnpm --version 2>&1 | tail -3; echo "--- proto node ---"; ls ~/.proto/tools/node/ 2>&1; echo "--- corepack cache ---"; ls ~/.cache/node/corepack/v1/pnpm/ 2>&1',
        'Ran ~/.proto/tools/node/24.11.0/bin/pnpm --version + 2 commands'
      ],
      [
        'cd /Users/brooklyn/www/bb-rainbows && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@10.20.0 --version 2>&1 | tail -3',
        'Ran COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@10.20.0 --version'
      ],
      [
        'cd /Users/brooklyn/www/bb-rainbows && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack use pnpm@10.20.0 2>&1 | tail -10; echo "exit=$?"',
        'Ran COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack use pnpm@10.20.0'
      ]
    ] as const

    for (const [command, expectedTitle] of rows) {
      const view = buildToolView(
        part({ args: { command }, result: { output: 'ok', exit_code: 0 }, toolName: 'terminal' }),
        ''
      )

      expect(view.title).toBe(expectedTitle)
    }
  })

  it('uses inherited backend context for live terminal rows', () => {
    const view = buildToolView(
      part({
        args: {
          command: 'cd /Users/brooklyn/www/bb-rainbows && pnpm run lint 2>&1 | tail -20',
          context: 'pnpm run lint'
        },
        result: undefined,
        toolName: 'terminal'
      }),
      ''
    )

    expect(view.title).toBe('Running pnpm run lint')
    expect(view.subtitle).toBe('')
    expect(view.titleAction).toEqual({ prefix: '', text: 'Running', suffix: ' pnpm run lint' })
  })

  it('uses the runtime locale for title text and action placement', () => {
    setRuntimeI18nLocale('ja')

    const read = buildToolView(part({ args: { path: '/tmp/demo.txt' }, result: undefined, toolName: 'read_file' }), '')

    const web = buildToolView(
      part({ args: { url: 'https://example.com/docs' }, result: undefined, toolName: 'web_extract' }),
      ''
    )

    expect(read.title).toBe('demo.txt を読み取り中')
    expect(read.titleAction).toEqual({ prefix: 'demo.txt を', text: '読み取り中', suffix: '' })
    expect(web.title).toBe('example.com/docs を読み取り中')
    expect(web.titleAction).toEqual({ prefix: 'example.com/docs を', text: '読み取り中', suffix: '' })
  })
})

describe('clampForDisplay', () => {
  it('passes short payloads through untouched', () => {
    expect(clampForDisplay('hello')).toBe('hello')
    expect(clampForDisplay('x'.repeat(MAX_TOOL_RENDER_CHARS))).toHaveLength(MAX_TOOL_RENDER_CHARS)
  })

  it('truncates oversized payloads and reports the omitted count', () => {
    const oversized = 'x'.repeat(MAX_TOOL_RENDER_CHARS + 5_000)
    const clamped = clampForDisplay(oversized)

    expect(clamped.length).toBeLessThan(oversized.length)
    expect(clamped.startsWith('x'.repeat(MAX_TOOL_RENDER_CHARS))).toBe(true)
    expect(clamped).toContain('5,000 more characters truncated')
    expect(clamped).toContain('Copy')
  })
})

// A large tool result (e.g. a 100KB read_file during a `/learn` run) must not
// be serialized into the rendered rawResult at full size — that JSON.stringify
// payload is what floods the renderer when many rows stack up.
describe('buildToolView caps serialized result size', () => {
  it('clamps rawResult for an oversized result', () => {
    const huge = 'y'.repeat(MAX_TOOL_RENDER_CHARS * 3)
    const view = buildToolView(part({ result: { content: huge }, toolName: 'read_file' }), '')

    expect(view.rawResult.length).toBeLessThanOrEqual(MAX_TOOL_RENDER_CHARS + 200)
    expect(view.rawResult).toContain('truncated')
  })
})

describe('countDiffLineStats', () => {
  it('counts added and removed lines', () => {
    expect(countDiffLineStats(`--- a/x\n+++ b/x\n@@\n-old\n+new\n context\n+another`)).toEqual({ added: 2, removed: 1 })
  })
})

describe('buildToolView vaelis_secretary_ask (WP-G5 real JSON)', () => {
  it('shows 日程秘书 + intent while waiting (args only)', () => {
    const view = buildToolView(
      part({
        args: { intent: 'refresh_agenda', user_text: '明天的日常安排是什么' },
        result: undefined,
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.status).toBe('running')
    expect(view.title).toBe('Asking 日程秘书')
    expect(view.subtitle).toContain('日程秘书')
    expect(view.subtitle).toContain('refresh agenda')
  })

  it('never says Asked 日程秘书 for a pending mutate_agenda call (WP-L1-MUTATE-CARD)', () => {
    setRuntimeI18nLocale('zh')
    const view = buildToolView(
      part({
        args: { intent: 'mutate_agenda', action: 'create', user_text: '帮我加明天下午三点开会' },
        result: undefined,
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.title).toBe('记日程中')
    expect(view.title).not.toContain('Asked')
    expect(view.title).not.toContain('日程秘书')
  })
})

describe('buildToolView vaelis_secretary_ask mutate_agenda (WP-L1-MUTATE-CARD, 裁定 27)', () => {
  afterEach(() => {
    setRuntimeI18nLocale('en')
  })

  it('create reads 已记下 with 标题 · 15:00 · 未写结束', () => {
    setRuntimeI18nLocale('zh')
    const view = buildToolView(
      part({
        args: { intent: 'mutate_agenda', action: 'create', user_text: '帮我加明天下午三点开会' },
        result: {
          ok: true,
          intent: 'mutate_agenda',
          action: 'create',
          user_text: '帮我加明天下午三点开会',
          event: { id: 'evt_1', title: '开会', start_at: '2026-09-12T15:00:00', end_at: null, status: 'confirmed' }
        },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.status).toBe('success')
    expect(view.title).toBe('已记下')
    expect(view.subtitle).toBe('开会 · 15:00 · 未写结束')
    // 裁定 27: a spoken order is done work — the dispatch wording must be gone.
    expect(view.subtitle).not.toContain('日程秘书')
  })

  it('update reads 已改 with a real start–end span', () => {
    setRuntimeI18nLocale('zh')
    const view = buildToolView(
      part({
        args: { intent: 'mutate_agenda', action: 'update', event_id: 'evt_1' },
        result: {
          ok: true,
          intent: 'mutate_agenda',
          action: 'update',
          event: { id: 'evt_1', title: '开会', start_at: '2026-09-12T15:00:00', end_at: '2026-09-12T16:00:00' }
        },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.title).toBe('已改')
    expect(view.subtitle).toBe('开会 · 15:00–16:00')
  })

  it('delete reads 已取消', () => {
    setRuntimeI18nLocale('zh')
    const view = buildToolView(
      part({
        args: { intent: 'mutate_agenda', action: 'delete', event_id: 'evt_1' },
        result: { ok: true, intent: 'mutate_agenda', action: 'delete', deleted: true, title: '开会' },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.title).toBe('已取消')
    expect(view.subtitle).toContain('开会')
  })

  it('keeps the C3 wording for refresh_agenda', () => {
    const view = buildToolView(
      part({
        args: { intent: 'refresh_agenda', user_text: '明天的日常安排是什么' },
        result: { ok: true, intent: 'refresh_agenda', agent: { id: 'agenda' } },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.title).toBe('Asked 日程秘书')
  })

  it('maps agent.id short name and lists agenda.events on refresh', () => {
    const view = buildToolView(
      part({
        args: { intent: 'refresh_agenda', user_text: '明天的日常安排是什么' },
        result: {
          ok: true,
          intent: 'refresh_agenda',
          user_text: '明天的日常安排是什么',
          agent: { id: 'agenda', role: 'secretary', profile: 'agenda', spawned: false },
          agenda: {
            events: [
              {
                id: 'e1',
                title: 'Standup',
                start_at: '2026-09-07T09:00:00+08:00',
                end_at: '2026-09-07T09:30:00+08:00',
                kind: 'meeting',
                status: 'confirmed',
                source: 'chatlog'
              }
            ]
          },
          route: 'fallback',
          model: 'test'
        },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.status).toBe('success')
    expect(view.title).toBe('Asked 日程秘书')
    expect(view.subtitle).toContain('refresh agenda')
    expect(view.subtitle).toContain('route=fallback')
    expect(view.subtitle).toContain('1 event')
    expect(view.detail).toContain('Standup')
    expect(view.detail).toContain('2026-09-07T09:00:00+08:00')
  })

  it('shows an empty-window refresh without inventing events', () => {
    const view = buildToolView(
      part({
        args: { intent: 'refresh_agenda' },
        result: {
          ok: true,
          intent: 'refresh_agenda',
          agent: { id: 'agenda-secretary' },
          agenda: { events: [] },
          route: 'fallback'
        },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.title).toBe('Asked 日程秘书')
    expect(view.subtitle).toContain('no events')
    expect(view.detail).toContain('no events')
  })

  it('shows write_briefing route while waiting when args already carry it', () => {
    const view = buildToolView(
      part({
        args: { intent: 'write_briefing', user_text: '根据明天的日程写一段早报', route: 'workbuddy' },
        result: undefined,
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.status).toBe('running')
    expect(view.title).toBe('Asking 日程秘书')
    expect(view.subtitle).toContain('write briefing')
    expect(view.subtitle).toContain('route=workbuddy')
  })

  it('maps write_briefing model hint to route=workbuddy when route is absent', () => {
    const view = buildToolView(
      part({
        args: { intent: 'write_briefing' },
        result: { ok: true, intent: 'write_briefing', briefing: 'Morning.', model: 'workbuddy/deepseek-chat' },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.subtitle).toContain('route=workbuddy')
  })

  it('surfaces briefing text and F2 route on write_briefing', () => {
    const view = buildToolView(
      part({
        args: { intent: 'write_briefing', user_text: '根据明天的日程写一段早报' },
        result: {
          ok: true,
          intent: 'write_briefing',
          agent: { id: 'agenda' },
          briefing: 'Tomorrow: 09:00 standup, 14:00 review.',
          route: 'workbuddy',
          model: 'workbuddy/default'
        },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.status).toBe('success')
    expect(view.title).toBe('Asked 日程秘书')
    expect(view.subtitle).toContain('write briefing')
    expect(view.subtitle).toContain('route=workbuddy')
    expect(view.detail).toContain('09:00 standup')
  })

  it('paints the chatlog dead door as a visible error', () => {
    const view = buildToolView(
      part({
        args: { intent: 'refresh_agenda' },
        isError: true,
        result: {
          ok: false,
          dead: true,
          error: 'chatlog 未启动或 /health 失败，采集不通',
          agent: { id: 'agenda' }
        },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(view.status).toBe('error')
    expect(view.title).toBe('Asked 日程秘书')
    expect(view.subtitle).toContain('chatlog 未启动或 /health 失败，采集不通')
    expect(view.detail).toContain('chatlog 未启动或 /health 失败，采集不通')
  })
})

describe('buildToolView vaelis_secretary_ask query_agenda (WP-SEC-VOCAB, 裁定 28.4)', () => {
  afterEach(() => {
    setRuntimeI18nLocale('en')
  })

  const event = (id: string, title: string, start: string, end: string | null, status = 'confirmed') => ({
    id,
    title,
    start_at: start,
    end_at: end,
    kind: 'class',
    status,
    source: 'timetable'
  })

  const query = (result: Record<string, unknown>, args: Record<string, unknown> = {}) =>
    buildToolView(
      part({
        args: { intent: 'query_agenda', user_text: '今天有什么', ...args },
        result: { ok: true, intent: 'query_agenda', ...result },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

  it('titles today / tomorrow / week with the backend row count', () => {
    setRuntimeI18nLocale('zh')
    const today = query({ range: 'today', from: '2026-09-12', to: '2026-09-12', events: [event('1', '高数课', '2026-09-12T08:00:00', '2026-09-12T09:40:00')], pending: [] })

    expect(today.title).toBe('今天的安排 · 1 条')

    const tomorrow = query({ range: 'tomorrow', from: '2026-09-13', to: '2026-09-13', events: [], pending: [] })

    expect(tomorrow.title).toBe('明天 · 0 条')
    expect(tomorrow.subtitle).toBe('没有安排')

    const week = query({ range: 'week', events: [event('1', 'a', '2026-09-12T08:00:00', null), event('2', 'b', '2026-09-13T08:00:00', null)], pending: [] })

    expect(week.title).toBe('本周 · 2 条')
  })

  it('titles a date range from the backend `from` (MM-DD) and a pending range from pending.length', () => {
    setRuntimeI18nLocale('zh')
    const dated = query({ range: 'date', from: '2026-09-15', to: '2026-09-15', events: [event('1', '体检', '2026-09-15T09:00:00', null)], pending: [] })

    expect(dated.title).toBe('09-15 · 1 条')

    const pendingRange = query({ range: 'pending', events: [], pending: [event('1', '组会', '2026-09-12T10:00:00', null, 'pending')] })

    expect(pendingRange.title).toBe('待确认 · 1 条')
    expect(pendingRange.subtitle).toBe('10:00 组会')
  })

  it('previews three rows with start–end, truncates with +K, and tails pending', () => {
    setRuntimeI18nLocale('zh')
    const view = query({
      range: 'today',
      events: [
        event('1', '高数课', '2026-09-12T08:00:00', '2026-09-12T09:40:00'),
        event('2', '线代', '2026-09-12T10:00:00', null),
        event('3', '英语', '2026-09-12T14:00:00', '2026-09-12T15:00:00'),
        event('4', '班会', '2026-09-12T19:00:00', null)
      ],
      pending: [event('p1', '组会', '2026-09-12T20:00:00', null, 'pending'), event('p2', '汇报', '2026-09-12T21:00:00', null, 'pending')]
    })

    // 3 rows max, +1 for the fourth; a row without an end prints only its start.
    expect(view.subtitle).toBe('08:00–09:40 高数课 / 10:00 线代 / 14:00–15:00 英语 +1 · 待确认 2')
    // The card is an answer, not a dispatch.
    expect(view.title).not.toContain('Asked')
    expect(view.subtitle).not.toContain('未写结束')
  })

  it('reads 查看中 while the tool is still running', () => {
    setRuntimeI18nLocale('zh')
    const view = buildToolView(
      part({ args: { intent: 'query_agenda', range: 'today' }, result: undefined, toolName: 'vaelis_secretary_ask' }),
      ''
    )

    expect(view.title).toBe('查看中')
  })
})

describe('buildToolView vaelis_secretary_ask decide_pending (WP-SEC-VOCAB, 裁定 28.4)', () => {
  afterEach(() => {
    setRuntimeI18nLocale('en')
  })

  const decide = (result: Record<string, unknown>, args: Record<string, unknown> = {}) =>
    buildToolView(
      part({
        args: { intent: 'decide_pending', decision: 'confirm', ...args },
        result: { ok: true, intent: 'decide_pending', ...result },
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

  it('confirm / dismiss / dismissed-and-removed each read as done', () => {
    setRuntimeI18nLocale('zh')
    const confirmed = decide({
      decision: 'confirm',
      event: { id: 'e1', title: '组会', start_at: '2026-09-12T10:00:00', end_at: null, status: 'confirmed' }
    })

    expect(confirmed.title).toBe('已确认 · 组会 10:00')

    const dismissed = decide({
      decision: 'dismiss',
      event: { id: 'e1', title: '组会', start_at: '2026-09-12T10:00:00', end_at: null, status: 'pending' }
    })

    expect(dismissed.title).toBe('已忽略 · 组会 10:00')

    const removed = decide({
      decision: 'dismiss',
      deleted: true,
      event: { id: 'e2', title: '汇报', start_at: '2026-09-12T21:00:00', end_at: null, status: 'dismissed' }
    })

    expect(removed.title).toBe('已忽略并移除 · 汇报 21:00')
  })

  it('reads 处理中 while running and one-lines a failure with candidates expandable', () => {
    setRuntimeI18nLocale('zh')
    const running = buildToolView(
      part({
        args: { intent: 'decide_pending', decision: 'confirm' },
        result: undefined,
        toolName: 'vaelis_secretary_ask'
      }),
      ''
    )

    expect(running.title).toBe('处理中')

    const ambiguous = decide({
      ok: false,
      error: '多条匹配',
      candidates: [
        { id: 'a', title: '组会', start_at: '2026-09-12T10:00:00' },
        { id: 'b', title: '组会', start_at: '2026-09-12T15:00:00' }
      ]
    })

    // 失败走 failureRowLabel：命令/内部正文不常驻，候选进可展开体。
    expect(ambiguous.status).toBe('error')
    expect(ambiguous.title).not.toBe('多条匹配')
    expect(ambiguous.detail).toContain('多条匹配')
    expect(ambiguous.detail).toContain('- 组会 · 2026-09-12T10:00:00\n- 组会 · 2026-09-12T15:00:00')
  })
})
