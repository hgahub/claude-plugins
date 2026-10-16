import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const T0 = Date.parse('2026-10-13T10:00:00+02:00')
const MIN = 60_000

const steps = (done: number, inProgress?: number) =>
  Array.from({ length: 13 }, (_, i) =>
    i < done ? { state: i === 6 ? 'skipped' : 'done', evidence: '' } : i === inProgress ? { state: 'in_progress', evidence: '' } : null,
  )

const FILES: Record<string, object> = {
  'acme-web-app-31.json': { issue: 'acme/web-app#31', verb: 'fix', startedAt: T0 - 102 * MIN, updatedAt: T0 - 5 * MIN, session: 's1', desktop: 'local_00000000-0000-0000-0000-000000000031', steps: steps(8, 8) },
  'acme-web-app-24.json': { issue: 'acme/web-app#24', verb: 'fix', startedAt: T0 - 300 * MIN, updatedAt: T0 - 120 * MIN, session: 's2', steps: steps(13) },
  'acme-web-app-23.json': { issue: 'acme/web-app#23', verb: 'implement', startedAt: T0 - 200 * MIN, updatedAt: T0 - 90 * MIN, session: 's3', steps: steps(5, 5) },
  'acme-api-42.json': { issue: 'acme/api#42', verb: 'fix', startedAt: T0, updatedAt: T0, session: 's4', steps: steps(2, 2) },
}

const NEXT = {
  repo: 'acme/web-app',
  project: 'Engineering',
  buckets: {
    ready: [{ number: 35, title: 'CSV export ignores the date filter', blockers: [] }],
    needs_human: [{ number: 40, title: 'Decide the log retention period', blockers: [] }],
    blocked: [{ number: 12, title: 'Cache invalidation', blockers: [9] }, { number: 17, title: 'Search pagination', blockers: [9] }],
    needs_info: [],
    in_progress: [{ number: 5, title: 'a', blockers: [] }, { number: 7, title: 'b', blockers: [] }],
    in_review: [],
    untriaged: [{ number: 44, title: 'x', blockers: [] }, { number: 45, title: 'y', blockers: [] }],
  },
  off_board: 0,
}

const CONFIG = { parallel: { max_per_repo: 2, usage_ceiling_pct: 80 } }

const fileName = (path: string) => path.replaceAll('\\', '/').split('/').pop() ?? ''
type Run = { exitCode: number; stdout: string; stderr: string }

// Stands in for the engine: repository, home folder, state files, `HGA config`, `HGA next` and usage from memory.
function engine(on: On, opts: { next?: Run; config?: object; registerFails?: boolean; files?: Record<string, object>; store?: Record<string, unknown> } = {}) {
  const files = { ...FILES, ...opts.files }
  const runs: (readonly string[])[] = []
  const opened: string[] = []
  const toasts: string[] = []
  const registered: string[] = []
  const clock = mock.clock(on, { now: T0 })
  mock.store(on, opts.store)
  mock.env(on, { USERPROFILE: 'C:/Users/test', OS: 'Windows_NT' })
  on('session.start', ($, e) => e as never)
  on('command.register', ($, e) => {
    if (opts.registerFails) throw new Error(`"/${e.name}" refused`)
    registered.push(`/${e.name}`)
    return { value: { command: e.name } } as never
  })
  on('ui.toast', ($, e) => { toasts.push(e.text); return { value: undefined } as never })
  on('tool.register', ($, e) => { registered.push(e.name); return { value: undefined } as never })
  on('session.repo', () => ({ value: { root: 'C:/repo', remote: 'https://github.com/acme/web-app.git' } }) as never)
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 1 }, rateLimits: [{ kind: 'five_hour', percentUsed: 34.4 }] } }) as never)
  on('fs.exists', () => ({ value: true }) as never)
  on('fs.list', () => ({ value: Object.keys(files).map(name => ({ name, kind: 'file' })) }) as never)
  on('fs.read', ($, e) => ({ value: JSON.stringify(files[fileName(e.path)]) }) as never)
  on('process.run', ($, e) => {
    runs.push(e.argv)
    const ok = (stdout: string) => ({ exitCode: 0, stdout, stderr: '', isStdoutTruncated: false })
    if (e.argv.includes('config')) return { value: ok(JSON.stringify(opts.config ?? CONFIG)) } as never
    if (e.argv.includes('next')) return { value: opts.next ?? ok(JSON.stringify(NEXT)) } as never
    return { value: ok('') } as never
  })
  on('ui.open', ($, e) => { opened.push(e.title ?? e.id); return { value: { isPlaced: true } } as never })
  on('ui.close', () => ({ value: undefined }) as never)
  on('ui.render', { component: 'SessionMode' }, ($, e) => h($.ui.resolve(e).Box, { key: 'engine' }) as never)
  on('tool.call', { tool: 'Bash' }, () => ({ result: 'ok' }) as never)
  const nexts = () => runs.filter(r => r.includes('next'))
  return { runs, nexts, opened, toasts, clock, registered }
}

