import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

import { digest } from '../hooks/issue-pane'

const TOOL = 'mcp__hga__step'
const ISSUE = 'acme/web-app#18'

// Stands in for the engine: the session starts, the tool and the command can be registered, pane opens and closes
// are collected, and an empty box is drawn in place of the footer.
function engine(on: On) {
  const opened: string[] = []
  const closed: string[] = []
  const clock = mock.clock(on, { now: 1_000_000 })
  on('session.start', ($, e) => e as never)
  on('tool.register', () => ({ value: undefined }) as never)
  on('command.register', ($, e) => ({ value: { command: e.name } }) as never)
  on('ui.open', ($, e) => { opened.push(e.title ?? e.id); return { value: true } as never })
  on('ui.close', ($, e) => { closed.push(e.id); return { value: undefined } as never })
  on('ui.render', { component: 'SessionMode' }, ($, e) => h($.ui.resolve(e).Box, { key: 'engine' }) as never)
  return { opened, closed, clock }
}

// The record `HGA evidence` writes next to the state file (hga_issue.py); the step tool reads it before a done of
// steps 3, 5, 7, 8 and 9. passing(): an ok entry written at `at` (default: long after every test clock), with its digest.
const LATER = Date.parse('2100-01-01T00:00:00Z')
const entry = (step: number, fields: Record<string, unknown> = {}, issue = ISSUE) => {
  const e = { ok: true, at: new Date(LATER).toISOString(), facts: [], ...fields }
  return { ...e, digest: digest(issue, step, e) }
}
const passing = (...steps: number[]) => Object.fromEntries(steps.map(n => [String(n), entry(n)]))
// fs.read answers the evidence record from `steps()` (null: there is none); other paths do not exist.
function evidence(on: On, steps: () => Record<string, unknown> | null) {
  on('fs.read', ($, e) => {
    const s = steps()
    if (!String(e.path).replaceAll('\\', '/').endsWith('/home/test/.claude/hga/issue/acme-web-app-18.evidence.json') || s === null) {
      throw new Error(`ENOENT: ${String(e.path)}`)
    }
    return { value: JSON.stringify({ schema: 1, issue: ISSUE, gates: [], reviews: [], steps: s }) } as never
  })
}

const start = ($: Engine) => $.session.start({ cwd: '/tmp', surface: null, isInteractive: false } as never)
const step = ($: Engine, args: Record<string, unknown>) =>
  $.tool.call({ tool: TOOL, ...args } as never) as Promise<{ result: string }>
const pane = async ($: Engine) =>
  JSON.stringify(
    await $.ui.render({
      surface: 'desktop', component: 'Pane', requestId: 'hga-issue',
      props: { title: 'x', isFocused: false, bodyColumns: 70 },
    } as never),
  )

test('a step report is drawn: mark, color, evidence, counter; the first report opens the pane', async ($, on) => {
  const s = engine(on)
  await start($)
  expect((await step($, { issue: ISSUE, verb: 'fix', step: 0, state: 'done', evidence: 'repo-check OK' })).result)
    .toBe(`${ISSUE}: 1/13 done.`)
  await step($, { issue: ISSUE, step: 6, state: 'skipped', evidence: 'no VPN' })
  await step($, { issue: ISSUE, step: 8, state: 'in_progress', evidence: 'round 3 · 2 P2' })
  expect(s.opened).toEqual(['🎫 web-app#18'])

  const drawn = await pane($)
  expect(drawn).toContain('web-app#18 · fix')
  expect(drawn).toContain('2/13 · ◷')
  // Four section rows with a summary; only the running section (Review) is open, with its evidence.
  expect(drawn).toContain('Prepare')
  expect(drawn).toContain('1/5 ›')
  expect(drawn).toContain('1/2 · 1 skipped ›')
  expect(drawn).toContain('0/2 ⌄')
  expect(drawn).toContain('"Review"')
  expect(drawn).toContain('round 3 · 2 P2')
  expect(drawn).not.toContain('repo-check OK')
  expect(drawn).not.toContain('no VPN')
  // One accent color (suggestion) and the warning.
  expect(drawn).toContain('"color":"suggestion"')
  expect(drawn).toContain('"color":"warning"')
  // Section icons: ☰ Prepare, ✎ Build, ⌕ Review, ⚑ Finish.
  for (const icon of ['☰', '✎', '⌕', '⚑']) expect(drawn).toContain(`" ${icon}"`)
  // Thick bar: full block characters; Prepare's 1/5 is one accent block.
  expect(drawn).toContain('{"color":"suggestion"},"children":["█"]')
})

