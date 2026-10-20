import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, ResolveInput } from 'claude-code'

import type { Branch, Bucket, Issues, Limits, Phase, Question, Running, Verdict } from '../types'

const PANE = 'hga-triage'

const active = atom({ plugin: 'hga', key: 'active' } as const, false)
const open = atom({ plugin: 'hga', key: 'open' } as const, false)
const repo = atom({ plugin: 'hga', key: 'repo' } as const, null)
const issues = atom({ plugin: 'hga', key: 'issues' } as const, null)
const issuesAt = atom({ plugin: 'hga', key: 'issuesAt' } as const, 0)
const running = atom({ plugin: 'hga', key: 'running' } as const, [])
const usage = atom({ plugin: 'hga', key: 'usage' } as const, null)
const error = atom({ plugin: 'hga', key: 'error' } as const, null)
const now = atom({ plugin: 'hga', key: 'now' } as const, 0)
// Hidden issues (issue → the state file's update time back then); kept in $.store, across sessions too.
const hidden = atom({ plugin: 'hga', key: 'hidden' } as const, {})
// The triage's current branch and the five questions' verdicts: the model reports them with the phase tool.
const phase = atom({ plugin: 'hga', key: 'phase' } as const, null)
// Groups opened or closed by hand; null = default (Ready and Needs a human open, the rest closed).
const openGroups = atom({ plugin: 'hga', key: 'triageOpen' } as const, null)
// Limits from the configuration (`HGA config`); defaults until it has been read.
const limits = atom({ plugin: 'hga', key: 'limits' } as const, { maxPerRepo: 2, usageCeilingPct: 80 })
const DEFAULT_OPEN = ['ready', 'needs_human']

// After this many quiet minutes an unfinished implementation gets a "stalled?" mark and no longer takes a slot.
const STALLED_MIN = 60
const NEXT_MIN = 5
const DAY = 24 * 3600_000

// The issue skill's checklist (skills/issue/SKILL.md), in the same order as on the issue pane.
const STEPS = [
  'Start', 'Claim', 'In Progress', 'Worktree', 'Decisions', 'Build + tests',
  'Live test', 'PR', 'Review', 'Done', 'Cleanup', 'Knowledge', 'Report',
]
// As on the issue pane: one accent color (running), green for done, yellow for warnings, red only for errors
// and overruns; everything else dim, the symbol tells the state.
const ACCENT = 'suggestion'
const GROUPS: { key: Bucket; title: string; mark: string; color?: string }[] = [
  { key: 'ready', title: 'Ready', mark: '▶', color: ACCENT },
  { key: 'needs_human', title: 'Needs a human', mark: '?', color: 'warning' },
  { key: 'blocked', title: 'Blocked', mark: '✕' },
  { key: 'needs_info', title: 'Needs info', mark: '…' },
  { key: 'in_progress', title: 'In progress', mark: '◐' },
  { key: 'in_review', title: 'In review', mark: '⌕' },
  { key: 'untriaged', title: 'Untriaged', mark: '○' },
]
// The branch icon: assess, finalize (edit), next issue (list), launch.
const BRANCH_ICON: Record<Branch, string> = { A: '⌕', B: '✎', C: '☰', D: '▶' }
const MINI = 6
// A block character is about two columns wide in the desktop app's font: the bar's box must leave room for it,
// or it runs over the counter next to it.
const MINI_COLUMNS = MINI * 2 + 2
// Room for repo#number; longer names are cut with an ellipsis.
const NAME_COLUMNS = 14
const PHASE_TOOL = 'mcp__hga__phase'
const BRANCHES: Record<Branch, string> = { A: 'Assess', B: 'Finalize', C: 'Next issue', D: 'Launch' }
// Branch A's five questions (skills/triage/SKILL.md, A.2–A.6). "preceded" is inverted: there "yes" is unfavorable.
const QUESTIONS: { key: Question; title: string; inverted?: true }[] = [
  { key: 'current', title: 'Still current?' },
  { key: 'complete', title: 'Is the issue complete?' },
  { key: 'feasible', title: 'Feasible?' },
  { key: 'problem', title: 'Which problem does it solve?' },
  { key: 'preceded', title: 'Is it preceded by another issue?', inverted: true },
]
const VERDICTS: readonly string[] = ['yes', 'partly', 'no']
const STATE_COLOR: Record<string, string> = { 'ready-for-agent': 'success', 'ready-for-human': 'warning', 'needs-info': 'suggestion' }

