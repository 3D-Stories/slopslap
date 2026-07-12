# PRD — Kukakuka

**Multi-agent cockpit: a room where AI models work — and talk to each other.**
*(From Hawaiian kūkākūkā — "to consult together how to manage a difficult matter.")*

**Date:** 2026-07-12 · **Status:** DRAFT for owner review · **Owner:** Chris
**Inputs:** problem brief (`drafts/2026-07-12-multiagent-cockpit-problem-brief.md`),
gpt-5.6-sol peer proposal (`docs/reviews/peer-2026-07-12-multiagent-cockpit-problem-brief-2026-07-12.md`),
hardened bus design (`2026-07-12-agora-multi-model-bus-design.md` — mechanics inherited, homelab framing superseded).
**Operating principles (owner-set):** built for **quality, not expediency**; **fail-fast
P0 spikes** immediately after this PRD to settle architecture before real build.

---

## 1. Vision & wedge

A local-first **desktop app (Windows + macOS)** for solo developers: one workspace where
Claude, GPT, GLM — and the human — each occupy a live terminal pane while participating
in a **shared, durable conversation**. It looks and feels like cmux; the difference is
that cmux's agents run isolated and never speak. Here, agents address each other, share
findings, request human decisions, and record dissent — without collapsing into one
opaque orchestrator. The wedge is **coordinated visibility and communication**, not
pane management.

The human is a first-class participant: same message envelope, same ordering; privileged
actions (stop, kill) are explicitly attributed control events.

## 2. Naming (owner direction: story theme)

The org is 3D-Stories; siblings are ChoreStory and SayStory. Hawaiian vocabulary maps
uncannily onto the product (all dictionary-verified via wehewehe.org):
**moʻolelo** = "succession of talk" → story/record (the transcript); **kūkākūkā** =
"consult together how to manage a difficult matter" (the Council); **hoa kūkākūkā** =
"one with whom one confers and deliberates" (an agent in the room); pidgin **talk
story** = converse freely (the shared room). Hawaiian Wikipedia uses Kūkākūkā as its
"Talk:" namespace.

**DECIDED (owner, 2026-07-12): the product is Kukakuka** (ASCII; stylized Kūkākūkā in
prose where the macrons render). *koo-kah-koo-kah.*

Screens run 2026-07-12 (practical screen, NOT legal clearance):
- No existing product/company/app/mark named "kukakuka" found anywhere; npm + PyPI free;
  GitHub target `3D-Stories/kukakuka` free (bare username taken, irrelevant).
- Domains: `.app/.dev/.io/.ai` NXDOMAIN (available); `.com` parked/aftermarket;
  **`.ca` chosen and registered by owner on Cloudflare Registrar** (wholesale ~CAD 10/yr).
- **Standing caution:** KUKA AG holds famous marks in software/robotics classes —
  professional trademark clearance REQUIRED before any commercial launch (fine for
  repo + developer preview). "kuk" substring is a Swedish/Norwegian vulgarity —
  accepted, revisit if Nordic marketing ever matters.

The vocabulary table above is the README naming story. Runner-up TalkStory recorded;
CrewStory/StoryWeave/MindStory and Sol's Threadhall/Meldroom/Polylogue archived.

## 3. Target user

v1: the owner + technically advanced solo developers who already run local coding CLIs
(Claude Code, Codex, etc.) with bring-your-own credentials. Shippable-quality installer,
onboarding, provider validation, and diagnostics from day one — but no accounts, teams,
or cloud service.

## 4. Core jobs

1. Launch the right agent (model+role) in the right directory; see it working live.
2. Talk to one agent, several, or the whole room; agents talk to each other.
3. Let agents exchange findings/handoffs; intervene, answer requests, or stop safely.
4. Run a **Council**: pose a question → models debate rounds → synthesized answer + dissents.
5. Recover the record afterward: durable transcript, exportable diagnostics.

## 5. Primary journey

Create workspace → validate providers (native harnesses first: Claude CLI OAuth, Codex
CLI OAuth, GLM z.ai; CCR fallback lane for keys/local)
→ spawn agents into a pane grid → open the shared room → mention/assign participants →
watch pane output AND semantic messages (distinct surfaces) → answer attention requests
→ stop safely → review/export the outcome.

## 6. Design & UX direction (owner-mandated: settled UP FRONT)

The design is settled before feature code, not bolted on after — mockups and tokens
ship in M2 ahead of any feature UI.