test('not_applicable: needs the risk line as evidence, counts as finished, shown as n/a with its own mark', async ($, on) => {
  engine(on)
  await start($)
  expect((await step($, { issue: ISSUE, step: 6, state: 'not_applicable' })).result).toContain('the `HGA risk` line')
  await step($, { issue: ISSUE, verb: 'fix', step: 0, state: 'done', evidence: 'repo-check OK' })
  expect((await step($, { issue: ISSUE, step: 6, state: 'not_applicable', evidence: 'Risk: low · every file matches a low pattern' })).result)
    .toBe(`${ISSUE}: 2/13 done.`)
  await step($, { issue: ISSUE, step: 5, state: 'in_progress', evidence: 'gate running' })
  const drawn = await pane($)
  expect(drawn).toContain('1/2 · 1 n/a ⌄')
  expect(drawn).toContain('" –"')
  expect(drawn).toContain('Risk: low')
  // not a warning: the Build section's icon is the accent (running), not the warning color
  expect(drawn).not.toContain('"color":"warning"')
})

test('clicking a section name opens and closes it', async ($, on) => {
  engine(on)
  await start($)
  await step($, { issue: ISSUE, verb: 'fix', step: 0, state: 'done', evidence: 'repo-check OK' })
  await step($, { issue: ISSUE, step: 8, state: 'in_progress', evidence: 'round 3 · 2 P2' })
  const ui = await $.ui.mount({ plugin: 'hga', surface: 'desktop', component: 'Pane', requestId: 'hga-issue', props: { title: 'x', isFocused: false, bodyColumns: 70 } } as never)
  await ui.press({ key: 'section-Prepare' })
  expect(await pane($)).toContain('repo-check OK')
  // A finished step's check mark is green.
  expect(await pane($)).toContain('{"color":"success","dimColor":false},"children":[" ✓"]')
  await ui.press({ key: 'section-Review' })
  expect(await pane($)).not.toContain('round 3 · 2 P2')
  await ui.press({ key: 'section-Prepare' })
  expect(await pane($)).not.toContain('repo-check OK')
  await ui.unmount()
})

test('invalid input gets an error and writes no state', async ($, on) => {
  engine(on)
  await start($)
  expect((await step($, { issue: ISSUE, step: 13, state: 'done' })).result).toStartWith('Invalid input')
  expect((await step($, { issue: ISSUE, step: 2, state: 'finished' })).result).toStartWith('Invalid input')
  expect((await step($, { issue: '', step: 2, state: 'done' })).result).toStartWith('Invalid input')
  expect(await pane($)).toMatch(/No issue is running.*\/triage-pane/)
})

test('a done or skipped step needs evidence; a finished step reported again keeps its own', async ($, on) => {
  engine(on)
  mock.env(on, { HOME: '/home/test' })
  evidence(on, () => passing(5))
  await start($)
  expect((await step($, { issue: ISSUE, step: 0, state: 'done' })).result).toStartWith('Invalid input')
  expect((await step($, { issue: ISSUE, step: 0, state: 'done', evidence: '   ' })).result).toStartWith('Invalid input')
  expect((await step($, { issue: ISSUE, step: 6, state: 'skipped' })).result).toContain('the reason')
  expect(await pane($)).toMatch(/No issue is running/)
  expect((await step($, { issue: ISSUE, step: 5, state: 'in_progress' })).result).toBe(`${ISSUE}: 0/13 done.`)
  // in_progress evidence is not a finished step's evidence
  expect((await step($, { issue: ISSUE, step: 5, state: 'done' })).result).toStartWith('Invalid input')
  await step($, { issue: ISSUE, step: 5, state: 'done', evidence: '12 passed' })
  expect((await step($, { issue: ISSUE, step: 5, state: 'done', checks: ['Rollback tested'] })).result).toContain('1/13 done')
  const ui = await mount($)
  await ui.press({ key: 'section-Build' })
  expect(await pane($)).toContain('12 passed')
  await ui.unmount()
})

