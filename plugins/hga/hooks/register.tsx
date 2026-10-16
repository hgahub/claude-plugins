import type { Register } from 'claude-code'

import { register as intentPane } from './intent-pane'
import { register as issuePane } from './issue-pane'
import { register as triagePane } from './triage-pane'

// Only one hooks module can be loaded per plugin: all three panes register from here.
export const register: Register = (on, options) => {
  issuePane(on, options)
  triagePane(on, options)
  intentPane(on, options)
}