- **What "good" means here:** this is a tool a developer keeps open all day, so it has
  to look considered rather than themed from a template — and it has to stay legible
  under real load (a dozen panes, a fast-moving room). Concretely: a typographic scale
  and spacing system defined up front and held to; color that carries state, never
  decoration; and animation kept to two places only — the attention ring and a message
  arriving — with everything else instant.
- **Accessibility is a requirement, not a pass:** keyboard-navigable throughout, text
  contrast meets WCAG 2.2 AA, `prefers-reduced-motion` disables the ring pulse and the
  message animation, and no dark patterns (nothing nags, nothing hides a cost or a
  cancel).
- **Register:** developer tool, dark-first, GPU-smooth panes — matching cmux on pane
  fluidity is the floor, not the identity.
- **Where the craft goes:** two surfaces carry the product's identity, and they get the
  attention the rest of the UI doesn't need. First, **the attention state** — when an
  agent needs a human or two agents disagree, that has to be obvious at a glance across
  a wall of panes (the ring / unread badge, borrowed from cmux). Second, **the room
  itself** — rendering who said what, to whom, and where they disagree. No other agent
  tool renders a conversation; that view is the thing to get right.
- **Two surfaces, two materials:** raw terminal output and room messages are different
  things and should look different — a PTY pane reads as a terminal, a room message
  reads as speech. They never blur into each other.
- **Deliverable order:** a design brief comes first (tokens, type scale, and the key
  screens drawn — workspace, room, council, onboarding), following the studio pattern,
  and it lands in M2 before feature UI is built. Screens get reviewed against those
  mockups, not improvised in code.
- **Design-consistency constraint feeds §8:** per-platform webviews (Tauri) render
  differently; Chromium (Electron) renders identically. A design-first product weighs
  this for real — P0 spike includes a mac/Windows visual-parity check.

## 7. Functional scope (full v1 scope — slicing in §13 happens with the owner)