test('a different issue starts a new pane', async ($, on) => {
  const s = engine(on)
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  await step($, { issue: 'acme/api#42', step: 1, state: 'in_progress' })
  const drawn = await pane($)
  expect(drawn).toContain('api#42')
  expect(drawn).not.toContain('web-app#18')
  expect(drawn).toContain('"0/13 · ◷')
  expect(s.opened.length).toBe(2)
})

test('the elapsed time updates every minute', async ($, on) => {
  const s = engine(on)
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'in_progress' })
  expect(await pane($)).toContain('◷ 0:00')
  await s.clock.advance(61 * 60_000)
  expect(await pane($)).toContain('◷ 1:01')
})

// A finished issue's (step 12 done) clock stops at the last report, as on the triage panel.
test("a finished issue's clock stops at the last report", async ($, on) => {
  const s = engine(on)
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  await s.clock.advance(15 * 60_000)
  await step($, { issue: ISSUE, step: 12, state: 'done', evidence: 'ok' })
  await s.clock.advance(30 * 60_000)
  expect(await pane($)).toContain('◷ 0:15')
})

test('/issue-pane opens and closes, even without an issue', async ($, on) => {
  const s = engine(on)
  await start($)
  expect((await $.command.run({ command: 'issue-pane', args: '' } as never)).text).toBe('Issue pane opened.')
  expect(s.opened).toEqual(['🎫 Issue'])
  expect((await $.command.run({ command: 'issue-pane', args: '' } as never)).text).toBe('Issue pane closed.')
  expect(s.closed).toEqual(['hga-issue'])
})

const footer = ($: Engine) =>
  $.ui.mount({ plugin: 'hga', surface: 'desktop', component: 'SessionMode', props: { modes: [] } })

test('footer: only the built-in drawing without an issue; with one, a progress button that opens and closes', async ($, on) => {
  const s = engine(on)
  await start($)
  let ui = await footer($)
  expect(await ui.find({ key: 'engine' })).toBeDefined()
  expect(await ui.find({ type: 'Button' })).toBeUndefined()
  await ui.unmount()

  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  expect(s.opened.length).toBe(1)
  ui = await footer($)
  expect(await ui.find({ key: 'engine' })).toBeDefined()
  expect((await ui.find({ type: 'Button' }))?.text).toBe('🎫 web-app#18 1/13')

  await ui.press({ key: 'issue-pane' })
  expect(s.closed).toEqual(['hga-issue'])
  await ui.press({ key: 'issue-pane' })
  expect(s.opened.length).toBe(2)
  await ui.unmount()
})

test('after closing, further reports do not reopen it; a new issue does', async ($, on) => {
  const s = engine(on)
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  await $.command.run({ command: 'issue-pane', args: '' } as never)
  await step($, { issue: ISSUE, step: 1, state: 'done', evidence: 'ok' })
  expect(s.opened.length).toBe(1)
  await step($, { issue: 'acme/api#42', step: 0, state: 'in_progress' })
  expect(s.opened.length).toBe(2)
})

