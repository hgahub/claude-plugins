// not_applicable: the step's gate does not apply to this change (the issue pane only; `HGA risk` is its evidence).
export type StepState = 'in_progress' | 'done' | 'skipped' | 'not_applicable'
// startedAt / endedAt (ms): when the step was reported in_progress, and done, skipped or not_applicable. Optional: older state
// files have neither, and a step reported done without an in_progress has no start.
export type Step = { state: StepState; evidence: string; startedAt?: number; endedAt?: number }
// The account's five-hour usage at one moment (`$.session.usage()`, kind five_hour). It is account-wide: context
// for the issue's numbers, never the issue's own cost.
export type UsageSnapshot = { at: number; percentUsed: number }
// The current issue: steps in the order of the issue skill's checklist (0–12), null = not started yet.
// updatedAt: time of the last report; a finished issue's clock (step 12 done) stops here.
// checks: the PR's manual review points (the model writes them, the reviewer ticks them); [] = no such point.
// fiveHour: the five-hour usage at step 0's start and at step 12's done (for the metrics record).
export type Check = { text: string; done: boolean }
export type Issue = {
  issue: string
  verb: string
  startedAt: number
  steps: (Step | null)[]
  updatedAt?: number
  checks?: Check[]
  fiveHour?: { start?: UsageSnapshot; end?: UsageSnapshot }
}
// The shared state file (~/.claude/hga/issue/<owner>-<repo>-<n>.json): the issue pane writes it, the triage panel reads it.
// desktop: the desktop app's session id (CLAUDE_CODE_HOST_SESSION_ID, local_…); the triage panel jumps to this session.
export type IssueFile = Issue & { updatedAt: number; session: string; desktop?: string }
export type Running = IssueFile

// The output of `HGA next <repo> --json` (skills/issue/scripts/hga_issue.py).
export type IssueRow = { number: number; title: string; blockers: number[]; assignees?: string[] }
export type Bucket = 'ready' | 'needs_human' | 'blocked' | 'needs_info' | 'in_progress' | 'in_review' | 'untriaged'
export type Issues = { repo: string; project: string | null; buckets: Record<Bucket, IssueRow[]>; off_board: number }

// The parallel limit and the 5-hour usage ceiling, from `HGA config` (parallel.*).
export type Limits = { maxPerRepo: number; usageCeilingPct: number }

// The triage's current position (from the phase tool).
export type Branch = 'A' | 'B' | 'C' | 'D'
export type Question = 'current' | 'complete' | 'feasible' | 'problem' | 'preceded'
export type Verdict = 'yes' | 'partly' | 'no'
export type Phase = {
  branch: Branch
  issue: string | null
  step: string
  verdicts: Partial<Record<Question, Verdict>>
  proposed: string | null
  decisions: number | null
}

// The hga:intent's position (from the intent tool). The sections are the intent.md's: how complete the picture is.
export type Coverage = 'empty' | 'partial' | 'done'
export type Intent = {
  intent: string
  steps: (Step | null)[]
  sections: Record<string, Coverage>
  questions: number | null
  // the readiness gate of intent_check.py: PASS | WARN | BLOCK
  verdict: string | null
  issue: string | null
  file: string | null
}
// The intent's state file (~/.claude/hga/intent/<intent>.json): after a restart the pane comes back from it.
export type IntentFile = Intent & { updatedAt: number; session: string }

declare module 'claude-code' {
  // The mod's own tools: the generated MCP list only contains servers connected at load time.
  interface McpToolInputs {
    'mcp__hga__step': { issue: string; step: number; state: string; evidence?: string; verb?: string; started_at?: string; checks?: string[] }
    'mcp__hga__phase': { branch: string; issue?: string; step?: string; verdicts?: Record<string, string>; proposed?: string; decisions?: number }
    'mcp__hga__intent': { intent: string; step?: number; state?: string; evidence?: string; sections?: Record<string, string>; questions?: number; verdict?: string; issue?: string; file?: string }
  }
  interface PluginState {
    hga: {
      // issue pane
      issue: Issue | null
      issueNow: number
      issueOpen: boolean
      // sections opened by hand; null = default (only the running section)
      issueSections: string[] | null
      // the steps opened to several lines by a double click
      issueRows: number[]
      // triage panel. active: the triage skill was loaded in this session (or /triage-pane opened it); only then does it work.
      active: boolean
      open: boolean
      repo: string | null
      issues: Issues | null
      issuesAt: number
      running: Running[]
      usage: number | null
      error: string | null
      now: number
      hidden: Record<string, number>
      phase: Phase | null
      // groups opened/closed by hand (finished, issue groups); null = default
      triageOpen: string[] | null
      limits: Limits
      // intent pane and the band above the prompt
      intent: Intent | null
      intentOpen: boolean
      intentHidden: boolean
      // the issue's state file (~/.claude/hga/issue/), once the implementation runs
      intentRunning: IssueFile | null
    }
  }
}
