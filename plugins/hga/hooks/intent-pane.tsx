import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Coverage, Intent, IntentFile, StepState } from '../types'

const PANE = 'hga-intent'
const TOOL = 'mcp__hga__intent'

const intent = atom({ plugin: 'hga', key: 'intent' } as const, null)
const open = atom({ plugin: 'hga', key: 'intentOpen' } as const, false)
// The band's ✕ button; a new intent shows it again.
const hidden = atom({ plugin: 'hga', key: 'intentHidden' } as const, false)

// The intent skill's stations, in order (skills/intent/SKILL.md, "Stations").
export const STEPS = ['Intent', 'Context', 'Interview', 'Research', 'Draft', 'Approval', 'Knowledge base', 'Issue', 'Handoff']
const KNOWLEDGE = 6
const ISSUE = 7
const HANDOFF = 8
// The intent.md sections that make up the "full picture"; the keys are those of intent_check.py --json.
export const SECTIONS: { key: string; title: string }[] = [
  { key: 'problem', title: 'Problem' },
  { key: 'outcome', title: 'Desired outcome' },
  { key: 'affected', title: 'Affected' },
  { key: 'current', title: 'Current state' },
  { key: 'behavior', title: 'Expected behavior' },
  { key: 'criteria', title: 'Acceptance criteria' },
  { key: 'constraints', title: 'Constraints' },
  { key: 'scope', title: 'Out of scope' },
]
const COVERAGES: readonly string[] = ['empty', 'partial', 'done']
const STATES: readonly string[] = ['in_progress', 'done', 'skipped']
const VERDICTS: readonly string[] = ['PASS', 'WARN', 'BLOCK']
const VERDICT_COLOR: Record<string, string> = { PASS: 'success', WARN: 'warning', BLOCK: 'error' }
// The same color scheme as the issue and triage panes: one accent color, green for done, yellow for a warning.
const ACCENT = 'suggestion'
const MARK: Record<StepState | 'none', { mark: string; color?: string }> = {
  done: { mark: '✓', color: 'success' },
  in_progress: { mark: '◐', color: ACCENT },
  skipped: { mark: '!', color: 'warning' },
  not_applicable: { mark: '–' }, // an issue step state only; the intent's steps do not take it
  none: { mark: '○' },
}
const COVERAGE_MARK: Record<Coverage, { mark: string; color?: string }> = {
  done: { mark: '✓', color: 'success' },
  partial: { mark: '◐', color: 'warning' },
  empty: { mark: '○' },
}
const BAR = 14
const NAME = 22

const SPEC = {
  name: 'intent',
  description:
    "The hga:intent's position, for the user's pane and the progress band above the prompt. Call it at every station " +
    'change (step + state), and when an intent.md section\'s coverage, the number of open questions, the file or the issue changes. ' +
    'Give only the changed fields; a different intent starts a new pane. A station change closes the station left ' +
    '(done | skipped) and starts the next; the answer names any earlier station not yet closed.',
  isDeferred: false,
  inputSchema: {
    type: 'object',
    properties: {
      intent: { type: 'string', description: "The intent's short name, <app>-intent-<topic> (the intent.md's file name stem), e.g. web-app-intent-xlsx-export." },
      step: { type: 'integer', minimum: 0, maximum: STEPS.length - 1, description: 'The station: 0 Intent, 1 Context, 2 Interview, 3 Research, 4 Draft, 5 Approval, 6 Knowledge base, 7 Issue, 8 Handoff.' },
      state: { type: 'string', enum: STATES },
      evidence: { type: 'string', description: 'One short line: round, module found, SHA, file, issue URL, or the reason for skipping.' },
      sections: {
        type: 'object',
        description: 'Coverage per section: empty | partial | done. Keys: ' + SECTIONS.map(s => s.key).join(', ') + '.',
        properties: Object.fromEntries(SECTIONS.map(s => [s.key, { type: 'string', enum: COVERAGES }])),
      },
      questions: { type: 'integer', minimum: 0, description: 'The number of questions still open.' },
      verdict: { type: 'string', enum: VERDICTS, description: "The verdict of intent_check.py's readiness gate." },
      file: { type: 'string', description: "The intent.md's path in the knowledge base, e.g. notes/web-app-intent-xlsx-export.md." },
      issue: { type: 'string', description: 'The issue created: owner/repo#number.' },
    },
    required: ['intent'],
  },
}