test('counts from the given start (late report); ignores a future or invalid start', async ($, on) => {
  const s = engine(on)
  await s.clock.set(Date.parse('2026-10-13T10:00:00+02:00'))
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok', started_at: '2026-10-13T08:53:00+02:00' })
  expect(await pane($)).toContain('◷ 1:07')

  const future = await step($, { issue: ISSUE, step: 1, state: 'done', evidence: 'ok', started_at: '2026-10-13T11:00:00+02:00' })
  expect(future.result).toContain('ignored')
  expect(await pane($)).toContain('◷ 1:07')

  const invalid = await step($, { issue: ISSUE, step: 2, state: 'done', evidence: 'ok', started_at: 'yesterday morning' })
  expect(invalid.result).toContain('ignored')
  expect(await pane($)).toContain('◷ 1:07')
})

test('every report writes the shared state file for the triage panel; a write error does not break it', async ($, on) => {
  engine(on)
  const writes: { path: string; text: string }[] = []
  mock.env(on, { HOME: '/home/test', CLAUDE_CODE_HOST_SESSION_ID: 'local_test' })
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('fs.write', ($, e) => { writes.push(e as never); return { value: undefined } as never })
  await start($)
  await step($, { issue: ISSUE, verb: 'fix', step: 0, state: 'done', evidence: 'ok' })
  await step($, { issue: ISSUE, step: 1, state: 'in_progress' })
  expect(writes.length).toBe(2)
  // On Windows the engine resolves the faked POSIX home to an absolute path: C:\home\test\...
  expect(writes[1]!.path.replaceAll('\\', '/').endsWith('/home/test/.claude/hga/issue/acme-web-app-18.json')).toBe(true)
  const file = JSON.parse(writes[1]!.text)
  expect(file.issue).toBe(ISSUE)
  expect(file.session).toBe('sess-1')
  // the desktop session id: the triage panel jumps to this session with it
  expect(file.desktop).toBe('local_test')
  expect(file.steps[1].state).toBe('in_progress')
  expect(typeof file.updatedAt).toBe('number')
})

test('without a file system the report works the same', async ($, on) => {
  engine(on)
  await start($)
  expect((await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })).result).toBe(`${ISSUE}: 1/13 done.`)
})

// After a plugin update or restart the session's memory is empty, the state file remains.
test("the issue comes back from the session's own state file; not from another session's", async ($, on) => {
  const s = engine(on)
  const finishedIssue = (issue: string, session: string, updatedAt: number) => ({
    issue, verb: 'fix', startedAt: 0, updatedAt, session,
    steps: Array.from({ length: 13 }, () => ({ state: 'done', evidence: 'ok' })),
  })
  const files: Record<string, object> = {
    'acme-web-app-27.json': finishedIssue('acme/web-app#27', 'sess-1', 500),
    'acme-web-app-29.json': finishedIssue('acme/web-app#29', 'sess-2', 900),
  }
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('fs.exists', () => ({ value: true }) as never)
  on('fs.list', () => ({ value: Object.keys(files).map(name => ({ name, kind: 'file' })) }) as never)
  on('fs.read', ($, e) => ({ value: JSON.stringify(files[String(e.path).replaceAll('\\', '/').split('/').pop()!]) }) as never)
  await start($)
  const drawn = await pane($)
  expect(drawn).toContain('web-app#27')
  expect(drawn).toContain('13/13')
  expect(drawn).toContain('◷ 0:00') // finished issue: the clock stands at the last report (updatedAt: 500 ms)
  expect(drawn).not.toContain('#29')
  expect((await $.command.run({ command: 'issue-pane', args: '' } as never)).text).toBe('Issue pane opened.')
  expect(s.opened.at(-1)).toContain('web-app#27')
})

test('without its own state file the pane stays empty', async ($, on) => {
  engine(on)
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-9' }) as never)
  on('fs.exists', () => ({ value: false }) as never)
  await start($)
  expect(await pane($)).toMatch(/No issue is running/)
})

const mount = ($: Engine) =>
  $.ui.mount({ plugin: 'hga', surface: 'desktop', component: 'Pane', requestId: 'hga-issue', props: { title: 'x', isFocused: false, bodyColumns: 50 } } as never)

