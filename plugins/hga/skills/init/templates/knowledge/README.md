# Knowledge base

This repository is a knowledge base for the [hga Claude Code plugin](https://github.com/hgahub/claude-plugins):
`/hga:knowledge` reads and writes it, `/hga:issue` and `/hga:triage` read the app pages before they work and
record what they learned afterwards. Start at [00-index.md](00-index.md).

- Every page has frontmatter (`title`, `verified_at`, `status`, `review_after_days`) and ends with a
  `## Sources and verification` section.
- New findings go to `notes/` (or raw input to `inbox/`); canonical pages change only with evidence.
- No secrets: no tokens, passwords, private keys, `.env` contents or personal data — only the *names* of keys.
- `hga.config.json` holds the team's settings for the plugin (see the plugin's README).

Validate and rebuild the map after writing (the plugin's skills do this for you):

```
python <plugin>/skills/knowledge/scripts/build_map.py <this folder>
python <plugin>/skills/knowledge/scripts/validate_kb.py <this folder>
```