const PHASE_SPEC = {
  name: 'phase',
  description:
    "The hga:triage run's current branch and verdicts, for the user's dashboard. Call it on every branch change (A assess, B finalize, " +
    'C next issue, D launch), at each verdict of branch A, at the proposed state, and when the number of open decisions changes. ' +
    'Give only the changed fields; a different issue id resets the verdicts.',
  isDeferred: false,
  inputSchema: {
    type: 'object',
    properties: {
      branch: { type: 'string', enum: ['A', 'B', 'C', 'D'], description: 'The triage branch.' },
      issue: { type: 'string', description: 'owner/repo#number, e.g. acme/web-app#42 (optional in branch C).' },
      step: { type: 'string', description: 'What it is doing now, in one short line.' },
      verdicts: {
        type: 'object',
        description: 'The five questions\' verdicts (yes | partly | no); only those answered so far.',
        properties: Object.fromEntries(QUESTIONS.map(k => [k.key, { type: 'string', enum: ['yes', 'partly', 'no'] }])),
      },
      proposed: { type: 'string', enum: ['ready-for-agent', 'ready-for-human', 'needs-info'], description: 'Proposed or applied state label.' },
      decisions: { type: 'integer', minimum: 0, description: 'Number of open decisions waiting for the user.' },
    },
    required: ['branch'],
  },
}

export function repoOf(remote: string | null | undefined): string | null {
  const m = remote?.match(/github\.com[:/]([^/\s]+)\/([^/\s]+?)(?:\.git)?\/?$/)
  return m ? `${m[1]}/${m[2]}` : null
}