// A long evidence is cut on a narrow pane; a double click on the row opens it to several lines, the next one closes it.
test('double click on a row: the evidence wraps, another double click restores it; a single click does not toggle', async ($, on) => {
  const s = engine(on)
  await start($)
  const long = 'launch.json not needed (Bash path); worktree + local branch deleted; the remote branch stays until merge'
  await step($, { issue: ISSUE, step: 10, state: 'in_progress', evidence: long })
  const ui = await mount($)
  const draw = async () =>
    JSON.stringify(await $.ui.render({ surface: 'desktop', component: 'Pane', requestId: 'hga-issue', props: { title: 'x', isFocused: false, bodyColumns: 50 } } as never))
  expect(await draw()).not.toContain(long)
  await ui.press({ key: 'row-10' })
  await s.clock.advance(1_000)
  await ui.press({ key: 'row-10' })
  expect(await draw()).not.toContain(long)
  await ui.press({ key: 'row-10' })
  expect(await draw()).toContain(`{"dimColor":true,"wrap":"wrap"},"children":["${long}"]`)
  await s.clock.advance(1_000)
  await ui.press({ key: 'row-10' })
  await ui.press({ key: 'row-10' })
  expect(await draw()).not.toContain(long)
  await ui.unmount()
})

test('manual review: the list under Review, tickable, a same-text point keeps its tick, cut above 13', async ($, on) => {
  engine(on)
  const writes: { path: string; text: string }[] = []
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('fs.write', ($, e) => { writes.push(e as never); return { value: undefined } as never })
  evidence(on, () => passing(7, 8))
  await start($)
  const r = await step($, { issue: ISSUE, step: 7, state: 'done', evidence: 'ok', checks: ['Migration is backward compatible', '  Permission:   admin only  ', ''] })
  expect(r.result).toBe(`${ISSUE}: 1/13 done. Manual review: 0/2 ticked.`)
  let drawn = await pane($)
  expect(drawn).toContain('Manual review')
  expect(drawn).toContain('0/2 ⌄')
  expect(drawn).toContain('Permission: admin only')
  // between the Review and the Finish sections
  expect(drawn.indexOf('section-Review')).toBeGreaterThan(-1)
  expect(drawn.indexOf('section-Manual review')).toBeGreaterThan(drawn.indexOf('section-Review'))
  expect(drawn.indexOf('section-Manual review')).toBeLessThan(drawn.indexOf('section-Finish'))

  const ui = await mount($)
  await ui.press({ key: 'check-1' })
  drawn = await pane($)
  expect(drawn).toContain('1/2 ⌄')
  expect(drawn).toContain('"strikethrough":true')
  expect(JSON.parse(writes.at(-1)!.text).checks[1]).toEqual({ text: 'Permission: admin only', done: true })
  await ui.unmount()

  // A new list: a point with the same text keeps its tick, the others are new; cut above 13.
  const more = ['Permission: admin only', ...Array.from({ length: 14 }, (_, k) => `point ${k}`)]
  const r2 = await step($, { issue: ISSUE, step: 8, state: 'done', evidence: 'ok', checks: more })
  expect(r2.result).toContain('Manual review: 1/13 ticked.')
  expect(r2.result).toContain('Only the first 13 points')
  expect(await pane($)).not.toContain('Migration')

  expect((await step($, { issue: ISSUE, step: 8, state: 'done', checks: 'one string' })).result).toStartWith('Invalid input')
})

test('manual review: an empty list = no highlighted point; without a list there is no section', async ($, on) => {
  engine(on)
  mock.env(on, { HOME: '/home/test' })
  evidence(on, () => passing(7))
  await start($)
  await step($, { issue: ISSUE, step: 7, state: 'done', evidence: 'ok' })
  expect(await pane($)).not.toContain('Manual review')
  await step($, { issue: ISSUE, step: 7, state: 'done', checks: [] })
  const ui = await mount($)
  await ui.press({ key: 'section-Manual review' })
  expect(await pane($)).toContain('no highlighted manual review point')
  await ui.unmount()
})