// The desktop app runs Claude Code in SDK mode: at start there is no surface, and it is not interactive.
const start = ($: Engine) => $.session.start({ cwd: 'C:/repo', surface: null, isInteractive: false } as never)
const triage = ($: Engine, args = '') => $.command.run({ command: 'triage-pane', args } as never) as Promise<{ text: string }>
const PANE_PROPS = { plugin: 'hga', surface: 'desktop', component: 'Pane', requestId: 'hga-triage', props: { title: 'x', isFocused: false, bodyColumns: 90 } }
const pane = async ($: Engine) => JSON.stringify(await $.ui.render(PANE_PROPS as never))
// Closed groups (finished, blocked, in progress, untriaged) open by clicking their names.
const openGroups = async ($: Engine, ...keys: string[]) => {
  const ui = await $.ui.mount(PANE_PROPS as never)
  for (const k of keys) await ui.press({ key: `group-${k}` })
  await ui.unmount()
}
const footer = ($: Engine) => $.ui.mount({ plugin: 'hga', surface: 'desktop', component: 'SessionMode', props: { modes: [] } })

test('registers on a desktop start too: the phase tool and /triage-pane exist', async ($, on) => {
  const s = engine(on)
  await start($)
  expect(s.registered).toContain('phase')
  expect(s.registered).toContain('/triage-pane')
})

test('quiet before activation: no footer button, no commands run', async ($, on) => {
  const s = engine(on)
  await start($)
  await s.clock.advance(10 * MIN)
  const ui = await footer($)
  expect(await ui.find({ type: 'Button' })).toBeUndefined()
  await ui.unmount()
  expect(s.runs.length).toBe(0)
  expect(await pane($)).toContain('has not run')
})

test("/triage-pane activates: the repo from the remote, HGA next's JSON, running issues from this repo's files", async ($, on) => {
  const s = engine(on)
  await start($)
  expect((await triage($)).text).toBe('Dashboard opened.')
  expect(s.opened).toEqual(['🧭 web-app'])
  expect(s.nexts()[0]!.slice(-3)).toEqual(['next', 'acme/web-app', '--json'])
  expect(s.nexts()[0]![1]!.replaceAll('\\', '/')).toMatch(/\/skills\/issue\/scripts\/hga_issue\.py$/)

  let drawn = await pane($)
  expect(drawn).toContain('"web-app · triage"')
  expect(drawn).toContain('5h 34% / 80%')
  // only the running #31 takes a slot; #24 is finished, #23 has been quiet for 90 minutes, api#42 is another repo
  expect(drawn).toContain('"Running implementations"')
  expect(drawn).toContain('"1/2"')
  expect(drawn).toContain('web-app#31')
  // the running issue's name is a button that jumps to its session (desktop id in the state file); otherwise plain text.
  const ui = await $.ui.mount(PANE_PROPS as never)
  expect(await ui.find({ key: 'jump-31' })).toBeDefined()
  expect(await ui.find({ key: 'jump-23' })).toBeUndefined()
  await ui.press({ key: 'jump-31' })
  await ui.unmount()
  expect(s.runs.at(-1)).toEqual(['rundll32', 'url.dll,FileProtocolHandler', 'claude://claude.ai/epitaxy/local_00000000-0000-0000-0000-000000000031'])
  expect(drawn).toContain('"8/13"')
  expect(drawn).toContain('"Review"')
  expect(drawn).toContain('◷ 1:42')
  expect(drawn).toContain('quiet for 90 min')
  expect(drawn).not.toContain('api#42')
  expect(drawn).toContain('"free slot"')
  // Finished is closed ("1 ›"), Ready and Needs a human are open, the rest closed
  expect(drawn).toContain('"Finished"')
  expect(drawn).not.toContain('web-app#24')
  expect(drawn).toContain('"Ready"')
  expect(drawn).toContain('"1 ⌄"')
  expect(drawn).toContain('#35 CSV export')
  expect(drawn).toContain('"Blocked"')
  expect(drawn).not.toContain('#12 ← #9')
  expect(drawn).not.toContain('#44 #45')
  expect(drawn).not.toContain('Needs info')
  await openGroups($, 'finished', 'blocked', 'untriaged')
  drawn = await pane($)
  expect(drawn).toContain('web-app#24')
  expect(drawn).toContain('{"color":"success","dimColor":false},"children":[" ✓"]')
  expect(drawn).toContain('#12 ← #9 · #17 ← #9')
  expect(drawn).toContain('#44 #45')
})