const prefix = (r: string) => `${r.replace(/[^A-Za-z0-9_-]+/g, '-')}-`
// owner/repo#n → repo#n: the pane is per repository, the owner adds nothing.
const short = (id: string) => id.replace(/^[^/#\s]+\//, '')
const cut = (s: string, n: number) => (s.length <= n ? s : `${s.slice(0, Math.max(0, n - 1))}…`)
const finishedSteps = (f: Running) => f.steps.filter(l => l !== null && l.state !== 'in_progress').length
const finished = (f: Running) => f.steps[12]?.state === 'done'
const stalled = (f: Running, t: number) => !finished(f) && t - f.updatedAt > STALLED_MIN * 60_000
// Whether the session is still alive (marked `◐ running` in the issue lists).
const alive = (f: Running, t: number) => !finished(f) && !stalled(f, t)
// After Done (step 9) only cleanup, knowledge and the report follow: it no longer takes a slot (closer to D.1's count).
const closed = (f: Running) => f.steps[9]?.state === 'done'
const occupies = (f: Running, t: number) => alive(f, t) && !closed(f)
const numberOf = (f: Running) => Number(f.issue.split('#').pop())
// The clock of a finished or stalled issue stops at the last report.
const elapsed = (f: Running, t: number) => (alive(f, t) ? Math.max(t, f.updatedAt) : f.updatedAt) - f.startedAt
const isHidden = (f: Running, h: Record<string, number>) => h[f.issue] !== undefined && f.updatedAt <= h[f.issue]!

export function duration(ms: number): string {
  const min = Math.max(0, Math.floor(ms / 60_000))
  return `${Math.floor(min / 60)}:${String(min % 60).padStart(2, '0')}`
}

// The current station: the one in progress, else the one after the last reported.
function currentStep(f: Running): string {
  const i = f.steps.findIndex(l => l?.state === 'in_progress')
  if (i >= 0) return STEPS[i]!
  const last = f.steps.reduce((acc, l, k) => (l === null ? acc : k), -1)
  return last >= STEPS.length - 1 ? 'done' : STEPS[last + 1]!
}

// Jump to a running issue's session. The desktop app is a remote surface: its Link draws only https: and turns
// claude:// into text, so the operating system opens the link, like a claude:// link clicked from outside.
// Only a local_… id is accepted: the file does not supply a URL.
const DESKTOP = /^local_[0-9a-f-]{36}$/
async function jumpTo($: EngineInterface, desktop: string): Promise<void> {
  if (!DESKTOP.test(desktop)) return
  const url = `claude://claude.ai/epitaxy/${desktop}`
  if ((await $.env.get('OS')) === 'Windows_NT') {
    await $.process.run(['rundll32', 'url.dll,FileProtocolHandler', url], { timeoutMs: 10_000 }).catch(() => undefined)
    return
  }
  const res = await $.process.run(['open', url], { timeoutMs: 10_000 }).catch(() => null)
  if (res === null || res.exitCode !== 0) await $.process.run(['xdg-open', url], { timeoutMs: 10_000 }).catch(() => undefined)
}

async function home($: EngineInterface): Promise<string | null> {
  return (await $.env.get('USERPROFILE')) || (await $.env.get('HOME')) || null
}

// Windows' App Execution Alias for a Python that is not installed: it runs, exits non-zero and prints this.
const STORE_STUB = 'Python was not found'

// Runs the helper script with the first Python that works (python3 on macOS/Linux, python on Windows).
async function helper($: EngineInterface, args: string[], timeoutMs: number) {
  const script = `${$.plugin.root}/skills/issue/scripts/hga_issue.py`
  let last: unknown = null
  for (const py of ['python3', 'python']) {
    try {
      const res = await $.process.run([py, script, ...args], { timeoutMs })
      if (res.exitCode !== 0 && `${res.stderr}${res.stdout}`.includes(STORE_STUB)) {
        last = new Error(`${py}: ${res.stderr.trim() || res.stdout.trim()}`)
        continue
      }
      return res
    } catch (err) {
      last = err
    }
  }
  throw last instanceof Error ? last : new Error('no Python found (python3 / python)')
}

// The issue pane's state files for this repository's issues: unfinished ones for a week, finished ones for a day.
async function loadRunning($: EngineInterface): Promise<void> {
  const r = await read($, repo)
  const h = await home($)
  const t = await $.clock.now()
  await update($, now, () => t)
  if (r === null || h === null) return
  const dir = `${h}/.claude/hga/issue`
  const list: Running[] = []
  try {
    if (await $.fs.exists(dir)) {
      for (const f of await $.fs.list(dir)) {
        if (f.kind !== 'file' || !f.name.startsWith(prefix(r)) || !f.name.endsWith('.json')) continue
        try {
          const data = JSON.parse(await $.fs.read(`${dir}/${f.name}`)) as Running
          if (Array.isArray(data.steps) && typeof data.updatedAt === 'number') list.push(data)
        } catch {
          // half-written or broken file: retried on the next round
        }
      }
    }
  } catch {
    // no file system access: the running section stays empty
  }
  const h2 = await read($, hidden)
  const visible = list
    .filter(f => t - f.updatedAt < (finished(f) ? DAY : 7 * DAY) && !isHidden(f, h2))
    .sort((a, b) => b.updatedAt - a.updatedAt)
  await update($, running, () => visible)
}

// The ✕ button: hides the row; if the issue reports again later (a newer file), it comes back.
async function hide($: EngineInterface, f: Running): Promise<void> {
  const next = { ...(await read($, hidden)), [f.issue]: f.updatedAt }
  await update($, hidden, () => next)
  await update($, running, list => list.filter(x => x.issue !== f.issue))
  await $.store.set('hidden', next).catch(() => undefined)
}

async function loadIssues($: EngineInterface): Promise<void> {
  const r = await read($, repo)
  if (r === null) return
  try {
    const res = await helper($, ['next', r, '--json'], 120_000)
    if (res.exitCode !== 0) throw new Error(res.stderr.trim().split('\n').pop() || `exit code ${res.exitCode}`)
    const j = JSON.parse(res.stdout) as Issues
    const t = await $.clock.now()
    await update($, issues, () => j)
    await update($, issuesAt, () => t)
    await update($, error, () => null)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    await update($, error, () => `HGA next: ${cut(message, 200)}`)
  }
}

// The parallel limit and the usage ceiling come from the configuration; on failure the defaults stay.
async function loadLimits($: EngineInterface): Promise<void> {
  try {
    const res = await helper($, ['config'], 30_000)
    if (res.exitCode !== 0) return
    const c = JSON.parse(res.stdout) as { parallel?: { max_per_repo?: number; usage_ceiling_pct?: number } }
    const l: Limits = {
      maxPerRepo: Number(c.parallel?.max_per_repo) || 2,
      usageCeilingPct: Number(c.parallel?.usage_ceiling_pct) || 80,
    }
    await update($, limits, () => l)
  } catch {
    // no Python or no configuration: defaults
  }
}

async function loadUsage($: EngineInterface): Promise<void> {
  const limit = (await $.session.usage()).rateLimits.find(l => l.kind === 'five_hour')
  await update($, usage, () => (limit === undefined ? null : Math.round(limit.percentUsed)))
}

async function refresh($: EngineInterface): Promise<void> {
  await loadRunning($)
  await loadUsage($).catch(() => undefined)
  await loadIssues($)
}

async function everyMinute($: EngineInterface): Promise<void> {
  if (!(await read($, active))) return
  await loadRunning($)
  await loadUsage($).catch(() => undefined)
  if ((await $.clock.now()) - (await read($, issuesAt)) >= NEXT_MIN * 60_000) await loadIssues($)
}

async function openPane($: EngineInterface): Promise<void> {
  const r = await read($, repo)
  await $.ui.open({ id: PANE, title: `🧭 ${r === null ? 'Triage' : short(r)}` })
  await update($, open, () => true)
}

// Our own close does not go through our `ui.close` hook: `open` is set here.
async function toggle($: EngineInterface): Promise<boolean> {
  if (await read($, open)) {
    await $.ui.close({ id: PANE })
    await update($, open, () => false)
    return false
  }
  await openPane($)
  return true
}

// The repository comes from the session's git remote (triage runs in the repo's main checkout), or from /triage-pane <owner/repo>.
async function activate($: EngineInterface, given?: string): Promise<void> {
  if (given !== undefined || !(await read($, active))) {
    const r = given ?? repoOf((await $.session.repo())?.remote)
    if (given !== undefined) {
      await update($, issues, () => null)
      await update($, issuesAt, () => 0)
    }
    await update($, repo, () => r)
    await update($, active, () => true)
    await loadLimits($)
  }
  await openPane($)
  await refresh($)
}

async function start($: EngineInterface): Promise<void> {
  // Registration throws if the name is taken (`/triage` is the plugin's own /hga:triage skill, and other skill
  // collections use it too, hence `/triage-pane`); that must not stop the clock and the other hooks.
  await $.command
    .register({
      name: 'triage-pane',
      description: 'Toggle the hga:triage dashboard · /triage-pane refresh · /triage-pane <owner/repo>',
      argumentHint: '[refresh | owner/repo]',
      immediate: true,
    })
    .catch((err: unknown) => $.ui.toast(`hga: /triage-pane could not be registered (${err instanceof Error ? err.message : String(err)})`))
  $.clock.every(60_000, () => void everyMinute($))
  const stored = await $.store.get('hidden').catch(() => undefined)
  if (stored !== undefined && stored !== null && typeof stored === 'object') await update($, hidden, () => stored as Record<string, number>)
  await $.tool.register(PHASE_SPEC)
}

async function button($: EngineInterface, e: ResolveInput) {
  if (!(await read($, active))) return null
  const t = await read($, now)
  const list = await read($, running)
  const { maxPerRepo } = await read($, limits)
  const busy = list.filter(f => occupies(f, t)).length
  const live = new Set(list.filter(f => alive(f, t)).map(numberOf))
  // An issue already running may still be Todo on the board: it is not ready.
  const ready = ((await read($, issues))?.buckets.ready ?? []).filter(s => !live.has(s.number)).length
  const { Button } = $.ui.resolve(e)
  return (
    <Button key="triage-pane" plain dimColor={!(await read($, open))} onPress={async () => { await toggle($) }}>
      {`🧭${busy > maxPerRepo ? '⚠' : ''} ${busy}/${maxPerRepo} · ▶${ready}`}
    </Button>
  )
}

export const register: Register = on => {
  // A matcher is needed because the issue pane binds session.start without one; /(?:)/ matches every session.
  // isInteractive is not a good filter: the desktop app runs in SDK mode, where it is false.
  on('session.start', { cwd: /(?:)/ }, async ($, e, next) => {
    const result = await next(e)
    await start($)
    return result
  })

  // Our own close does not go through ui.close; this follows the pane's ×. The matcher is needed: all panes of the
  // plugin register from the same hooks module, and an event without a matcher can be bound only once.
  on('ui.close', { id: PANE }, async ($, e, next) => {
    const result = await next(e)
    await update($, open, () => false)
    return result
  })

  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const below = await next(e)
    const b = await button($, e)
    if (b === null) return below
    const { Box } = $.ui.resolve(e)
    return (
      <Box flexDirection="row" columnGap={1}>
        {below}
        {b}
      </Box>
    )
  })
  // Loading the triage skill (`/hga:triage` or the Skill tool) turns the dashboard on.
  on('skill.prompt', { skill: 'hga:triage' }, async ($, e, next) => {
    const result = await next(e)
    void activate($)
    return result
  })

  on('command.run', { command: 'triage-pane' }, async ($, e) => {
    const arg = e.args.trim()
    if (/^[\w.-]+\/[\w.-]+$/.test(arg)) {
      await activate($, arg)
      return { text: `Dashboard: ${arg}.` }
    }
    if (arg !== '' && arg !== 'refresh') return { text: 'Usage: /triage-pane [refresh | owner/repo]' }
    if (arg === 'refresh') {
      await activate($)
      return { text: 'Dashboard refreshed.' }
    }
    if (!(await read($, active))) {
      await activate($)
      return { text: 'Dashboard opened.' }
    }
    return { text: (await toggle($)) ? 'Dashboard opened.' : 'Dashboard closed.' }
  })

  on('tool.call', { tool: PHASE_TOOL }, async ($, e) => {
    const branch = String(e.branch) as Branch
    if (!(branch in BRANCHES)) return { result: 'Invalid input: branch must be A | B | C | D.' }
    const id: string | null = typeof e.issue === 'string' && e.issue.trim() !== '' ? e.issue.trim() : null
    const prev = await read($, phase)
    const newIssue = id !== null && id !== prev?.issue
    const verdicts: Partial<Record<Question, Verdict>> = newIssue ? {} : { ...prev?.verdicts }
    const incoming = (typeof e.verdicts === 'object' && e.verdicts !== null ? e.verdicts : {}) as Record<string, unknown>
    for (const q of QUESTIONS) {
      const v = incoming[q.key]
      if (typeof v === 'string' && VERDICTS.includes(v)) verdicts[q.key] = v as Verdict
    }
    const nextPhase: Phase = {
      branch,
      issue: id ?? prev?.issue ?? null,
      step: typeof e.step === 'string' ? e.step.replace(/\s+/g, ' ').trim() : newIssue ? '' : (prev?.step ?? ''),
      verdicts,
      proposed: typeof e.proposed === 'string' && e.proposed in STATE_COLOR ? e.proposed : newIssue ? null : (prev?.proposed ?? null),
      decisions: typeof e.decisions === 'number' && e.decisions >= 0 ? Math.floor(e.decisions) : newIssue ? null : (prev?.decisions ?? null),
    }
    await update($, phase, () => nextPhase)
    if (!(await read($, active))) void activate($)
    return { result: `Dashboard: ${branch}. ${BRANCHES[branch]}${nextPhase.issue === null ? '' : ` · ${nextPhase.issue}`}.` }
  })

  // A label, prerequisite or status changed: reload the issue groups. `HGA next` (triage branch C) also turns the
  // dashboard on if the skill-load signal was missed.
  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    // PowerShell is a tool only on Windows, so the generated tool list may not contain it.
    const tool: string = e.tool
    const command = tool === 'Bash' || tool === 'PowerShell' ? String((e as { command?: unknown }).command ?? '') : ''
    if (!/hga_issue\.py/.test(command)) return result
    if (/\bnext\b/.test(command) && !/--json/.test(command) && !(await read($, active))) void activate($)
    else if (/\b(triage-state|block|status-set|track)\b/.test(command) && (await read($, active))) void loadIssues($)
    return result
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    if (!(await read($, active))) return <Text dimColor>hga:triage has not run in this session yet. /triage-pane turns it on.</Text>

    const width = Math.max(40, e.props.bodyColumns || 60)
    const r = await read($, repo)
    const t = await read($, now)
    const u = await read($, usage)
    const { maxPerRepo, usageCeilingPct } = await read($, limits)
    const errorText = await read($, error)
    const j = await read($, issues)
    const list = await read($, running)
    const busy = list.filter(f => occupies(f, t)).length
    const over = busy > maxPerRepo
    const live = new Set(list.filter(f => alive(f, t)).map(numberOf))
    const ph = await read($, phase)
    const opened = (await read($, openGroups)) ?? DEFAULT_OPEN
    // A 13/13 issue no longer runs: it sits below the running ones, in its own (collapsible) group.
    const done = list.filter(finished)
    const clock = (ms: number) => {
      const d = new Date(ms)
      return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    }
    const toggleGroup = async (key: string) => {
      const cur = (await read($, openGroups)) ?? DEFAULT_OPEN
      await update($, openGroups, () => (cur.includes(key) ? cur.filter(x => x !== key) : [...cur, key]))
    }
    // A header row: mark, the group's name (clickable if collapsible), the summary on the right.
    const header = (key: string, mark: string, color: string | undefined, title: string, summary: string, collapsible: boolean) => (
      <Box key={`head-${key}`} flexDirection="row" justifyContent="space-between">
        <Box flexDirection="row">
          <Box width={3}>
            <Text color={color} dimColor={color === undefined}>{` ${mark}`}</Text>
          </Box>
          {collapsible ? (
            <Button key={`group-${key}`} plain onPress={async () => { await toggleGroup(key) }}>
              {title}
            </Button>
          ) : (
            <Text>{title}</Text>
          )}
        </Box>
        <Text dimColor>{collapsible ? `${summary} ${opened.includes(key) ? '⌄' : '›'}` : summary}</Text>
      </Box>
    )
    const row = (f: Running) => {
      const all13 = finished(f)
      const state: { mark: string; color?: string } = all13
        ? { mark: '✓', color: 'success' }
        : stalled(f, t)
          ? { mark: '!', color: 'warning' }
          : closed(f)
            ? { mark: '◐' }
            : { mark: '◐', color: ACCENT }
      const note = stalled(f, t) ? `quiet for ${Math.floor((t - f.updatedAt) / 60_000)} min` : currentStep(f)
      const full = Math.round((finishedSteps(f) / STEPS.length) * MINI)
      // Fixed-width columns: with the desktop app's proportional font, padding with spaces does not align.
      return (
        <Box key={f.issue} flexDirection="row" paddingLeft={3}>
          <Box width={3}>
            <Text color={state.color} dimColor={state.color === undefined}>{` ${state.mark}`}</Text>
          </Box>
          <Box width={NAME_COLUMNS}>
            {/* The issue name jumps to its session if the issue pane recorded the desktop id. */}
            {f.desktop !== undefined && DESKTOP.test(f.desktop) ? (
              <Button key={`jump-${numberOf(f)}`} plain dimColor={!occupies(f, t)} onPress={async () => { await jumpTo($, f.desktop!) }}>
                {short(f.issue)}
              </Button>
            ) : (
              <Text bold={occupies(f, t)} dimColor={!occupies(f, t)} wrap="truncate-end">{short(f.issue)}</Text>
            )}
          </Box>
          <Box width={MINI_COLUMNS} flexDirection="row">
            <Text color={all13 ? 'success' : ACCENT}>{'█'.repeat(full)}</Text>
            <Text dimColor>{'█'.repeat(MINI - full)}</Text>
          </Box>
          <Box width={6}>
            <Text dimColor>{`${finishedSteps(f)}/13`}</Text>
          </Box>
          <Box width={17}>
            <Text dimColor wrap="truncate-end">{note}</Text>
          </Box>
          <Box width={8}>
            <Text dimColor>{`◷ ${duration(elapsed(f, t))}`}</Text>
          </Box>
          {alive(f, t) ? null : (
            <Button key={`hide-${numberOf(f)}`} label="✕" plain dimColor onPress={async () => { await hide($, f) }} />
          )}
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" justifyContent="space-between">
          <Text bold>{`${r === null ? 'unknown repository' : short(r)} · triage`}</Text>
          {u === null ? null : (
            <Text color={u >= usageCeilingPct ? 'error' : u >= usageCeilingPct - 10 ? 'warning' : undefined} dimColor={u < usageCeilingPct - 10}>
              {`5h ${u}% / ${usageCeilingPct}%`}
            </Text>
          )}
        </Box>
        {errorText === null ? null : <Text color="error">{cut(errorText, width)}</Text>}

        {ph === null ? null : (
          <Box flexDirection="column" marginTop={1}>
            <Box flexDirection="row">
              <Box width={3}>
                <Text color={ACCENT}>{` ${BRANCH_ICON[ph.branch]}`}</Text>
              </Box>
              <Text bold>{BRANCHES[ph.branch]}</Text>
              <Text dimColor>{` · ${ph.branch}${ph.issue === null ? '' : ` · ${short(ph.issue)}`}`}</Text>
            </Box>
            {ph.step === '' ? null : (
              <Box paddingLeft={3}>
                <Text dimColor wrap="truncate-end">{cut(ph.step, width - 4)}</Text>
              </Box>
            )}
            {ph.branch === 'A' || ph.branch === 'B'
              ? QUESTIONS.map(q => {
                  const v = ph.verdicts[q.key] ?? null
                  const good = q.inverted ? v === 'no' : v === 'yes'
                  const bad = q.inverted ? v === 'yes' : v === 'no'
                  const m: { mark: string; color?: string } =
                    v === null ? { mark: '○' } : good ? { mark: '✓', color: 'success' } : bad ? { mark: '✕', color: 'error' } : { mark: '!', color: 'warning' }
                  return (
                    <Box key={`q-${q.key}`} flexDirection="row" paddingLeft={3}>
                      <Box width={3}>
                        <Text color={m.color} dimColor={m.color === undefined}>{` ${m.mark}`}</Text>
                      </Box>
                      <Text dimColor={v === null}>{q.title.replace(/\?$/, '')}</Text>
                      <Text dimColor>{v === null ? '' : ` · ${v}`}</Text>
                    </Box>
                  )
                })
              : null}
            {ph.proposed === null ? null : (
              <Box paddingLeft={3}>
                <Text dimColor>{`→ ${ph.proposed}`}</Text>
              </Box>
            )}
            {(ph.decisions ?? 0) === 0 ? null : (
              <Box flexDirection="row" paddingLeft={3}>
                <Box width={3}>
                  <Text color="warning">{' ?'}</Text>
                </Box>
                <Text>{`${ph.decisions} open decision${ph.decisions === 1 ? '' : 's'} waiting for you`}</Text>
              </Box>
            )}
          </Box>
        )}

        <Box flexDirection="column" marginTop={1}>
          {header(
            'running',
            busy > 0 ? '◐' : '○',
            over ? 'error' : busy > 0 ? ACCENT : undefined,
            'Running implementations',
            `${busy}/${maxPerRepo}${over ? ' · over the limit' : ''}`,
            false,
          )}
          {list.filter(f => !finished(f)).slice(0, 6).map(row)}
          {Array.from({ length: Math.max(0, maxPerRepo - busy) }, (_, i) => (
            <Box key={`free-${i}`} flexDirection="row" paddingLeft={3}>
              <Box width={3}>
                <Text dimColor>{' ○'}</Text>
              </Box>
              <Text dimColor>free slot</Text>
            </Box>
          ))}
        </Box>

        {done.length === 0 ? null : (
          <Box flexDirection="column">
            {header('finished', '✓', 'success', 'Finished', `${done.length}`, true)}
            {opened.includes('finished') ? done.slice(0, 6).map(row) : null}
          </Box>
        )}

        <Box flexDirection="column" marginTop={1}>
          {header('issues', '☰', undefined, 'Issues', j === null ? 'loading…' : `HGA next · ${clock(await read($, issuesAt))}`, false)}
          {j === null
            ? null
            : GROUPS.map(g => {
                const rows = j.buckets[g.key] ?? []
                if (rows.length === 0 && g.key !== 'ready') return null
                // A live implementation session's issue gets `◐`: it does not count as ready, and under "In progress"
                // it stands apart from issues stuck on the board.
                const mark = (n: number) => (live.has(n) ? '◐' : '')
                const liveCount = rows.filter(s => live.has(s.number)).length
                const content =
                  g.key === 'blocked'
                    ? [rows.map(s => `#${s.number} ← ${s.blockers.map(b => `#${b}`).join(',')}`).join(' · ')]
                    : g.key === 'untriaged' || g.key === 'in_progress' || g.key === 'in_review'
                      ? [rows.slice(0, 10).map(s => `#${s.number}${mark(s.number)}`).join(' ') + (rows.length > 10 ? ' …' : '')]
                      : rows
                          .slice(0, 3)
                          .map(s => `#${s.number} ${live.has(s.number) ? '◐ running · ' : ''}${s.title}`)
                          .concat(rows.length > 3 ? [`… and ${rows.length - 3} more`] : [])
                const count =
                  g.key === 'ready'
                    ? `${rows.length - liveCount}${liveCount > 0 ? ` · ${liveCount} already running` : ''}`
                    : g.key === 'in_progress' && liveCount > 0
                      ? `${rows.length} · ◐ ${liveCount} live session${liveCount === 1 ? '' : 's'}`
                      : `${rows.length}`
                const empty = rows.length - (g.key === 'ready' ? liveCount : 0) === 0
                return (
                  <Box key={g.key} flexDirection="column" paddingLeft={3}>
                    {header(g.key, g.mark, empty ? undefined : g.color, g.title, count, rows.length > 0)}
                    {rows.length > 0 && opened.includes(g.key)
                      ? content
                          .filter(c => c !== '')
                          .map((c, i) => (
                            <Box key={`${g.key}-${i}`} paddingLeft={3}>
                              <Text dimColor wrap="truncate-end">{cut(c, width - 8)}</Text>
                            </Box>
                          ))
                      : null}
                  </Box>
                )
              })}
        </Box>
      </Box>
    )
  })
}