// The metrics record (hga_issue.py metrics-record) reads the step times and the five-hour snapshots from here.
test('step times: in_progress stamps the start, done the end and keeps the start; a repeat keeps the first start', async ($, on) => {
  const s = engine(on)
  const writes: { path: string; text: string }[] = []
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('fs.write', ($, e) => { writes.push(e as never); return { value: undefined } as never })
  evidence(on, () => passing(5))
  await s.clock.set(Date.parse('2026-10-13T10:00:00Z'))
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'in_progress', started_at: '2026-10-13T09:58:00Z' })
  await s.clock.advance(60_000)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  await step($, { issue: ISSUE, step: 5, state: 'in_progress' })
  await s.clock.advance(10 * 60_000)
  await step($, { issue: ISSUE, step: 5, state: 'in_progress', evidence: '3 new cases' })
  await s.clock.advance(5 * 60_000)
  await step($, { issue: ISSUE, step: 5, state: 'done', evidence: '12 passed' })
  await step($, { issue: ISSUE, step: 6, state: 'skipped', evidence: 'no browser' })
  const file = JSON.parse(writes.at(-1)!.text)
  // step 0 starts at the given started_at, not at the report
  expect(file.steps[0]).toEqual({ state: 'done', evidence: 'ok', startedAt: Date.parse('2026-10-13T09:58:00Z'), endedAt: Date.parse('2026-10-13T10:01:00Z') })
  expect(file.steps[5].startedAt).toBe(Date.parse('2026-10-13T10:01:00Z'))
  expect(file.steps[5].endedAt).toBe(Date.parse('2026-10-13T10:16:00Z'))
  // skipped without an in_progress: an end, no start
  expect(file.steps[6].startedAt).toBeUndefined()
  expect(file.steps[6].endedAt).toBe(Date.parse('2026-10-13T10:16:00Z'))

  // opened again: the first start stays, the end is gone until it is done again
  await s.clock.advance(60_000)
  await step($, { issue: ISSUE, step: 5, state: 'in_progress', evidence: 'review fix' })
  const again = JSON.parse(writes.at(-1)!.text).steps[5]
  expect(again.startedAt).toBe(Date.parse('2026-10-13T10:01:00Z'))
  expect(again.endedAt).toBeUndefined()
  // a finished step reported again (amended evidence) keeps its end
  await step($, { issue: ISSUE, step: 6, state: 'skipped', evidence: 'no browser; NOT VERIFIED' })
  expect(JSON.parse(writes.at(-1)!.text).steps[6].endedAt).toBe(Date.parse('2026-10-13T10:16:00Z'))
})

test('an older state file without step times still restores and takes new reports', async ($, on) => {
  engine(on)
  const writes: { path: string; text: string }[] = []
  const old = { issue: ISSUE, verb: 'fix', startedAt: 0, updatedAt: 500, session: 'sess-1', steps: [{ state: 'done', evidence: 'ok' }, ...Array(12).fill(null)] }
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('fs.exists', () => ({ value: true }) as never)
  on('fs.list', () => ({ value: [{ name: 'acme-web-app-18.json', kind: 'file' }] }) as never)
  on('fs.read', () => ({ value: JSON.stringify(old) }) as never)
  on('fs.write', ($, e) => { writes.push(e as never); return { value: undefined } as never })
  await start($)
  expect(await pane($)).toContain('1/13')
  expect((await step($, { issue: ISSUE, step: 1, state: 'in_progress' })).result).toBe(`${ISSUE}: 1/13 done.`)
  const file = JSON.parse(writes.at(-1)!.text)
  expect(file.steps[0]).toEqual({ state: 'done', evidence: 'ok' })
  expect(typeof file.steps[1].startedAt).toBe('number')
  expect(file.fiveHour).toBeUndefined()
})