test('the parallel limit and the usage ceiling come from the configuration', async ($, on) => {
  engine(on, { config: { parallel: { max_per_repo: 3, usage_ceiling_pct: 60 } } })
  await start($)
  await triage($)
  const drawn = await pane($)
  expect(drawn).toContain('"1/3"')
  expect(drawn).toContain('5h 34% / 60%')
})

test('footer button: running and ready counts, a click closes and opens', async ($, on) => {
  const s = engine(on)
  await start($)
  await triage($)
  const ui = await footer($)
  expect(await ui.find({ key: 'engine' })).toBeDefined()
  expect((await ui.find({ type: 'Button' }))?.text).toBe('🧭 1/2 · ▶1')
  await ui.press({ key: 'triage-pane' })
  expect((await triage($)).text).toBe('Dashboard opened.')
  expect(s.opened.length).toBe(2)
  await ui.unmount()
})

test('reloads the issues after a label change; not after other commands', async ($, on) => {
  const s = engine(on)
  await start($)
  await triage($)
  await $.tool.call({ tool: 'Bash', command: 'git status' } as never)
  await s.clock.advance(0)
  expect(s.nexts().length).toBe(1)
  await $.tool.call({ tool: 'Bash', command: 'python3 /x/hga_issue.py triage-state acme/web-app 256 ready-for-agent' } as never)
  await s.clock.advance(0)
  expect(s.nexts().length).toBe(2)
})

test('refreshes running issues every minute and the issue list every five minutes', async ($, on) => {
  const s = engine(on)
  await start($)
  await triage($)
  expect(s.nexts().length).toBe(1)
  await s.clock.advance(4 * MIN)
  expect(s.nexts().length).toBe(1)
  await s.clock.advance(2 * MIN)
  expect(s.nexts().length).toBe(2)
})

test('if HGA next fails, the error shows, running issues still do', async ($, on) => {
  engine(on, { next: { exitCode: 1, stdout: '', stderr: 'gh: authentication required' } })
  await start($)
  await triage($)
  const drawn = await pane($)
  expect(drawn).toContain('HGA next: gh: authentication required')
  expect(drawn).toContain('web-app#31')
  expect(drawn).toContain('loading…')
})

test('loading the triage skill activates and opens; another skill does not', async ($, on) => {
  const s = engine(on)
  on('skill.prompt', ($, e) => ({ text: e.text }) as never)
  await start($)
  await $.skill.prompt({ skill: 'hga:issue', text: '…' })
  await s.clock.advance(0)
  expect(s.opened).toEqual([])
  expect((await $.skill.prompt({ skill: 'hga:triage', text: 'The skill text' })).text).toBe('The skill text')
  await s.clock.advance(0)
  expect(s.opened).toEqual(['🧭 web-app'])
  expect(s.nexts().length).toBe(1)
})

test('/triage-pane <owner/repo> switches to another repo; help for a wrong argument', async ($, on) => {
  const s = engine(on)
  await start($)
  expect((await triage($, 'acme/api')).text).toBe('Dashboard: acme/api.')
  expect(s.nexts()[0]!.slice(-3)).toEqual(['next', 'acme/api', '--json'])
  const drawn = await pane($)
  expect(drawn).toContain('"api · triage"')
  expect(drawn).toContain('api#42')
  expect(drawn).not.toContain('web-app#31')
  expect((await triage($, 'something else')).text).toBe('Usage: /triage-pane [refresh | owner/repo]')
})

