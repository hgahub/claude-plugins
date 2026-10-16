import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const TOOL = 'mcp__hga__intent'
const NAME = 'web-app-intent-xlsx-source'
const ISSUE = 'acme/web-app#351'
const T0 = Date.parse('2026-10-16T10:00:00+02:00')
const MIN = 60_000

// The issue pane's state file for the issue: 8 steps done, step 8 in progress, started 80 minutes ago.
const ISSUE_FILE = {
  issue: ISSUE, verb: 'implement', startedAt: T0 - 80 * MIN, updatedAt: T0 - 2 * MIN, session: 's9',
  steps: Array.from({ length: 13 }, (_, i) => (i < 8 ? { state: 'done', evidence: '' } : i === 8 ? { state: 'in_progress', evidence: '' } : null)),
}

// On Windows the engine gives back-slashed paths.
const slashed = (path: string) => path.replaceAll('\\', '/')
const baseName = (path: string) => slashed(path).split('/').pop() ?? ''

// Stands in for the engine. files: the intent's state files (~/.claude/hga/intent/); writes: what the mod writes.
function engine(on: On, opts: { issue?: boolean; files?: Record<string, object> } = {}) {
  const opened: string[] = []
  const registered: string[] = []
  const writes: { path: string; text: string }[] = []
  const files = opts.files ?? {}
  mock.clock(on, { now: T0 })
  mock.env(on, { HOME: '/home/test' })
  on('session.start', ($, e) => e as never)
  on('tool.register', ($, e) => { registered.push(e.name); return { value: undefined } as never })
  on('command.register', ($, e) => { registered.push(`/${e.name}`); return { value: { command: e.name } } as never })
  on('ui.open', ($, e) => { opened.push(e.title ?? e.id); return { value: true } as never })
  on('ui.close', () => ({ value: undefined }) as never)
  on('ui.render', { component: 'SessionMode' }, ($, e) => h($.ui.resolve(e).Box, { key: 'engine' }) as never)
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => h($.ui.resolve(e).Box, { key: 'engine-band' }) as never)
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('fs.exists', ($, e) => ({
    value: (opts.issue === true && e.path.endsWith('acme-web-app-351.json')) || (opts.files !== undefined && slashed(e.path).endsWith('/hga/intent')),
  }) as never)
  on('fs.list', () => ({ value: Object.keys(files).map(name => ({ name, kind: 'file' })) }) as never)
  on('fs.read', ($, e) => ({ value: JSON.stringify(files[baseName(e.path)] ?? ISSUE_FILE) }) as never)
  on('fs.write', ($, e) => { writes.push(e as never); return { value: undefined } as never })
  return { opened, registered, writes }
}

const start = ($: Engine) => $.session.start({ cwd: '/tmp', surface: null, isInteractive: false } as never)
const report = ($: Engine, args: Record<string, unknown>) =>
  $.tool.call({ tool: TOOL, intent: NAME, ...args } as never) as Promise<{ result: string }>
const BAND = { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 120 }
const band = async ($: Engine, props: Partial<typeof BAND> = {}) =>
  JSON.stringify(await $.ui.render({ surface: 'desktop', component: 'AbovePrompt', props: { ...BAND, ...props } } as never))
const pane = async ($: Engine) =>
  JSON.stringify(await $.ui.render({ surface: 'desktop', component: 'Pane', requestId: 'hga-intent', props: { title: 'x', isFocused: false, bodyColumns: 70 } } as never))

test('the tool and the command register; without an intent there is no band', async ($, on) => {
  const s = engine(on)
  await start($)
  expect(s.registered).toContain('intent')
  expect(s.registered).toContain('/intent-pane')
  expect(await band($)).toContain('engine-band')
})

test('a report fills the pane: stations, coverage, verdict; the first one opens it', async ($, on) => {
  const s = engine(on)
  await start($)
  await report($, { step: 0, state: 'done', evidence: 'web-app, export' })
  const r = await report($, { step: 2, state: 'in_progress', evidence: 'round 2', sections: { problem: 'done', outcome: 'done', criteria: 'partial' }, questions: 2, verdict: 'BLOCK' })
  expect(r.result).toBe(`${NAME}: full picture 2.5/8, 2 open questions.`)
  expect(s.opened).toEqual([`◎ ${NAME}`])
  const p = await pane($)
  expect(p).toContain('web-app, export')
  expect(p).toContain('round 2')
  expect(p).toContain('2.5/8 · 2 open questions')
  expect(p).toContain('"color":"error"},"children":["BLOCK"]')
  expect(p).toContain('Acceptance criteria')
})

