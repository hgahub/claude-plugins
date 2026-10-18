import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, ResolveInput } from 'claude-code'

import type { Issue, IssueFile, Step, StepState, UsageSnapshot } from '../types'

const PANE = 'hga-issue'
const TOOL = 'mcp__hga__step'

const issue = atom({ plugin: 'hga', key: 'issue' } as const, null)
// Ticks every minute so the elapsed time on the pane stays live.
const now = atom({ plugin: 'hga', key: 'issueNow' } as const, 0)
// Whether the pane is open: the footer button and /issue-pane open or close it based on this.
const open = atom({ plugin: 'hga', key: 'issueOpen' } as const, false)
// Sections opened by hand (by clicking the section name); null = only the running section is open.
const sections = atom({ plugin: 'hga', key: 'issueSections' } as const, null)
// Steps opened to several lines by a double click: a long evidence is readable without widening the pane.
const rows = atom({ plugin: 'hga', key: 'issueRows' } as const, [])
// Double click: the engine only reports single presses, so two presses of the same row within this many ms count.
const DOUBLE = 500
let lastPress: { key: string; at: number } | null = null

// The issue skill's "Verified checklist", in order (skills/issue/SKILL.md).
const STEPS = [
  'Start', 'Claim', 'In Progress', 'Worktree', 'Decisions', 'Build + tests',
  'Live test', 'PR', 'Review', 'Done', 'Cleanup', 'Knowledge', 'Report',
]
// A section's icon shows its kind, not its state: plan, build, review, finish.
// Unicode symbols, because a mod only draws text; all of them are in the common symbol fonts.
const SECTIONS = [
  { title: 'Prepare', from: 0, to: 4, icon: '☰' },
  { title: 'Build', from: 5, to: 6, icon: '✎' },
  { title: 'Review', from: 7, to: 8, icon: '⌕' },
  { title: 'Finish', from: 9, to: 12, icon: '⚑' },
]
// One accent color (the running step, the bar), the warning color for skipped steps, everything else dim;
// the symbol tells the state. Theme keys, so both light and dark themes are followed.
const ACCENT = 'suggestion'
const MARK: Record<StepState | 'none', { mark: string; color?: string }> = {
  done: { mark: '✓', color: 'success' },
  in_progress: { mark: '◐', color: ACCENT },
  skipped: { mark: '!', color: 'warning' },
  not_applicable: { mark: '–' },
  none: { mark: '○' },
}
const BAR = 7
const STATES: readonly string[] = ['in_progress', 'done', 'skipped', 'not_applicable']
// Fixed-width columns: with the desktop app's proportional font, padding with spaces does not align.
const NAME = 18
const TITLE = 14
// The PR's manual review section: the reviewer ticks off here what they have checked.
const CHECKS = 'Manual review'
const CHECKS_MAX = 13

const STEP_SPEC = {
  name: 'step',
  description:
    "The state of one step of the hga:issue workflow, for the user's side pane. Call it on every state change: " +
    'when a step starts (in_progress), finishes (done, with the read-back evidence), is skipped (skipped, with the reason) ' +
    "or does not apply to this change's risk class (not_applicable, with the `HGA risk` line as evidence). " +
    'A different issue id starts a new pane.',
  isDeferred: false,
  inputSchema: {
    type: 'object',
    properties: {
      issue: { type: 'string', description: 'owner/repo#number, e.g. acme/web-app#42' },
      verb: { type: 'string', description: 'The claim verb: implement, fix, verify, re-verify.' },
      step: { type: 'integer', minimum: 0, maximum: 12, description: 'The checklist number: 0 Start … 12 Report.' },
      state: { type: 'string', enum: STATES },
      evidence: { type: 'string', description: 'Short evidence or the reason for skipping, in one line (SHA, test count, status, URL). Required for done, skipped and not_applicable; a step reported again in the same state keeps its evidence.' },
      started_at: {
        type: 'string',
        description: 'When the work really started, ISO 8601 (the `HGA now` value of step 0, e.g. 2026-10-13T08:53:05+02:00); the clock counts from here.',
      },
      checks: {
        type: 'array',
        items: { type: 'string' },
        maxItems: CHECKS_MAX,
        description:
          "The PR's manual review points for the reviewer, at most 13, one short line each: only what really needs a human check " +
          '(not covered by the tests or the review bot). [] = no such point. Replaces the whole list; a point with the same text keeps its tick.',
      },
    },
    required: ['issue', 'step', 'state'],
  },
}