test('if /triage-pane cannot be registered, a toast says so, and the clock and skill activation still work', async ($, on) => {
  const s = engine(on, { registerFails: true })
  on('skill.prompt', ($, e) => ({ text: e.text }) as never)
  await start($)
  // The issue and intent panes toast about their own commands too: the order is not fixed.
  expect(s.toasts.join(' | ')).toContain('/triage-pane could not be registered')
  await $.skill.prompt({ skill: 'hga:triage', text: 'x' })
  await s.clock.advance(0)
  expect(s.opened).toEqual(['🧭 web-app'])
  await s.clock.advance(6 * MIN)
  expect(s.nexts().length).toBe(2)
})

test('running HGA next turns the dashboard on if it is not active yet', async ($, on) => {
  const s = engine(on)
  await start($)
  await $.tool.call({ tool: 'Bash', command: 'python3 /x/hga_issue.py next acme/web-app' } as never)
  await s.clock.advance(0)
  expect(s.opened).toEqual(['🧭 web-app'])
})

test('a running issue is not ready; overrun in red; no slot after Done; marked under "In progress"', async ($, on) => {
  const run = (n: number, done: number) => ({ issue: `acme/web-app#${n}`, verb: 'fix', startedAt: T0 - 30 * MIN, updatedAt: T0 - 2 * MIN, session: `s${n}`, steps: steps(done, done) })
  const next = { ...NEXT, buckets: { ...NEXT.buckets, in_progress: [...NEXT.buckets.in_progress, { number: 17, title: 'c', blockers: [] }] } }
  const s = engine(on, {
    files: {
      'acme-web-app-35.json': run(35, 3),
      'acme-web-app-17.json': run(17, 5),
      'acme-web-app-12.json': run(12, 10),
    },
    next: { exitCode: 0, stdout: JSON.stringify(next), stderr: '' },
  })
  await start($)
  await triage($)
  const drawn = await pane($)
  // #31, #35, #17 take slots; #12 is past Done and does not count
  expect(drawn).toContain('3/2 · over the limit')
  expect(drawn).toContain('{"color":"error","dimColor":false},"children":[" ◐"]')
  // #12 after Done: dim ◐, takes no slot
  expect(drawn).toContain('{"dimColor":true},"children":[" ◐"]')
  expect(drawn).not.toContain('free slot')
  expect(drawn).toContain('"0 · 1 already running ⌄"')
  expect(drawn).toContain('#35 ◐ running · CSV export')
  expect(drawn).toContain('"3 · ◐ 1 live session ›"')
  await openGroups($, 'in_progress')
  expect(await pane($)).toContain('#5 #7 #17◐')
  const ui = await footer($)
  expect((await ui.find({ type: 'Button' }))?.text).toBe('🧭⚠ 3/2 · ▶0')
  await ui.unmount()
  expect(s.opened.length).toBe(1)
})

const phase = ($: Engine, args: Record<string, unknown>) =>
  $.tool.call({ tool: 'mcp__hga__phase', ...args } as never) as Promise<{ result: string }>

test('phase: branch, issue, step and the five verdicts; "preceded" has inverted colors', async ($, on) => {
  engine(on)
  await start($)
  await triage($)
  expect((await phase($, { branch: 'A', issue: 'acme/web-app#51', step: 'reproducing on the real modules' })).result)
    .toBe('Dashboard: A. Vet · acme/web-app#51.')
  await phase($, { branch: 'A', verdicts: { current: 'yes', complete: 'partly', preceded: 'no' } })
  await phase($, { branch: 'B', proposed: 'ready-for-agent', decisions: 1 })
  const drawn = await pane($)
  // the branch with its icon (✎ finalize), the five questions with marks: ✓ yes, ! partly, ○ not yet
  expect(drawn).toContain('" ✎"')
  expect(drawn).toContain('"Finalize"')
  expect(drawn).toContain('" · B · web-app#51"')
  expect(drawn).toContain('reproducing on the real modules')
  expect(drawn).toContain('"Still current"')
  expect(drawn).toContain('" · yes"')
  expect(drawn).toContain('{"color":"warning","dimColor":false},"children":[" !"]')
  expect(drawn).toContain('" · partly"')
  // Is it preceded by another issue? No → favorable, green check
  expect(drawn).toContain('" · no"')
  expect(drawn.match(/\{"color":"success","dimColor":false\},"children":\[" ✓"\]/g)?.length).toBe(3) // two for questions, one on the "Finished" header
  expect(drawn).toContain('{"dimColor":true},"children":[" ○"]')
  expect(drawn).toContain('→ ready-for-agent')
  expect(drawn).toContain('"1 open decision waiting for you"')
})