const cut = (s: string, n: number) => (s.length <= n ? s : `${s.slice(0, Math.max(0, n - 1))}…`)
// owner/repo#n → repo#n, as on the issue pane.
const short = (id: string) => id.replace(/^[^/#\s]+\//, '')
const oneLine = (s: unknown) => (typeof s === 'string' ? s.replace(/\s+/g, ' ').trim() : '')
const fileName = (id: string) => `${id.replace(/[^A-Za-z0-9_-]+/g, '-')}.json`
// owner/repo#n → its GitHub URL; anything else has none and is drawn as plain text.
export function issueUrl(id: string | null): string | null {
  const m = id === null ? null : /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(id)
  return m === null ? null : `https://github.com/${m[1]}/${m[2]}/issues/${m[3]}`
}

// The full picture: a done section counts one, a partial one half.
export function coverage(i: Intent): number {
  return SECTIONS.reduce((n, s) => n + (i.sections[s.key] === 'done' ? 1 : i.sections[s.key] === 'partial' ? 0.5 : 0), 0)
}

// The stations behind the furthest one reported that were never closed (not reported, or left in progress): the
// tool's answer names them, so a station skipped on the pane shows up at the next report, not at the end.
export function unclosed(i: Intent): number[] {
  const last = i.steps.reduce((m, l, k) => (l === null ? m : k), -1)
  return i.steps.flatMap((l, k) => (k < last && (l === null || l.state === 'in_progress') ? [k] : []))
}

async function home($: EngineInterface): Promise<string | null> {
  return (await $.env.get('USERPROFILE')) || (await $.env.get('HOME')) || null
}

async function stateDir($: EngineInterface): Promise<string | null> {
  const h = await home($)
  return h ? `${h}/.claude/hga/intent` : null
}

// As on the issue pane: every report writes the state, one file per intent. On error it is silently skipped:
// the pane is not affected.
async function save($: EngineInterface, i: Intent): Promise<void> {
  try {
    const dir = await stateDir($)
    if (dir === null) return
    const file: IntentFile = { ...i, updatedAt: await $.clock.now(), session: await $.session.id() }
    await $.fs.write(`${dir}/${fileName(i.intent)}`, JSON.stringify(file, null, 2))
  } catch {
    // no file system or permission: after a restart the pane stays empty
  }
}

// After a plugin update or restart the memory is empty: the intent comes back from the session's own most recent
// state file, never from another session's.
async function restore($: EngineInterface): Promise<void> {
  if ((await read($, intent)) !== null) return
  try {
    const dir = await stateDir($)
    if (dir === null || !(await $.fs.exists(dir))) return
    const id = await $.session.id()
    let found: IntentFile | null = null
    for (const f of await $.fs.list(dir)) {
      if (f.kind !== 'file' || !f.name.endsWith('.json')) continue
      try {
        const data = JSON.parse(await $.fs.read(`${dir}/${f.name}`)) as IntentFile
        if (data.session !== id || !Array.isArray(data.steps)) continue
        if (found === null || data.updatedAt > found.updatedAt) found = data
      } catch {
        // half-written or broken file: skip it
      }
    }
    if (found === null) return
    const { session: _s, updatedAt: _u, ...i } = found
    await update($, intent, () => i)
  } catch {
    // no file system: the next report fills it
  }
}

async function openPane($: EngineInterface): Promise<void> {
  await restore($)
  const i = await read($, intent)
  await $.ui.open({ id: PANE, title: i === null ? '◎ Intent' : `◎ ${i.intent}` })
  await update($, open, () => true)
}

async function toggle($: EngineInterface): Promise<boolean> {
  if (await read($, open)) {
    await $.ui.close({ id: PANE })
    await update($, open, () => false)
    return false
  }
  await openPane($)
  return true
}

type Stage = { name: string; text: string; state: StepState | 'none' }

// The current station: the one in progress, else the one after the last reported.
export function station(i: Intent): string {
  const k = i.steps.findIndex(l => l?.state === 'in_progress')
  if (k >= 0) return STEPS[k]!
  const last = i.steps.reduce((acc, l, n) => (l === null ? acc : n), -1)
  return STEPS[Math.min(last + 1, STEPS.length - 1)]!
}

// The intent's own stages, for the band: Intent → Issue. Triage and build have panes of their own.
export function stages(i: Intent): Stage[] {
  const intentDone = i.steps[KNOWLEDGE]?.state === 'done'
  const extra = (i.questions === null || i.questions === 0 ? '' : ` · ${i.questions} question${i.questions === 1 ? '' : 's'}`) +
    (i.verdict === null ? '' : ` · ${i.verdict}`)
  return [
    { name: 'Intent', text: intentDone ? '' : `${station(i)}${extra}`, state: intentDone ? 'done' : 'in_progress' },
    {
      name: 'Issue',
      text: i.issue === null ? '' : `#${i.issue.split('#').pop()}`,
      state: i.issue !== null ? 'done' : i.steps[ISSUE]?.state === 'in_progress' ? 'in_progress' : 'none',
    },
  ]
}

// The band has done its job once the intent is handed off.
const finished = (i: Intent) => i.steps[HANDOFF]?.state === 'done' || i.steps[HANDOFF]?.state === 'skipped'

export const register: Register = on => {
  // A matcher is needed: the issue pane binds session.start without one, the triage panel with /(?:)/.
  on('session.start', { cwd: /^/ }, async ($, e, next) => {
    const result = await next(e)
    await $.tool.register(SPEC)
    await $.command
      .register({ name: 'intent-pane', description: 'Toggle the hga:intent pane', immediate: true })
      .catch((err: unknown) => $.ui.toast(`hga: /intent-pane could not be registered (${err instanceof Error ? err.message : String(err)})`))
    await restore($)
    return result
  })

  on('ui.close', { id: PANE }, async ($, e, next) => {
    const result = await next(e)
    await update($, open, () => false)
    return result
  })

  on('command.run', { command: 'intent-pane' }, async $ => ({ text: (await toggle($)) ? 'Intent pane opened.' : 'Intent pane closed.' }))

  on('tool.call', { tool: TOOL }, async ($, e) => {
    const name = oneLine(e.intent)
    if (name === '') return { result: 'Invalid input: intent is required (<app>-intent-<topic>).' }
    const step = e.step === undefined ? null : Number(e.step)
    const state = e.state === undefined ? null : String(e.state)
    if ((step === null) !== (state === null) || (step !== null && (!Number.isInteger(step) || step < 0 || step >= STEPS.length)) || (state !== null && !STATES.includes(state))) {
      return { result: `Invalid input: step (0–${STEPS.length - 1}) and state (in_progress | done | skipped) go together.` }
    }
    const prev = await read($, intent)
    const isNew = prev?.intent !== name
    const base: Intent = !isNew && prev !== null ? prev : { intent: name, steps: STEPS.map(() => null), sections: {}, questions: null, verdict: null, issue: null, file: null }
    const sections = { ...base.sections }
    const given = (typeof e.sections === 'object' && e.sections !== null ? e.sections : {}) as Record<string, unknown>
    for (const s of SECTIONS) {
      const v = given[s.key]
      if (typeof v === 'string' && COVERAGES.includes(v)) sections[s.key] = v as Coverage
    }
    const nextIntent: Intent = {
      ...base,
      steps: step === null ? base.steps : base.steps.map((l, k) => (k === step ? { state: state as StepState, evidence: oneLine(e.evidence) } : l)),
      sections,
      questions: typeof e.questions === 'number' && e.questions >= 0 ? Math.floor(e.questions) : base.questions,
      verdict: typeof e.verdict === 'string' && VERDICTS.includes(e.verdict) ? e.verdict : base.verdict,
      file: oneLine(e.file) || base.file,
      issue: oneLine(e.issue) || base.issue,
    }
    await update($, intent, () => nextIntent)
    await save($, nextIntent)
    if (isNew) {
      await update($, hidden, () => false)
      await openPane($)
    }
    const q = nextIntent.questions ? `, ${nextIntent.questions} open question${nextIntent.questions === 1 ? '' : 's'}` : ''
    const gaps = unclosed(nextIntent)
    const closed = nextIntent.steps.filter(l => l !== null && l.state !== 'in_progress').length
    const stations =
      gaps.length > 0
        ? ` Not closed on the pane: ${gaps.map(k => `${k} ${STEPS[k]}`).join(', ')} — report each as done or skipped, with its evidence.`
        : closed === STEPS.length ? ` All ${STEPS.length} stations closed.` : ''
    return { result: `${name}: full picture ${coverage(nextIntent)}/${SECTIONS.length}${q}.${stations}` }
  })

  // The band above the prompt: the intent's flow in one row, Intent → Issue; gone once handed off.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const i = await read($, intent)
    if (e.props.hasSurvey || i === null || finished(i) || (await read($, hidden))) return next(e)
    const { Box, Button, Link, Text } = $.ui.resolve(e)
    const st = stages(i)
    const url = issueUrl(i.issue)
    return (
      <Box flexDirection="row" columnGap={1} flexWrap="wrap">
        <Button key="intent-open" plain onPress={async () => { await toggle($) }}>
          {`◎ ${cut(i.intent, 32)}`}
        </Button>
        {st.map((s, k) => {
          const m = MARK[s.state]
          return (
            <Box key={`stage-${s.name}`} flexDirection="row" columnGap={1}>
              {k > 0 ? <Text dimColor>›</Text> : null}
              <Text color={m.color} dimColor={m.color === undefined}>{m.mark}</Text>
              <Text bold={s.state === 'in_progress'} dimColor={s.state === 'none'}>{s.name}</Text>
              {s.text === '' ? null : s.name === 'Issue' && url !== null ? <Link href={url}>{s.text}</Link> : <Text dimColor>{s.text}</Text>}
            </Box>
          )
        })}
        <Button key="intent-hide" plain dimColor onPress={() => update($, hidden, () => true)}>
          ✕
        </Button>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Link, Text } = $.ui.resolve(e)
    const i = await read($, intent)
    if (i === null) return <Text dimColor>No intent is running in this session: /hga:intent fills the pane with the intent tool.</Text>
    const width = Math.max(30, e.props.bodyColumns || 40)
    const n = coverage(i)
    const url = issueUrl(i.issue)
    const full = Math.round((n / SECTIONS.length) * BAR)
    return (
      <Box flexDirection="column">
        <Box flexDirection="row" justifyContent="space-between">
          <Text bold>{cut(i.intent, width - 12)}</Text>
          {url === null ? <Text dimColor>{i.issue === null ? '' : short(i.issue)}</Text> : <Link href={url}>{short(i.issue!)}</Link>}
        </Box>
        <Box flexDirection="row" columnGap={1} marginBottom={1}>
          <Text dimColor>Full picture</Text>
          <Box flexDirection="row">
            <Text color={ACCENT}>{'█'.repeat(full)}</Text>
            <Text dimColor>{'█'.repeat(BAR - full)}</Text>
          </Box>
          <Text dimColor>{`${n}/${SECTIONS.length}${i.questions ? ` · ${i.questions} open question${i.questions === 1 ? '' : 's'}` : ''}`}</Text>
          {i.verdict === null ? null : <Text color={VERDICT_COLOR[i.verdict]}>{i.verdict}</Text>}
        </Box>
        {STEPS.map((name, k) => {
          const l = i.steps[k] ?? null
          const m = MARK[l?.state ?? 'none']
          return (
            <Box key={`s${k}`} flexDirection="row">
              <Box width={3}>
                <Text color={m.color} dimColor={m.color === undefined}>{` ${m.mark}`}</Text>
              </Box>
              <Box width={NAME}>
                <Text bold={l?.state === 'in_progress'} dimColor={l?.state !== 'in_progress'} wrap="truncate-end">{name}</Text>
              </Box>
              {l !== null && l.evidence !== '' ? <Text dimColor>{cut(l.evidence, width - NAME - 4)}</Text> : null}
            </Box>
          )
        })}
        <Box marginTop={1}>
          <Text dimColor>intent.md</Text>
        </Box>
        {SECTIONS.map(s => {
          const m = COVERAGE_MARK[i.sections[s.key] ?? 'empty']
          return (
            <Box key={`sec-${s.key}`} flexDirection="row">
              <Box width={3}>
                <Text color={m.color} dimColor={m.color === undefined}>{` ${m.mark}`}</Text>
              </Box>
              <Text dimColor={m.color === undefined}>{s.title}</Text>
            </Box>
          )
        })}
        {i.file === null ? null : <Text dimColor>{cut(i.file, width)}</Text>}
      </Box>
    )
  })
}