export function duration(ms: number): string {
  const min = Math.max(0, Math.floor(ms / 60_000))
  return `${Math.floor(min / 60)}:${String(min % 60).padStart(2, '0')}`
}

const cut = (s: string, n: number) => (s.length <= n ? s : `${s.slice(0, Math.max(0, n - 1))}…`)
// owner/repo#n → repo#n: the owner is the same for most issues, and the pane is narrow.
const short = (id: string) => id.replace(/^[^/#\s]+\//, '')
const finished = (j: Issue) => j.steps.filter(l => l !== null && l.state !== 'in_progress').length

// The step's times for the metrics record: in_progress keeps an earlier start (a repeated report, or a step
// opened again) and drops the end; done / skipped / not_applicable stamps the end and keeps the start. A finished step reported
// again (its evidence amended) keeps its end. A step reported done without an in_progress gets no start (step 0
// takes the given started_at): the record falls back on the step before it.
export function stamp(prev: Step | null, state: StepState, evidence: string, t: number, start?: number): Step {
  const startedAt = prev?.startedAt ?? start ?? (state === 'in_progress' ? t : undefined)
  return {
    state,
    evidence,
    ...(startedAt === undefined ? {} : { startedAt }),
    ...(state === 'in_progress' ? {} : { endedAt: prev !== null && prev.state !== 'in_progress' ? (prev.endedAt ?? t) : t }),
  }
}

// The account's five-hour usage now; null if the engine has no rate limit data (API key, older version, test).
async function fiveHour($: EngineInterface, t: number): Promise<UsageSnapshot | null> {
  try {
    const limit = (await $.session.usage()).rateLimits?.find(l => l.kind === 'five_hour')
    return limit === undefined || !Number.isFinite(limit.percentUsed) ? null : { at: t, percentUsed: limit.percentUsed }
  } catch {
    return null
  }
}

async function tick($: EngineInterface): Promise<void> {
  if ((await read($, issue)) === null) return
  const t = await $.clock.now()
  await update($, now, () => t)
}

async function stateDir($: EngineInterface): Promise<string | null> {
  const home = (await $.env.get('USERPROFILE')) || (await $.env.get('HOME'))
  return home ? `${home}/.claude/hga/issue` : null
}

// Shared state file for the triage session (triage panel), in the user's folder: one file per issue, so two
// parallel sessions do not overwrite each other. On error it is silently skipped: the pane is not affected.
async function save($: EngineInterface, j: Issue): Promise<void> {
  try {
    const dir = await stateDir($)
    if (dir === null) return
    // The desktop app's session id (absent in a terminal): the triage panel links to this session with it.
    const desktop = (await $.env.get('CLAUDE_CODE_HOST_SESSION_ID')) || undefined
    const file: IssueFile = { ...j, updatedAt: await $.clock.now(), session: await $.session.id(), ...(desktop ? { desktop } : {}) }
    await $.fs.write(`${dir}/${j.issue.replace(/[^A-Za-z0-9_-]+/g, '-')}.json`, JSON.stringify(file, null, 2))
  } catch {
    // no file system or permission: the triage panel does not see this issue
  }
}

// The issue lives in the session's memory: after a plugin update or restart it is empty. Then it comes back
// from the session's own most recent state file. If an in-memory issue lacks updatedAt (an older version kept by
// /reload-plugins), only that field is filled in, from the same issue's state file.
async function restore($: EngineInterface): Promise<void> {
  const cur = await read($, issue)
  if (cur !== null && cur.updatedAt !== undefined) return
  try {
    const dir = await stateDir($)
    if (dir === null || !(await $.fs.exists(dir))) return
    const id = await $.session.id()
    let found: IssueFile | null = null
    for (const f of await $.fs.list(dir)) {
      if (f.kind !== 'file' || !f.name.endsWith('.json')) continue
      try {
        const data = JSON.parse(await $.fs.read(`${dir}/${f.name}`)) as IssueFile
        if (data.session !== id || !Array.isArray(data.steps) || (cur !== null && data.issue !== cur.issue)) continue
        if (found === null || data.updatedAt > found.updatedAt) found = data
      } catch {
        // half-written or broken file: skip it
      }
    }
    if (found === null) return
    if (cur !== null) {
      const updatedAt = found.updatedAt
      await update($, issue, j => (j === null ? j : { ...j, updatedAt }))
      return
    }
    const { session: _s, ...j } = found
    await update($, issue, () => j)
    await update($, now, () => found.updatedAt)
  } catch {
    // no file system: the pane stays empty, the next report fills it
  }
}

// Two presses of the same row within DOUBLE ms: the row's evidence opens to several lines, or back to one.
async function doublePress($: EngineInterface, key: string, i: number): Promise<void> {
  const t = await $.clock.now()
  if (lastPress === null || lastPress.key !== key || t - lastPress.at > DOUBLE) {
    lastPress = { key, at: t }
    return
  }
  lastPress = null
  await update($, rows, r => (r.includes(i) ? r.filter(x => x !== i) : [...r, i]))
}

// The reviewer's tick: it goes into the state file too, so it survives a restart.
async function toggleCheck($: EngineInterface, i: number): Promise<void> {
  await update($, issue, j =>
    j === null || j.checks === undefined ? j : { ...j, checks: j.checks.map((c, k) => (k === i ? { ...c, done: !c.done } : c)) },
  )
  const j = await read($, issue)
  if (j !== null) await save($, j)
}

async function openPane($: EngineInterface): Promise<void> {
  await restore($)
  const j = await read($, issue)
  await $.ui.open({ id: PANE, title: j === null ? '🎫 Issue' : `🎫 ${short(j.issue)}` })
  await update($, open, () => true)
}

// After our own close we set `open` here; the pane's × is followed by the `ui.close` hook.
async function toggle($: EngineInterface): Promise<boolean> {
  if (await read($, open)) {
    await $.ui.close({ id: PANE })
    await update($, open, () => false)
    return false
  }
  await openPane($)
  return true
}

async function start($: EngineInterface): Promise<void> {
  await $.tool.register(STEP_SPEC)
  // `/issue` is taken by the plugin's own /hga:issue skill; if registration still fails, the clock should run anyway.
  await $.command
    .register({ name: 'issue-pane', description: 'Toggle the hga:issue workflow pane', immediate: true })
    .catch((err: unknown) => $.ui.toast(`hga: /issue-pane could not be registered (${err instanceof Error ? err.message : String(err)})`))
  $.clock.every(60_000, () => void tick($))
  await restore($)
}

// A button on the right of the footer: the issue and its progress; a click opens / closes the pane.
async function button($: EngineInterface, e: ResolveInput) {
  const j = await read($, issue)
  if (j === null) return null
  const { Button } = $.ui.resolve(e)
  return (
    <Button key="issue-pane" plain dimColor={!(await read($, open))} onPress={async () => { await toggle($) }}>
      {`🎫 ${short(j.issue)} ${finished(j)}/${STEPS.length}`}
    </Button>
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
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
  on('command.run', { command: 'issue-pane' }, async $ => ({ text: (await toggle($)) ? 'Issue pane opened.' : 'Issue pane closed.' }))

  on('tool.call', { tool: TOOL }, async ($, e) => {
    const id: string = typeof e.issue === 'string' ? e.issue.trim() : ''
    const step = Number(e.step)
    const state = String(e.state) as StepState
    if (id === '' || !Number.isInteger(step) || step < 0 || step >= STEPS.length || !STATES.includes(state)) {
      return { result: 'Invalid input: issue (owner/repo#number), step 0–12 and state (in_progress | done | skipped | not_applicable) are required.' }
    }
    if (e.checks !== undefined && !(Array.isArray(e.checks) && e.checks.every((c: unknown) => typeof c === 'string'))) {
      return { result: 'Invalid input: checks is a list of strings (at most 13).' }
    }
    const t = await $.clock.now()
    const prev = await read($, issue)
    const base: Issue = prev !== null && prev.issue === id ? prev : { issue: id, verb: '', startedAt: t, steps: STEPS.map(() => null) }
    const reported = typeof e.evidence === 'string' ? e.evidence.replace(/\s+/g, ' ').trim() : ''
    // A finished step needs its evidence (✅ only with read-back evidence). A finished step reported again without
    // one (e.g. only its check list changes) keeps the evidence it has.
    const was = base.steps[step]
    const evidence = reported === '' && state !== 'in_progress' && was?.state === state ? was.evidence : reported
    if (state !== 'in_progress' && evidence === '') {
      const what = state === 'done' ? 'the read-back result' : state === 'skipped' ? 'the reason' : 'the `HGA risk` line'
      return { result: `Invalid input: a ${state} step needs its evidence (${what}).` }
    }
    // The model may report steps late: the real start is step 0's timestamp. A future or invalid value does not count.
    const given = typeof e.started_at === 'string' ? Date.parse(e.started_at) : NaN
    const startOk = Number.isFinite(given) && given <= t
    const points: string[] | undefined = e.checks?.map((c: string) => c.replace(/\s+/g, ' ').trim()).filter((c: string) => c !== '')
    // The five-hour usage at the start (step 0's first report) and at the end (step 12's first done): account-wide
    // context. Step 12 is reported again with the metrics record's path; that keeps the first snapshot.
    const snapStart = step === 0 && base.fiveHour?.start === undefined ? await fiveHour($, t) : null
    const snapEnd = step === 12 && state === 'done' && base.fiveHour?.end === undefined ? await fiveHour($, t) : null
    const usage =
      snapStart === null && snapEnd === null
        ? base.fiveHour
        : { ...base.fiveHour, ...(snapStart === null ? {} : { start: snapStart }), ...(snapEnd === null ? {} : { end: snapEnd }) }
    const nextIssue: Issue = {
      ...base,
      ...(points === undefined
        ? {}
        : { checks: points.slice(0, CHECKS_MAX).map(text => ({ text, done: base.checks?.some(c => c.text === text && c.done) ?? false })) }),
      startedAt: startOk ? given : base.startedAt,
      verb: typeof e.verb === 'string' && e.verb !== '' ? e.verb : base.verb,
      steps: base.steps.map((l, i) => (i === step ? stamp(l ?? null, state, evidence, t, step === 0 && startOk ? given : undefined) : l)),
      ...(usage === undefined ? {} : { fiveHour: usage }),
      updatedAt: t,
    }
    await update($, issue, () => nextIssue)
    if (prev?.issue !== id) {
      await update($, sections, () => null)
      await update($, rows, () => [])
    }
    await update($, now, () => t)
    await save($, nextIssue)
    // Opens by itself only for a new issue: if the user closed it, further reports do not reopen it.
    if (prev?.issue !== id) await openPane($)
    const warning = typeof e.started_at === 'string' && !startOk ? ' started_at is invalid or in the future; ignored.' : ''
    const cut13 = points !== undefined && points.length > CHECKS_MAX ? ` Only the first ${CHECKS_MAX} points of the check list were kept.` : ''
    // The model sees where the reviewer stands too: the report says from this what is still unticked.
    const ch = nextIssue.checks
    const standing = ch === undefined || ch.length === 0 ? '' : ` Manual review: ${ch.filter(c => c.done).length}/${ch.length} ticked.`
    return { result: `${id}: ${finished(nextIssue)}/${STEPS.length} done.${standing}${warning}${cut13}` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const j = await read($, issue)
    if (j === null) {
      return (
        <Text dimColor>
          No issue is running in this session: /hga:issue fills the pane with the step tool. Implementations running in
          parallel are on the triage panel (/triage-pane).
        </Text>
      )
    }

    const width = Math.max(30, e.props.bodyColumns || 40)
    const count = finished(j)
    // A finished issue's clock stops at the last report, as on the triage panel.
    const end = j.steps[12]?.state === 'done' && j.updatedAt !== undefined ? j.updatedAt : Math.max(await read($, now), j.startedAt)
    const elapsed = duration(end - j.startedAt)
    const stepsOf = (sz: (typeof SECTIONS)[number]) => j.steps.slice(sz.from, sz.to + 1).map(l => l ?? null)
    // By default only the running section is open: the one with a step in progress, else the first unfinished one.
    const running =
      SECTIONS.find(sz => stepsOf(sz).some(l => l?.state === 'in_progress')) ?? SECTIONS.find(sz => stepsOf(sz).some(l => l === null))
    const ch = j.checks
    // The manual review section is open by default while it has an unticked point.
    const opened =
      (await read($, sections)) ?? [...(running === undefined ? [] : [running.title]), ...(ch?.some(c => !c.done) ? [CHECKS] : [])]
    const multi = await read($, rows)
    const { Button } = $.ui.resolve(e)
    const toggleSection = async (title: string) => {
      const cur = (await read($, sections)) ?? opened
      await update($, sections, () => (cur.includes(title) ? cur.filter(c => c !== title) : [...cur, title]))
    }
    const checksOpen = opened.includes(CHECKS)
    const manual =
      ch === undefined ? null : (
        <Box key={CHECKS} flexDirection="column">
          <Box flexDirection="row">
            <Box width={3}>
              <Text color={ch.some(c => !c.done) ? ACCENT : undefined} dimColor={!ch.some(c => !c.done)}>{' ☑'}</Text>
            </Box>
            <Box width={TITLE}>
              <Button key={`section-${CHECKS}`} plain dimColor onPress={async () => { await toggleSection(CHECKS) }}>
                {CHECKS}
              </Button>
            </Box>
            <Text dimColor>{`${ch.filter(c => c.done).length}/${ch.length} ${checksOpen ? '⌄' : '›'}`}</Text>
          </Box>
          {!checksOpen ? null : ch.length === 0 ? (
            <Box paddingLeft={6}>
              <Text dimColor>This PR has no highlighted manual review point.</Text>
            </Box>
          ) : (
            ch.map((c, i) => (
              <Box key={`c${i}`} flexDirection="row" paddingLeft={3}>
                <Box width={3}>
                  <Button key={`check-${i}`} plain dimColor={c.done} onPress={async () => { await toggleCheck($, i) }}>
                    <Text color={c.done ? 'success' : undefined}>{c.done ? '☑' : '☐'}</Text>
                  </Button>
                </Box>
                <Box width={width - 7}>
                  <Text dimColor={c.done} strikethrough={c.done} wrap="wrap">{c.text}</Text>
                </Box>
              </Box>
            ))
          )}
        </Box>
      )

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" justifyContent="space-between">
          <Text bold>{`${short(j.issue)}${j.verb === '' ? '' : ` · ${j.verb}`}`}</Text>
          <Text dimColor>{`${count}/${STEPS.length} · ◷ ${elapsed}`}</Text>
        </Box>
        <Box flexDirection="row" columnGap={1} marginBottom={1}>
          {SECTIONS.map(sz => {
            const ls = stepsOf(sz)
            const full = Math.round((ls.filter(l => l !== null && l.state !== 'in_progress').length / ls.length) * BAR)
            return (
              <Box key={`bar-${sz.title}`} flexDirection="row">
                <Text color={ACCENT}>{'█'.repeat(full)}</Text>
                <Text dimColor>{'█'.repeat(BAR - full)}</Text>
              </Box>
            )
          })}
        </Box>
        {SECTIONS.map(sz => {
          const ls = stepsOf(sz)
          const done = ls.filter(l => l !== null && l.state !== 'in_progress').length
          const skipped = ls.filter(l => l?.state === 'skipped').length
          const na = ls.filter(l => l?.state === 'not_applicable').length
          // Icon color: accent for the running section, warning if a step was skipped, otherwise neutral.
          const iconColor = ls.some(l => l?.state === 'in_progress') ? ACCENT : skipped > 0 ? 'warning' : undefined
          const isOpen = opened.includes(sz.title)
          // The manual review sits under the Review section: that is where the reviewer looks for it.
          return [
            <Box key={sz.title} flexDirection="column">
              <Box flexDirection="row">
                <Box width={3}>
                  <Text color={iconColor} dimColor={iconColor === undefined && ls.every(l => l === null)}>{` ${sz.icon}`}</Text>
                </Box>
                <Box width={TITLE}>
                  <Button
                    key={`section-${sz.title}`}
                    plain
                    dimColor={sz !== running}
                    onPress={async () => { await toggleSection(sz.title) }}
                  >
                    {sz.title}
                  </Button>
                </Box>
                <Text dimColor>{`${done}/${ls.length}${skipped > 0 ? ` · ${skipped} skipped` : ''}${na > 0 ? ` · ${na} n/a` : ''} ${isOpen ? '⌄' : '›'}`}</Text>
              </Box>
              {isOpen
                ? STEPS.slice(sz.from, sz.to + 1).map((name, k) => {
                    const i = sz.from + k
                    const l = j.steps[i] ?? null
                    const m = MARK[l?.state ?? 'none']
                    const room = width - NAME - 9
                    return (
                      <Box key={`s${i}`} flexDirection="row" paddingLeft={3}>
                        <Box width={3}>
                          <Text color={m.color} dimColor={m.color === undefined}>{` ${m.mark}`}</Text>
                        </Box>
                        <Box width={NAME + 1}>
                          <Button key={`row-${i}`} plain onPress={async () => { await doublePress($, `row-${i}`, i) }}>
                            <Text dimColor={l?.state !== 'in_progress'} bold={l?.state === 'in_progress'} wrap="truncate-end">
                              {name}
                            </Text>
                          </Button>
                        </Box>
                        {l === null || l.evidence === '' ? null : multi.includes(i) ? (
                          <Box width={room}>
                            <Text dimColor wrap="wrap">{l.evidence}</Text>
                          </Box>
                        ) : (
                          <Text dimColor>{cut(l.evidence, room)}</Text>
                        )}
                      </Box>
                    )
                  })
                : null}
            </Box>,
            sz.title === 'Review' ? manual : null,
          ]
        })}
      </Box>
    )
  })
}