test("five-hour usage: snapshot at step 0's start and at step 12 done, account-wide; none without rate limit data", async ($, on) => {
  const s = engine(on)
  const writes: { path: string; text: string }[] = []
  let pct = 21.5
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 1 }, rateLimits: [{ kind: 'five_hour', percentUsed: pct }] } }) as never)
  on('fs.write', ($, e) => { writes.push(e as never); return { value: undefined } as never })
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'in_progress' })
  pct = 30
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  await step($, { issue: ISSUE, step: 12, state: 'in_progress' })
  expect(JSON.parse(writes.at(-1)!.text).fiveHour).toEqual({ start: { at: 1_000_000, percentUsed: 21.5 } })
  await s.clock.advance(60_000)
  pct = 48.25
  await step($, { issue: ISSUE, step: 12, state: 'done', evidence: 'https://x.test' })
  expect(JSON.parse(writes.at(-1)!.text).fiveHour).toEqual({
    start: { at: 1_000_000, percentUsed: 21.5 },
    end: { at: 1_060_000, percentUsed: 48.25 },
  })
  // step 12 reported again with the metrics record's path: the first end snapshot and end time stay
  await s.clock.advance(60_000)
  pct = 50
  await step($, { issue: ISSUE, step: 12, state: 'done', evidence: 'https://x.test · metrics/acme/web-app/18.json' })
  const file = JSON.parse(writes.at(-1)!.text)
  expect(file.fiveHour.end).toEqual({ at: 1_060_000, percentUsed: 48.25 })
  expect(file.steps[12].endedAt).toBe(1_060_000)
})

test('five-hour usage: no rate limit (API key) records nothing and the report works', async ($, on) => {
  engine(on)
  const writes: { path: string; text: string }[] = []
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: 'sess-1' }) as never)
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 1 }, rateLimits: [] } }) as never)
  on('fs.write', ($, e) => { writes.push(e as never); return { value: undefined } as never })
  await start($)
  expect((await step($, { issue: ISSUE, step: 0, state: 'in_progress' })).result).toBe(`${ISSUE}: 0/13 done.`)
  expect(JSON.parse(writes.at(-1)!.text).fiveHour).toBeUndefined()
})

// Steps 3, 5, 7, 8 and 9: done only with `HGA evidence`'s passing record, written after the step's start.
test('a machine-checked step without its record: done is rejected and nothing changes; skipped and n/a are not checked', async ($, on) => {
  engine(on)
  mock.env(on, { HOME: '/home/test' })
  evidence(on, () => null)
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  for (const n of [3, 5, 7, 8, 9]) {
    const r = (await step($, { issue: ISSUE, step: n, state: 'done', evidence: 'looks fine' })).result
    expect(r).toStartWith(`Invalid input: step ${n} (`)
    expect(r).toContain('no evidence record')
    expect(r).toContain(`HGA evidence acme/web-app 18 --step ${n}`)
  }
  expect((await step($, { issue: ISSUE, step: 1, state: 'in_progress' })).result).toBe(`${ISSUE}: 1/13 done.`)
  // the other steps, and skipped / not_applicable on any step, need no record
  expect((await step($, { issue: ISSUE, step: 4, state: 'done', evidence: 'nothing to decide' })).result).toBe(`${ISSUE}: 2/13 done.`)
  expect((await step($, { issue: ISSUE, step: 6, state: 'not_applicable', evidence: 'Risk: low' })).result).toBe(`${ISSUE}: 3/13 done.`)
  expect((await step($, { issue: ISSUE, step: 7, state: 'skipped', evidence: 'no PR: the user said so' })).result).toBe(`${ISSUE}: 4/13 done.`)
})