test('phase: another issue resets the verdicts; branch C has no question list; a wrong branch is an error', async ($, on) => {
  engine(on)
  await start($)
  await triage($)
  await phase($, { branch: 'A', issue: 'acme/web-app#51', verdicts: { current: 'no' }, proposed: 'needs-info' })
  await phase($, { branch: 'A', issue: 'acme/web-app#52' })
  let drawn = await pane($)
  expect(drawn).toContain('web-app#52')
  expect(drawn).not.toContain('needs-info')
  expect(drawn).not.toContain('" · no"')
  await phase($, { branch: 'C', step: 'HGA next, conflict check' })
  drawn = await pane($)
  expect(drawn).toContain('"Next issue"')
  expect(drawn).toContain('" ☰"')
  expect(drawn).not.toContain('Still current')
  expect((await phase($, { branch: 'X' })).result).toStartWith('Invalid input')
})

test('phase activates if the dashboard was not on yet', async ($, on) => {
  const s = engine(on)
  await start($)
  await phase($, { branch: 'C' })
  await s.clock.advance(0)
  expect(s.opened).toEqual(['🧭 web-app'])
})

test("finished and stalled issues' clocks stop; ✕ hides, the store remembers; a newer report brings it back", async ($, on) => {
  const s = engine(on)
  await start($)
  await triage($)
  // #24: started T0-300m, last report T0-120m → 3:00, still the same 30 minutes later
  await s.clock.advance(30 * MIN)
  await openGroups($, 'finished')
  let drawn = await pane($)
  expect(drawn).toContain('◷ 3:00')
  // #23 stalled: started T0-200m, last T0-90m → 1:50
  expect(drawn).toContain('◷ 1:50')
  const ui = await $.ui.mount(PANE_PROPS as never)
  // the running #31 has no ✕ button
  expect(await ui.find({ key: 'hide-31' })).toBeUndefined()
  await ui.press({ key: 'hide-24' })
  await ui.unmount()
  drawn = await pane($)
  expect(drawn).not.toContain('web-app#24')
  // the next minute's reading does not bring it back either
  await s.clock.advance(MIN)
  expect(await pane($)).not.toContain('web-app#24')
})

test('a hidden issue comes back if its state file is newer; starts from the store', async ($, on) => {
  const fresh = { issue: 'acme/web-app#24', verb: 'fix', startedAt: T0 - 300 * MIN, updatedAt: T0 - 10 * MIN, session: 's2', steps: steps(13) }
  const s = engine(on, {
    files: { 'acme-web-app-24.json': fresh },
    store: { hidden: { 'acme/web-app#24': T0 - 120 * MIN, 'acme/web-app#23': T0 - 90 * MIN } },
  })
  await start($)
  await triage($)
  await openGroups($, 'finished')
  const drawn = await pane($)
  expect(drawn).toContain('web-app#24')
  expect(drawn).not.toContain('web-app#23')
  expect(s.opened.length).toBe(1)
})

// A finished (13/13) issue no longer runs: it sits below the running ones, in its own list.
test('a finished issue sits below the running ones, in a separate collapsible "Finished" group', async ($, on) => {
  engine(on)
  await start($)
  await triage($)
  expect(await pane($)).toContain('"1 ›"')
  await openGroups($, 'finished')
  const drawn = await pane($)
  const at = (s: string) => drawn.indexOf(s)
  expect(drawn).toContain('"1 ⌄"')
  expect(at('"Finished"')).toBeGreaterThan(at('"Running implementations"'))
  expect(at('web-app#31')).toBeLessThan(at('"Finished"'))
  expect(at('web-app#23')).toBeLessThan(at('"Finished"'))
  expect(at('web-app#24')).toBeGreaterThan(at('"Finished"'))
  expect(at('web-app#24')).toBeLessThan(at('"Issues"'))
})