test('the band shows the four stages, after the issue from the issue state file', async ($, on) => {
  engine(on, { issue: true })
  await start($)
  await report($, { step: 4, state: 'in_progress', sections: { problem: 'done' }, questions: 1, verdict: 'WARN' })
  let b = await band($)
  expect(b).toContain(`◎ ${NAME}`)
  expect(b).toContain('1/8 · 1 question · WARN')
  for (const name of ['Intent', 'Issue', 'Triage', 'Build']) expect(b).toContain(`"children":["${name}"]`)
  await report($, { step: 6, state: 'done' })
  await report($, { step: 7, state: 'done', issue: ISSUE })
  b = await band($)
  expect(b).toContain('#351')
  expect(b).toContain('8/13 · ◷ 1:20')
  expect(b).not.toContain('WARN')
})

test('during a survey and after ✕ the band is quiet; a new intent shows it again', async ($, on) => {
  engine(on)
  await start($)
  await report($, { step: 0, state: 'in_progress' })
  expect(await band($, { hasSurvey: true })).not.toContain(NAME)
  const ui = await $.ui.mount({ plugin: 'hga', surface: 'desktop', component: 'AbovePrompt', props: BAND } as never)
  await ui.press({ key: 'intent-hide' })
  await ui.unmount()
  expect(await band($)).not.toContain(NAME)
  await $.tool.call({ tool: TOOL, intent: 'api-intent-other' } as never)
  expect(await band($)).toContain('api-intent-other')
})

test('invalid input', async ($, on) => {
  engine(on)
  await start($)
  expect((await $.tool.call({ tool: TOOL, intent: ' ' } as never) as { result: string }).result).toContain('intent is required')
  expect((await report($, { step: 3 })).result).toContain('go together')
  expect((await report($, { step: 9, state: 'done' })).result).toContain('go together')
})

test('every report writes the state file with the session id', async ($, on) => {
  const s = engine(on)
  await start($)
  await report($, { step: 2, state: 'in_progress', questions: 3 })
  await report($, { sections: { problem: 'done' } })
  expect(s.writes.length).toBe(2)
  // The engine resolves the path against the plugin folder; the end is ours.
  expect(slashed(s.writes[1]!.path).endsWith(`/home/test/.claude/hga/intent/${NAME}.json`)).toBe(true)
  const file = JSON.parse(s.writes[1]!.text)
  expect(file.session).toBe('sess-1')
  expect(file.updatedAt).toBe(T0)
  expect(file.questions).toBe(3)
  expect(file.sections).toEqual({ problem: 'done' })
})

// After a plugin update or restart the memory is empty, the state file stays (as on the issue pane).
test("the intent comes back from the session's own most recent state file; not from another session's", async ($, on) => {
  const state = (intent: string, session: string, updatedAt: number) => ({
    intent, session, updatedAt, steps: [{ state: 'done', evidence: 'came back' }, null, null, null, null, null, null, null, null],
    sections: { problem: 'done' }, questions: 1, verdict: 'WARN', issue: null, file: null,
  })
  engine(on, {
    files: {
      'web-app-intent-old.json': state('web-app-intent-old', 'sess-1', T0 - 60 * MIN),
      [`${NAME}.json`]: state(NAME, 'sess-1', T0 - 5 * MIN),
      'api-intent-foreign.json': state('api-intent-foreign', 'sess-9', T0),
    },
  })
  await start($)
  const b = await band($)
  expect(b).toContain(`◎ ${NAME}`)
  expect(b).toContain('1/8 · 1 question · WARN')
  expect(await pane($)).toContain('came back')
})

test('without an own state file there is no band', async ($, on) => {
  engine(on, { files: { 'api-intent-foreign.json': { intent: 'api-intent-foreign', session: 'sess-9', updatedAt: T0, steps: [], sections: {} } } })
  await start($)
  expect(await band($)).toContain('engine-band')
})