test('a record that is not ok, lacks the step, or was changed by hand is rejected; an ok and fresh one is accepted', async ($, on) => {
  engine(on)
  mock.env(on, { HOME: '/home/test' })
  let steps: Record<string, unknown> = {}
  evidence(on, () => steps)
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok' })
  await step($, { issue: ISSUE, step: 7, state: 'in_progress' })
  const done = async () => (await step($, { issue: ISSUE, step: 7, state: 'done', evidence: 'PR #7' })).result
  expect(await done()).toContain('the record has no step 7')
  steps = { '7': entry(7, { ok: false, facts: [{ name: 'pr_open', ok: true }, { name: 'pr_head_matches', ok: false, detail: 'PR head fffffff' }] }) }
  expect(await done()).toContain('failed: pr_head_matches')
  // the PR head changed by hand in an ok entry; an entry copied from another step or issue
  steps = { '7': { ...entry(7, { head: 'a'.repeat(40) }), head: 'b'.repeat(40) } }
  expect(await done()).toContain('changed by hand')
  steps = { '7': entry(3) }
  expect(await done()).toContain('changed by hand')
  steps = { '7': entry(7, {}, 'acme/web-app#19') }
  expect(await done()).toContain('changed by hand')
  steps = { '7': entry(7, { at: 'yesterday' }) }
  expect(await done()).toContain('invalid')
  expect(await pane($)).toContain('1/13')
  steps = { '7': entry(7, { head: 'a'.repeat(40), pr: 7 }) }
  expect(await done()).toBe(`${ISSUE}: 2/13 done.`)
})

test("a record older than the step's in_progress is rejected; a step opened again needs a newer one", async ($, on) => {
  const s = engine(on)
  mock.env(on, { HOME: '/home/test' })
  let at = '2026-10-13T09:59:59.999Z'
  evidence(on, () => ({ '5': entry(5, { at }) }))
  await s.clock.set(Date.parse('2026-10-13T10:00:00Z'))
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok', started_at: '2026-10-13T09:00:00Z' })
  await step($, { issue: ISSUE, step: 5, state: 'in_progress' })
  const done = async () => (await step($, { issue: ISSUE, step: 5, state: 'done', evidence: '148 passed' })).result
  expect(await done()).toContain("older than the step's start")
  at = '2026-10-13T10:00:00.000Z'
  await s.clock.advance(60_000)
  expect(await done()).toBe(`${ISSUE}: 2/13 done.`)
  // opened again (a live test fix round): the record of the first round no longer counts
  await s.clock.advance(60_000)
  await step($, { issue: ISSUE, step: 5, state: 'in_progress', evidence: 'live test: C2 ❌' })
  await s.clock.advance(60_000)
  expect(await done()).toContain("older than the step's start")
  at = '2026-10-13T10:03:00.000Z'
  expect(await done()).toBe(`${ISSUE}: 2/13 done.`)
})

test("a step reported done without an in_progress: the record must be newer than the issue's start", async ($, on) => {
  const s = engine(on)
  mock.env(on, { HOME: '/home/test' })
  let at = '2026-10-13T08:59:00.000Z'
  evidence(on, () => ({ '9': entry(9, { at }) }))
  await s.clock.set(Date.parse('2026-10-13T10:00:00Z'))
  await start($)
  await step($, { issue: ISSUE, step: 0, state: 'done', evidence: 'ok', started_at: '2026-10-13T09:00:00Z' })
  expect((await step($, { issue: ISSUE, step: 9, state: 'done', evidence: 'Done' })).result).toContain("older than the step's start")
  at = '2026-10-13T09:30:00.000Z'
  expect((await step($, { issue: ISSUE, step: 9, state: 'done', evidence: 'Done' })).result).toBe(`${ISSUE}: 2/13 done.`)
})

// The same vector as the Python test (test_evidence_digest_matches_the_pane): the two implementations agree.
test('the digest is the one HGA evidence writes', () => {
  const e = { ok: true, at: '2026-10-22T10:00:00.000+02:00', facts: [{ name: 'pr_open', ok: true, detail: 'PR #7 is OPEN · ő "q"\n' }], pr: 7, head: 'abc' }
  expect(digest('acme/web-app#18', 7, e)).toBe('fnv1a32:edb2961e')
  expect(digest('acme/web-app#18', 3, e)).toBe('fnv1a32:eda99bc2')
  expect(digest('acme/web-app#18', 7, { ...e, digest: 'ignored' })).toBe('fnv1a32:edb2961e')
})
