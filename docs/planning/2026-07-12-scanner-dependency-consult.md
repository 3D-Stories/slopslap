# slopslap scanner dependency — focused design question for a peer

## Context
slopslap is a Claude Code **plugin** (installable / shareable). One component is
`scripts/scan_prose.py` — a **measurement-only** prose scanner: it emits metrics
(sentence-length distribution, repeated openers, transition clusters, punctuation
rates, etc.) and **never** verdicts. It never authorizes an edit by itself; the
invariant ledger + deterministic verification do that. The scanner is advisory (soft
flags, candidate selection only).

For **Markdown** input the scanner needs a real CommonMark parser to correctly
**exclude** fenced/indented code, HTML blocks, blockquotes (default), link
destinations (keep visible text), autolinks/bare URLs, and inline code — and to retain
heading/list text tagged with its structural type. Getting these exclusions wrong means
measuring the wrong regions, which produces misleading soft flags.

The current spec names **`markdown-it-py`** as that parser and **explicitly forbids a
"silent approximate fallback"** (no pretending plain-text splitting is CommonMark). A
plain-text scanner ships first and needs **no** third-party dependency.

## Problem
Claude Code plugins have **no managed virtualenv and no dependency manager**. A plugin's
scripts run under whatever Python the user's Claude Code process provides. A hard
`import markdown_it` therefore fails for most users unless something installs it. How
should a **distributable** Claude Code plugin satisfy (or avoid) a third-party Python
dependency like `markdown-it-py`?

## Constraints / values
- **Zero-config install** is a strong plugin value. A manual `pip install` step is
  friction and a support burden.
- **No silent wrong answers.** If the Markdown parser is unavailable, the scanner must
  NOT silently emit approximate (wrong-region) metrics that then anchor edit decisions.
- **Scanner is advisory only.** It never authorizes an edit — the invariant ledger +
  deterministic verify do. So a *degraded or absent* scanner is tolerable **iff** it
  fails loudly and the rest of the pipeline still works.
- **Cross-platform** (Linux/macOS/Windows). Python 3 **stdlib-only** is the safe floor.
- **Vendoring** adds maintenance + license surface. **Runtime pip-install-on-first-use**
  adds a network + write-permission dependency and can fail in locked-down environments.

## Question for the peer
Propose the best approach (or a ranked set) for how `scan_prose.py` should obtain
CommonMark parsing in a distributable Claude Code plugin. Weigh at least:
- (a) **vendor** the parser into the plugin tree,
- (b) **degrade to the plain-text scanner** with a loud capability notice when the
  parser is absent (Markdown metrics simply unavailable, never approximated),
- (c) a **documented one-time `pip install`** as a prerequisite,
- (d) a **pure-stdlib minimal CommonMark subset** sufficient only for the exclusion
  rules the scanner needs (not a full renderer),
- (e) anything better.

State the tradeoffs and give a clear recommendation, including what the MVP should do
versus what can wait.