**Cockpit core:** workspace create/restore; configurable pane grid (layout-driven,
declarative — cmux borrow); spawn/kill/detach agent sessions; live PTY rendering
(xterm.js); agent status (running/idle/needs-attention/dead); crash recovery for
metadata + history (honest about processes that didn't survive).

**Shared room (the bus):** durable ordered messages (SQLite, autoincrement seq PK —
transactional ordering); mentions/addressing; leased→committed per-participant cursors;
explicit read status (`ok/not_found/empty/corrupt`; corrupt blocks "successful" labels);
unread/attention states; human compose as a peer; PTY-output vs bus-message boundary
("neither path silently substitutes for the other").

**Providers — the connector doctrine (owner requirement 2026-07-12).** The app must
withstand models coming and going. Two rules enforce it:

1. **Connectors are modules, never application code.** Each model ships as an
   out-of-core **connector package** (own manifest: launch spec, transport, capability
   flags, credential requirements, health probe, output parsing, cancellation). The app
   core knows exactly one interface — `AgentSession` + the connector manifest — and
   nothing about any vendor. Adding, breaking, or retiring a model touches one
   connector, zero core. A connector that fails its health probe degrades to a visible
   "unavailable" state; the room and the other agents keep working.
2. **Native-harness-first.** A connector wraps the model's **own harness** (its
   vendor CLI) wherever one exists — that's where subscription **OAuth** lives, where
   the vendor's ToS is honored by construction, and where vendor churn lands first
   (their CLI absorbs their API changes, not our code). Primary transport per turn is
   the harness's **headless exec invocation** (`claude -p`, `codex exec` — owner-
   confirmed first choices), which is exactly the round-based turn model of §3.2:
   - **Claude: native Claude Code CLI — with THREE auth modes, not OAuth-only.**
     ToS research (2026-07-12, primary sources) revised the original "OAuth mandatory"
     requirement: Anthropic's legal page bars subscription OAuth in "any other product,
     tool, or service"; the Agent SDK docs add *"unless previously approved, Anthropic
     does not allow third party developers to offer claude.ai login… for their
     products"*; enforcement is real (Jan 2026 harness blocks, account bans incl.
     false positives); April 2026 moved third-party usage to **paid usage bundles**.
     Anthropic staff simultaneously *encourage* "local development and experimentation
     with the Agent SDK and `claude -p`" on Max. Therefore the connector ships modes:
     1. `oauth-local` — the user's own authenticated `claude`. **Ships as an
        unadvertised, config-gated advanced mode** (owner decision 2026-07-12): normal
        onboarding never presents "log in with your Max plan"; the mode activates only
        by a deliberate opt-in (env var / advanced-config key / explicit
        `--i-understand-oauth-local` flag) the user sets themselves. This keeps the
        *product* from "offering claude.ai login" (the ToS phrase) — the user is
        self-wiring their own local `claude`, which sits inside Anthropic's stated
        "local development and experimentation with `claude -p`" encouragement.
        **Unadvertised ≠ concealed:** the mode is quiet in the UI, NOT cloaked from
        Anthropic — no traffic disguising, no detection evasion (that line is
        explicitly not crossed; enforcement is server-side anyway, so it would be both
        futile and dishonest). Documented residual risk at the opt-in gate:
        harness-detection false positives, policy volatility.
     2. `usage-bundle` — subscription OAuth + Anthropic's April-2026 pay-extra bundles
        (the sanctioned third-party path; what shipped Kukakuka defaults to).
     3. `api-key` — Console key via Agent SDK-style auth (always-clean commercial path).
     Shipped Kukakuka NEVER presents "log in with your Max plan, quota covered" as the
     happy path — that exact shape is what killed OpenClaw. A partnership pre-approval
     ("unless previously approved") is the named channel if subscription-native ever
     matters commercially.
   - **GPT: native Codex CLI (ChatGPT-subscription OAuth) is the primary transport** —
     this REVERSES the earlier "CCR primary / codex fallback" decision, per the
     doctrine. CCR + OpenAI API key remains the built-in fallback lane if S2 shows the
     Codex harness is brittle as a room participant (officially-unsupported caveat
     stands; the fallback exists precisely because vendors change their minds).
   - **Gemini (future): native Gemini CLI (OAuth)** with CCR's gemini transformer as
     its fallback lane.
   - **GLM: no OAuth (it's an API key) — but the SAME subscription-restriction shape,
     stricter (ToS research 2026-07-12, z.ai usage-policy docs).** The GLM Coding Plan
     is *"strictly limited to officially supported tools"* with an explicit
     supported-tools **allowlist**, is *coding-scenario-only*, and enforces automatically
     (error 1302/1303 → throttle → suspend → **permanent ban after 3 strikes**). Three
     modes, mirroring Claude:
     1. `coding-plan-via-native-claude` — the plan key on the z.ai **Anthropic** endpoint
        (`api.z.ai/api/anthropic`) driven by the **real `claude` CLI**. Compliant *by
        construction*: the wire traffic IS Claude Code, which is ON z.ai's allowlist.
        This is why GLM does **NOT** ride the CCR lane (see below). Coding-scenario
        caveat still applies — a non-code Council question may read as out-of-scope;
        surface z.ai policy errors, never silently retry (their codes aren't rate limits).
     2. `metered-api` — z.ai general endpoint (`/api/paas/v4`), pay-as-you-go, **no
        coding-scenario restriction** — the clean shipped/commercial path.
     3. Named channel: **apply for z.ai tool-whitelisting** (they have an application
        path; OpenClaw + Hermes Agent are already on the best-effort tier) if
        Kukakuka ever wants first-class GLM support under its own identity.
     **Danger, now validated:** routing GLM through the CCR/OpenAI-SDK lane hits
     `/api/coding/paas/v4/chat/completions` as unidentified "SDK-based access" — exactly
     the ban trigger. GLM's earlier "no CCR needed" note is now a hard rule: **never
     route the GLM coding plan through CCR.** (A metered `/api/paas/v4` key through CCR
     is fine — no restriction — but that's the paid path, not the subscription.)
   - **Local LLMs (future, definite): Ollama / llama.cpp server IS the native local
     harness**, reached through the CCR translation lane — an Ollama model is one
     connector manifest pointing at `localhost:11434`. S4 carries the proof.

BYO-credential onboarding validates each connector's auth (OAuth session or key) before
first spawn; secrets via OS credential store / references — never in SQLite or logs.

**Workflows:** Council v1 (question → N rounds → synthesizer answer + dissents; round-
based fresh invocations with single prompt-assembly algorithm — immutable question +
last-K window; human-stop state machine: round-boundary stop, `--hard` abort, labeled
artifact `complete|stopped-early|aborted`).

**Ops:** exportable diagnostics; auditable lifecycle + message events; installers
(Win + mac).

## 8. Architecture

**Shape (Sol's proposal, adopted):** a trusted **local control plane** (host process)
owning PTY/ConPTY processes, secret references, SQLite, session lifecycle, and a
loopback-only IPC/event boundary; a React/TS UI subscribing to typed events; a TS domain
layer (conversations, messages, participants, workflow events, adapter contracts).
Future: extract the control plane into a headless daemon → browser/multi-machine clients
attach; conversation-event replication, never shared SQLite files, and sync never grants
remote process control implicitly. **The multi-party collaboration + team-backlog horizon
(§12) is the hardest consumer of this seam** — keep it clean in v1: pod-local process
authority, replicable event log, participant identity in the envelope.

**`AgentSession` abstraction** over the OS substrate — tmux is NOT foundational:
- macOS/Linux: native PTY.
- Windows: ConPTY.
- Optional providers: tmux (Linux/remote) and **psmux** (native Rust tmux-for-Windows
  over ConPTY, tmux command language, **session persistence across terminal close** —
  verified real, github.com/psmux/psmux). psmux could restore tmux symmetry on Windows
  AND deliver the cross-restart process persistence v1 otherwise defers — but it's a
  young single-track project, so it enters as a **P0-evaluated optional provider**,
  never a foundation.

**The platform fork — Tauri 2 vs Electron (open; P0 spike S1 decides):**

| | Tauri 2 | Electron |
|---|---|---|
| PTY layer | `portable-pty` (Rust) — works (prior art exists), less battle-tested | `node-pty` — the most proven PTY binding in existence (VS Code) |
| Rendering | Per-OS webview (WebKit mac / WebView2 win) — **design-consistency risk** for a design-first product | Same Chromium everywhere — pixel-consistent |
| Footprint/startup | ~25× smaller bundles, much lower memory, ~4× faster startup | Heavy |
| Stack fit | **SayStory precedent:** Tauri 2 + Rust core (+ Swift for macOS platform integration) already ships mac DMGs in this shop — mac buildability proven in-house | New-to-shop for desktop |
| Security | Rust host, tighter default model | Mature but broader surface |

Answer to "why not Electron right away": Electron buys the safest PTY layer and perfect
rendering consistency; Tauri buys footprint, security, and the owner's proven
Rust(+Swift) shipping architecture. Quality-not-expediency cuts BOTH ways — node-pty's
maturity is a quality argument, not just convenience. So the PRD does not decide:
**S1 builds the Tauri harness first (proven in-house stack, preferred on fit); Electron
is the pre-approved fallback** if Tauri misses any measurable gate — including the
visual-parity gate.

**Bus:** **SQLite in WAL mode** (ADR-0002), owned by the single-writer host — WAL gives
one writer + concurrent readers, matching the host-serialized write model exactly;
transactional autoincrement PK for ordering; append-only messages + control events,
migrations. The single-writer-host assumption is what makes SQLite correct here (and
what ADR-0002's revisit trigger watches). All hardened-design mechanics inherited (§7 of
the bus design + its §11 adversarial-review resolutions).

**Architecture Decision Log:** every load-bearing structural choice is recorded in
`docs/decisions/` (ADR format + revisit trigger). Current: 0002 SQLite/WAL,
0003 modular native-harness connectors, 0004 multi-mode auth, 0005 AgentSession over
PTY/ConPTY, 0006 round-based turns, 0007 loopback-only trust boundary, 0008 platform
(proposed, S1-gated).

## 9. Trust boundaries

Loopback-only IPC; secrets via OS credential store or env references (never SQLite,
never logs); explicit command previews before an agent-initiated privileged action;
visible provider/credential routing (which key, which endpoint — always inspectable);
bounded adapter permissions; auditable event log.

## 10. Reliability semantics

Displayed ≠ consumed: a message is delivered when committed, not when rendered. Defined
behavior for delivery, cursor recovery, cancellation, crash, restart, orphaned
processes. v1 persists workspace/history/config/lifecycle truth across restarts and
**honestly marks dead sessions** rather than pretending reattachment (psmux, if adopted
as Windows provider, may upgrade this — P0 evidence decides).

## 11. Success measures

First useful multi-agent room < 10 minutes from install; all 3 providers launch;
the human can identify which agent needs attention at a glance; agents exchange ≥1
useful structured handoff; restart preserves the conversation; Council completes with
answer + dissents; the finished screens match the M2 mockups.

## 12. Non-goals (v1)

Cloud service; accounts/teams/collaboration; autonomous coding framework; universal
terminal replacement; remote fleet management; plugin marketplace; worktree automation;
distributed consensus; polished cross-restart process resurrection (unless psmux makes
it cheap on Windows — evidence, not promise). **Bundled v1 adapters stay at three** —
but the extension lanes (§7) are v1 architecture, so Gemini / Ollama-local / OpenRouter
adapters are v1.x config-plus-descriptor additions, not versioned scope.

**Named future horizon — managed subscriptions (owner, 2026-07-12).** Cursor-style:
users subscribe to model access *through* Kukakuka instead of bringing their own
credentials. Architecturally this is a fourth transport the connector doctrine already
holds — the API-key lane with **Kukakuka-brokered credentials** (reseller agreements,
usage metering, spend caps) instead of BYO. Explicitly NOT v1: it requires the KUKA
trademark clearance (unambiguously commercial), vendor reseller terms, and a billing
stack. v1's BYO-credential onboarding is designed so brokered credentials slot in as
just another credential source per connector.

**Named v2 horizon — messaging channels (owner requirement 2026-07-12).** Talk to the
room from **Apple iMessage first** (the established precedent on this server: the
Hermes gateway on darwin with its BlueBubbles iMessage bridge and channel-bound skill
model), then Discord, Slack, Telegram. Architecturally a channel bridge is just an
**alternate human transport**: the human is already a first-class bus participant with
the same message envelope, so inbound channel messages post to the room as the human,
and attention events / round summaries push outbound. Hard constraints when it lands:
it rides the **daemon-extraction path** (a remote channel must NOT breach the v1
loopback boundary); the remote command set is **scoped** (answer attention requests,
stop, status — never arbitrary spawn); every privileged act stays explicitly
attributed. v1 ships the bus seams this needs and nothing more.

**Named FAR horizon — multi-party collaboration + shared team backlog (owner, 2026-07-12).**
The furthest-out phase, and the biggest departure from v1: a **human + their agent
partners** (a "pod") can talk to **another human + their agent partners**, and teams
share a **backlog of work items** that humans and agents pick up from and work on
together. This is where Kukakuka's trajectory bends from *solo cockpit* toward
*collaborative multi-agent workspace* — deliberately deferred, and disciplined by R3
(freeze until the adoption signal proves the single-user room first).

- **Architecture — rides the daemon-extraction seam, hardest consumer of it.** Each
  pod's agents stay **process-local to that human's machine**; only **conversation
  events** replicate across daemons (Sol's rule, extended: sync = immutable event
  replication, never shared SQLite, and **cross-party sync NEVER grants remote process
  control** — a remote teammate can post to a shared room and see shared backlog items,
  never spawn/kill/steer your local agents). The bus envelope already carries
  participants; this adds cross-daemon **pod identity** and shared-channel routing.
- **Team backlog** = a multi-tenant work queue layered on the bus: items with state
  (open / claimed / in-progress / done), claimable by a human or an agent, with the
  room as the coordination surface. **Open design fork:** native Kukakuka backlog vs
  federating an existing tracker (GitHub Projects / Issues — note the rawgentic epic/
  driver queue model is prior art for "agents picking up from a shared queue"). Decide
  at design time.
- **Hard prerequisites this unlocks AFTER (why it's far, not next):** it requires the
  things v1 explicitly refused — **user accounts + identity**, **cross-user authn/authz**,
  and a **networked trust boundary** replacing v1's single-user loopback. It likely
  also wants the managed-subscription billing story. So the gate order is: v1 room proven
  → daemon extraction → identity/auth → messaging channels → *then* multi-party + backlog.
- **Security gravity:** cross-user + autonomous agents multiplies the trust surface.
  Same principle as every other remote horizon, held hard: **process authority is always
  local**; the network carries messages and backlog state, never execution rights.

## 13. Milestones — P0 fail-fast, then slices (SLICING TO BE AGREED WITH OWNER)

**P0 — architecture-settling spikes (fail-fast; ~1–2 weeks; each has a kill/pass gate):**
- **S1 Platform harness:** Tauri 2 + xterm.js + portable-pty on REAL Windows + macOS
  hardware; gates: resize, sustained output, detach, graceful stop, forced kill, crash
  recovery, 60-min responsiveness, **mac/win visual parity on a styled screen**. Any
  gate fails → rebuild harness in Electron/node-pty and re-gate (fallback pre-approved).
- **S2 A2A ingestion + auth-mode validation:** all 3 providers through a PTY — inject
  an addressed message, get a delimited response, cancel, repeat multi-turn. If live
  injection is brittle → fresh-invocation semantic turns (already the Council model)
  confirmed as the bus participation mode. **Auth gate:** run `oauth-local` Claude at
  council cadence and watch for harness-detection friction (the Jan-2026 block class);
  any credential error or warning → document and demote `oauth-local` guidance.
- **S3 psmux evaluation:** Windows session provider candidate — persistence across
  terminal close, ConPTY fidelity, stability under agent workloads. Pass → optional
  provider in M1 scope; fail → note and drop.
- **S4 CCR fidelity + concurrency:** translation faithfulness for our shapes; ≥2 GPT
  agents through one CCR instance. **Bonus (extensibility proof): one Ollama model on
  the homelab GPU box joins a room through the same CCR lane** — passes = "add a model
  = config entry" demonstrated with zero core change.
- **P0 exit gate (the rawgentic-next Phase-0 pattern):** platform + substrate decisions
  LOCKED and written back into this PRD; all downstream milestones revalidated against
  spike evidence.

**Proposed slices after P0 (to slice together once full scope is agreed):**
- **M1 Foundation:** control plane, AgentSession providers, SQLite bus + cursors, adapter
  contract + 3 adapters, secret broker. (Engine, no product UI.)
- **M2 Design + cockpit:** design brief/tokens/mockups FIRST (§6), then workspace, pane
  grid, spawn/kill/detach, live panes, status, onboarding + provider validation.
- **M3 The room:** shared channel, mentions, attention states, human compose, Council
  workflow end-to-end, stop machinery.
- **M4 Ship:** hardening, installers (Win dmg? — Win installer + mac DMG), diagnostics
  export, crash recovery polish, developer-preview release + the 5-external-devs
  product test (Sol's adoption signal).

## 14. Release gates

P0 gates above; credentials never appear in logs/db (test-enforced); message ordering +
cursor recovery survive forced termination; process-tree termination reliable on both
OSes; 60-minute sessions stay responsive; design bar signed off against mockups;
the two-surface boundary holds (no PTY-scrape masquerading as a bus message).

## 15. Risks

1. **A2A comms as theater** (Sol) — killed or confirmed by S2 in week 1; fresh-turn
   fallback already designed.
2. **Cross-platform PTY lifecycle eats the schedule** (Sol) — S1 before ANY UI spend.
3. **Everything-app sprawl** (Sol) — §12 non-goals frozen until the 5-dev signal; the
   room is the wedge, not panes, not workflows.
4. **Webview rendering divergence vs the design bar** — S1 visual-parity gate; Electron
   fallback bought and paid for.
5. **psmux immaturity** — optional provider only, never foundation; S3 evidence-gated.
6. **CCR under concurrent load** — S4.
7. **Subscription-auth policy volatility — Claude AND GLM (evidence-backed).**
   Anthropic shifted 3× in 4 months (Jan blocks → Feb ban → Apr usage bundles), banned
   accounts (acknowledged false positives). **z.ai/GLM is the same shape, stricter:**
   coding-scenario-only, supported-tools allowlist, automatic 3-strike permanent ban
   (error 1302/1303). Mitigations: multi-mode connectors for BOTH (§7) so no single
   policy change strands the app; shipped default = metered/bundle/key, never bare
   subscription; GLM coding plan runs ONLY via native `claude` (compliant-by-
   construction) and **never via CCR** (the SDK-access ban trigger); z.ai policy errors
   surfaced not retried. GPT is the resilient anchor — OpenAI **explicitly permits**
   Codex OAuth in third-party tools — so the room degrades gracefully if either Claude
   or GLM tightens. S2 auth gate exercises Claude `oauth-local` + GLM coding-plan under
   council cadence.

## 16. Open questions

- Name pick (§2) + availability checks — blocks repo creation.
- Tauri vs Electron — S1 output, locked at P0 exit.
- psmux adoption — S3 output.
- Where the SayStory Swift layer's patterns (signing, notarization, TCC-adjacent mac
  integration) transfer — M4 concern, noted now.
- Daemon extraction timing (post-v1) and multi-machine rooms (explicitly out).
