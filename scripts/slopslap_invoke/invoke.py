"""Bounded fresh-context ``claude -p`` runner + the CLOSED ``invoke_semantic`` public API.

The runner (``_run_claude``, module-private) launches the CLI in its OWN process group
(``start_new_session=True``) in a fresh empty temp cwd with a scrubbed environment, delivers
the request on stdin, and drains stdout/stderr under a hard byte cap. It NEVER raises on an
environmental failure — every failure is an explicit ``InvocationResult.status``. On timeout
it SIGTERMs the whole group, waits a short grace, then SIGKILLs — reaping descendants too.

``invoke_semantic`` is the only public entry: it builds the request via ``contract``, runs
the CLI, and returns EXACTLY ``{"verdict", "concerns"}`` — the ``normalize_semantic`` input
shape. Every failure status collapses to ``{"verdict": "ambiguous", "concerns": []}`` with a
stable diagnostic logged to ``slopslap.invoke``; the ``InvocationResult`` never leaks out.

Platform: Linux/macOS (the plugin's supported platforms) — relies on POSIX process groups.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Optional

from . import contract

_LOG = logging.getLogger("slopslap.invoke")

# Hard cap on drained stdout/stderr — a runaway CLI cannot exhaust memory (kill group, fail).
_MAX_STDOUT_BYTES = 5 * 1024 * 1024
_STDERR_TAIL_BYTES = 4096
_KILL_GRACE_S = 3.0

# The child env is scrubbed to this minimal allowlist so no rewriter/ambient state leaks in:
#   - HOME, PATH  : auth-credential discovery (~/.claude) and executable resolution
#   - CLAUDE_*, ANTHROPIC_*, XDG_* : Claude Code auth/config surface (the plugin's real config)
# Everything else (secrets, project vars, the rewriter's environment) is dropped.
_ENV_ALLOW_NAMES = frozenset({"HOME", "PATH"})
_ENV_ALLOW_PREFIXES = ("CLAUDE", "ANTHROPIC", "XDG")

# stable diagnostic codes (logged only; NEVER carried in the public {verdict, concerns} dict)
_DIAG_TRANSPORT = "semantic_transport_error"
_DIAG_TIMEOUT = "semantic_timeout"
_DIAG_INVALID = "semantic_invalid_response"

_AMBIGUOUS: dict = {"verdict": "ambiguous", "concerns": []}


def _record_status(sink: Optional[dict], status: str) -> None:
    """Record ``invocation_status`` into ``sink`` (the #27 §7 out-param), STICKY-WORST: once a
    non-``ok`` status is recorded, a later ``ok`` never overwrites it (a later successful call
    must not launder an earlier timeout/failure). ``sink is None`` is a no-op — the default keeps
    ``invoke_semantic`` byte-identical to its pre-#27 behavior."""
    if sink is None:
        return
    if status == "ok" and sink.get("invocation_status", "ok") != "ok":
        return
    sink["invocation_status"] = status


@dataclass
class InvocationResult:
    """Internal transport result. NEVER crosses the public ``invoke_semantic`` boundary."""

    status: str  # ok | timeout | cli_missing | nonzero_exit | parse_error | model_mismatch
    result_text: Optional[str] = None
    envelope: Optional[dict] = None
    duration_s: float = 0.0
    stderr_tail: str = ""
    diagnostic_code: Optional[str] = None


def _scrub_env() -> dict:
    return {
        k: v
        for k, v in os.environ.items()
        if k in _ENV_ALLOW_NAMES or k.startswith(_ENV_ALLOW_PREFIXES)
    }


def _reported_models(envelope) -> list:
    """The models the CLI says actually ran. `claude -p --output-format json` (v2.1.207) has NO
    top-level `model` field; the resolved model id(s) live in the `modelUsage` dict keys
    (e.g. {"claude-sonnet-5": {...}}). Return every reported id, or [] if none is available."""
    if not isinstance(envelope, dict):
        return []
    out = []
    mu = envelope.get("modelUsage")
    if isinstance(mu, dict):
        out.extend(k for k in mu if isinstance(k, str) and k)
    m = envelope.get("model")  # tolerate a future/renamed top-level field too
    if isinstance(m, str) and m:
        out.append(m)
    return out


def _model_confirmed(requested: str, reported: list) -> bool:
    """Confirm the requested model actually ran. The request uses an ALIAS (e.g. "sonnet"); the
    CLI reports a canonical id (e.g. "claude-sonnet-5"). Match if the alias appears as a token in
    any reported id (so "sonnet" ~ "claude-sonnet-5"), or exact-equals one. Empty `reported`
    means the CLI told us nothing — NOT confirmed (fail closed: an unverifiable model identity is
    never treated as a match)."""
    if not reported:
        return False
    req = requested.lower()
    for r in reported:
        rl = r.lower()
        # exact, or the alias as a whole TOKEN of the canonical id ("sonnet" ~ "claude-sonnet-5").
        # #31e: NO loose substring fallback — a distinct model whose id merely CONTAINS the alias
        # (e.g. requesting "opus" against "claude-opusx-9") must not be wrongly confirmed.
        if req == rl or req in rl.replace("-", " ").replace("_", " ").split():
            return True
    return False


def _drain(stream, chunks: list, over_cap: threading.Event, pgid: int, ring: Optional[int] = None) -> None:
    """Read a pipe to EOF, appending chunks; if the cap is exceeded, kill the group and stop. With
    ``ring`` set (stderr: we only keep a short tail for diagnostics, #31e), retain just the last
    ``ring`` bytes so a runaway stderr costs O(ring) memory, not O(_MAX_STDOUT_BYTES) — the total-byte
    cap kill still fires, so the DoS guard is unchanged."""
    total = 0
    # read1: return whatever is available now (one underlying read), never block for a full
    # buffer — otherwise a slow/oversized producer would only trip the cap at EOF/kill.
    reader = stream.read1 if hasattr(stream, "read1") else stream.read
    try:
        while True:
            chunk = reader(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_STDOUT_BYTES:
                over_cap.set()
                _killpg(pgid, signal.SIGKILL)
                break
            chunks.append(chunk)
            if ring is not None and total > ring:
                # collapse to the last `ring` bytes; memory stays bounded regardless of stderr volume.
                chunks[:] = [b"".join(chunks)[-ring:]]
    except (ValueError, OSError):
        pass


def _killpg(pgid: int, sig) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _run_claude(request: str, *, model: str, timeout_s: float, executable: str) -> InvocationResult:
    """Run one fresh-context ``claude -p`` invocation under the pinned lockdown argv.

    Returns an ``InvocationResult`` with an explicit status; never raises on environmental
    failure. Raises ``ValueError`` only for a caller bug (empty model).
    """
    if not model:
        raise ValueError("model must be a non-empty string")

    # EXACT pinned lockdown argv (proven live in the Task-1 probe). Request on stdin; never
    # shell=True; no --resume/--continue/--fallback-model by construction.
    argv = [
        executable, "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--tools", "",
        "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}',
    ]

    cwd = tempfile.mkdtemp(prefix="slopslap-invoke-")
    start = time.monotonic()
    try:
        try:
            proc = subprocess.Popen(  # noqa: S603 - argv list, no shell, scrubbed env
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=_scrub_env(),
                start_new_session=True,  # own process group -> whole-tree kill on timeout/cap
            )
        except FileNotFoundError:
            return InvocationResult(status="cli_missing", duration_s=time.monotonic() - start,
                                    diagnostic_code=_DIAG_TRANSPORT)
        except OSError as err:
            # PermissionError, ENOEXEC, resource exhaustion, bad cwd — any launch failure must
            # fail closed as a transport error, never propagate out of the closed seam.
            return InvocationResult(status="nonzero_exit", duration_s=time.monotonic() - start,
                                    stderr_tail=repr(err)[-_STDERR_TAIL_BYTES:],
                                    diagnostic_code=_DIAG_TRANSPORT)

        pgid = proc.pid  # start_new_session=True => proc is its own group leader (pgid == pid)
        over_cap = threading.Event()
        out_chunks: list = []
        err_chunks: list = []
        t_out = threading.Thread(target=_drain, args=(proc.stdout, out_chunks, over_cap, pgid))
        t_err = threading.Thread(target=_drain, args=(proc.stderr, err_chunks, over_cap, pgid),
                                 kwargs={"ring": _STDERR_TAIL_BYTES * 4})  # #31e: keep only a tail
        t_out.start()
        t_err.start()

        # Write stdin from a thread. A request larger than the OS pipe buffer (~64 KiB) would
        # block a synchronous write until the child drains it — and a child that never reads
        # stdin would then wedge us BEFORE proc.wait's timeout could fire, defeating the hard
        # bound. Off-thread, proc.wait(timeout) governs regardless of request size or child
        # behavior; on timeout the process-group kill (below) unblocks this writer.
        def _feed_stdin():
            try:
                proc.stdin.write(request.encode("utf-8"))
                proc.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass

        t_in = threading.Thread(target=_feed_stdin)
        t_in.start()

        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=_KILL_GRACE_S)
            except subprocess.TimeoutExpired:
                _killpg(pgid, signal.SIGKILL)
                proc.wait()

        # The leader has exited, but a backgrounded descendant may still hold the stdout/stderr
        # pipe open, so a drain thread would block on EOF forever and the joins below would hang
        # past timeout_s. SIGKILL the whole group unconditionally (harmless if already gone) to
        # close every inherited pipe end, then bound the joins so no reader can wedge us.
        _killpg(pgid, signal.SIGKILL)
        t_in.join(timeout=_KILL_GRACE_S)
        t_out.join(timeout=_KILL_GRACE_S)
        t_err.join(timeout=_KILL_GRACE_S)
        duration = time.monotonic() - start
        stderr_tail = b"".join(err_chunks)[-_STDERR_TAIL_BYTES:].decode("utf-8", "replace")

        if over_cap.is_set():
            return InvocationResult(status="parse_error", duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_INVALID)
        if timed_out:
            return InvocationResult(status="timeout", duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_TIMEOUT)
        if proc.returncode != 0:
            return InvocationResult(status="nonzero_exit", duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_TRANSPORT)

        stdout_text = b"".join(out_chunks).decode("utf-8", "replace")
        try:
            envelope = json.loads(stdout_text)
        except (ValueError, TypeError):
            return InvocationResult(status="parse_error", result_text=stdout_text,
                                    duration_s=duration, stderr_tail=stderr_tail,
                                    diagnostic_code=_DIAG_INVALID)

        # An errored envelope can still exit 0 (max-turns, refusal). Consult it explicitly rather
        # than relying on the result text coincidentally failing to parse as a verdict.
        if isinstance(envelope, dict) and envelope.get("is_error"):
            return InvocationResult(status="nonzero_exit", result_text=stdout_text,
                                    envelope=envelope, duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_TRANSPORT)

        # Confirm the model we asked for actually ran. Absent confirmation (empty reported list)
        # fails closed to ambiguous — an unverifiable model identity is never a trusted verdict.
        if not _model_confirmed(model, _reported_models(envelope)):
            return InvocationResult(status="model_mismatch", result_text=stdout_text,
                                    envelope=envelope, duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_INVALID)

        return InvocationResult(status="ok", result_text=stdout_text, envelope=envelope,
                                duration_s=duration, stderr_tail=stderr_tail)
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def invoke_semantic(
    original: bytes,
    revision: str,
    ledger_canonical: dict,
    *,
    model: str,
    timeout_s: float = 60.0,
    executable: Optional[str] = None,
    status_sink: Optional[dict] = None,
) -> dict:
    """CLOSED public semantic seam. Returns EXACTLY ``{"verdict", "concerns"}``.

    Bind the keywords for the ``verify(..., semantic_fn=...)`` 3-positional seam with
    ``functools.partial(invoke_semantic, model=..., timeout_s=...)``. Every failure collapses
    to ``{"verdict": "ambiguous", "concerns": []}`` (never "clean") with a diagnostic logged.

    ``status_sink`` (#27 §7 — additive, default-inert) is an optional dict the caller supplies to
    learn the typed invocation OUTCOME without breaking the closed ``{verdict, concerns}`` return.
    When non-None, ``status_sink["invocation_status"]`` is set on EVERY return path — ``ok`` only
    on a successfully parsed model verdict, else the failure slug (``timeout``/``cli_missing``/
    ``nonzero_exit``/``parse_error``/``model_mismatch``/``invalid_request``). It is STICKY-WORST
    (see ``_record_status``): a later ``ok`` never launders an earlier failure — the seam may be
    re-invoked many times per run by apply's re-verify loop. ``None`` (default) is a no-op, so the
    return shape and behavior are byte-identical to the pre-#27 seam.
    """
    if not model:
        raise ValueError("model must be a non-empty string")

    # The verify() seam passes revision as BYTES (apply_edits output); the contract wants text.
    # Decode STRICT utf-8 here — a non-utf-8 revision fails closed to ambiguous, never "clean".
    if isinstance(revision, (bytes, bytearray)):
        try:
            revision = bytes(revision).decode("utf-8")
        except UnicodeDecodeError as err:
            _LOG.warning("%s: revision is not valid utf-8: %s", _DIAG_INVALID, err)
            _record_status(status_sink, "invalid_request")
            return dict(_AMBIGUOUS)

    exe = executable if executable is not None else shutil.which("claude")
    if not exe:
        _LOG.warning("%s: claude executable not found (which('claude') is None)", _DIAG_TRANSPORT)
        _record_status(status_sink, "cli_missing")
        return dict(_AMBIGUOUS)

    # The seam is documented as TOTAL: it never raises on any input. `original` is meant to be
    # bytes and `ledger_canonical` a well-formed ledger, but both come from internal code — a
    # str original (no .decode) or a structurally-bad ledger entry (missing id/source key) must
    # still fail closed to ambiguous, not propagate out of the closed boundary.
    try:
        request = contract.build_request(original, revision, ledger_canonical)
    except contract.InvalidRequestError as err:
        _LOG.warning("%s: request build rejected: %s", _DIAG_INVALID, err)
        _record_status(status_sink, "invalid_request")
        return dict(_AMBIGUOUS)
    except (AttributeError, KeyError, TypeError) as err:
        _LOG.warning("%s: malformed original/ledger at request build: %r", _DIAG_INVALID, err)
        _record_status(status_sink, "invalid_request")
        return dict(_AMBIGUOUS)

    result = _run_claude(request, model=model, timeout_s=timeout_s, executable=exe)
    if result.status != "ok":
        _LOG.warning("%s: invocation failed (status=%s)", result.diagnostic_code, result.status)
        _record_status(status_sink, result.status)
        return dict(_AMBIGUOUS)

    try:
        parsed = contract.parse_response(result.result_text, ledger_canonical)
    except (AttributeError, KeyError, TypeError) as err:
        _LOG.warning("%s: malformed ledger at response parse: %r", _DIAG_INVALID, err)
        _record_status(status_sink, "parse_error")
        return dict(_AMBIGUOUS)
    _record_status(status_sink, "ok")
    return parsed


# --------------------------------------------------------------------------- #102: judge transport
# A SECOND, independent runner for the blind paired-preference eval's LLM judge. The judge runs on a
# different vendor than the rewrite engine (cross-model), so the transport is the Codex CLI
# (`codex exec`), not `claude -p`. Same lockdown philosophy as `_run_claude` — fresh empty temp cwd,
# scrubbed env, own process group, SIGTERM->SIGKILL on timeout, never raises on an environmental
# failure — but a separate function: `_run_claude` is security-hardened and pinned by tests, and a
# shared "run any CLI" abstraction would widen its surface for no gain.
# NOT `_ENV_ALLOW_PREFIXES + ("CODEX",)`: that list exists for the Anthropic transport, and
# reusing it here hands every CLAUDE_*/ANTHROPIC_* variable — an API key among them — to a
# DIFFERENT vendor's process. The judge needs neither. Codex auth lives under HOME (~/.codex).
_CODEX_ENV_ALLOW_PREFIXES = ("CODEX", "XDG")


def _scrub_env_codex() -> dict:
    return {
        k: v
        for k, v in os.environ.items()
        if k in _ENV_ALLOW_NAMES or k.startswith(_CODEX_ENV_ALLOW_PREFIXES)
    }


def _run_codex(request: str, *, model: str, timeout_s: float, executable: str, schema: dict,
               reasoning_effort: str = "medium") -> InvocationResult:
    """Run one `codex exec` judge call under the pinned lockdown argv (probed live 2026-09-02).

    The prompt goes on stdin; the answer comes back through `--output-schema` + `-o` (a JSON object
    the CLI validates against the schema) — never parsed out of free text. The CLI reports NO model
    identity in any output, so `envelope` carries the parsed `-o` object and the caller must treat
    the model as pinned-by-request, not confirmed. Returns an explicit status; raises `ValueError`
    only for a caller bug (empty model).
    """
    if not model:
        raise ValueError("model must be a non-empty string")
    cwd = tempfile.mkdtemp(prefix="slopslap-judge-")
    start = time.monotonic()
    try:
        schema_path = os.path.join(cwd, "schema.json")
        out_path = os.path.join(cwd, "out.json")
        # 0600 from creation: the answer file is written by the CLI, but the schema is ours.
        with os.fdopen(os.open(schema_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600),
                       "w", encoding="utf-8") as fh:
            json.dump(schema, fh)
        argv = [
            executable, "exec",
            "-m", model,
            "--sandbox", "read-only",
            "--output-schema", schema_path,
            "-o", out_path,
            "-c", f"model_reasoning_effort={reasoning_effort}",
            "--ephemeral",
            "--color", "never",
            "-c", "project_doc_max_bytes=0",
            "-C", cwd,
            "--skip-git-repo-check",
            "-",
        ]
        try:
            proc = subprocess.Popen(  # noqa: S603 - argv list, no shell, scrubbed env
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=_scrub_env_codex(),
                start_new_session=True,
            )
        except FileNotFoundError:
            return InvocationResult(status="cli_missing", duration_s=time.monotonic() - start,
                                    diagnostic_code=_DIAG_TRANSPORT)
        except OSError as err:
            return InvocationResult(status="nonzero_exit", duration_s=time.monotonic() - start,
                                    stderr_tail=repr(err)[-_STDERR_TAIL_BYTES:],
                                    diagnostic_code=_DIAG_TRANSPORT)

        pgid = proc.pid  # own group leader (start_new_session=True)
        timed_out = False
        err_bytes = b""
        try:
            # ponytail: communicate() has no byte cap — the judge's stdout is the CLI's final
            # message only (the answer rides in `-o`). Upgrade path: the _drain cap from _run_claude.
            _out, err_bytes = proc.communicate(request.encode("utf-8"), timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _killpg(pgid, signal.SIGTERM)
            try:
                proc.wait(timeout=_KILL_GRACE_S)
            except subprocess.TimeoutExpired:
                _killpg(pgid, signal.SIGKILL)
                proc.wait()
            _killpg(pgid, signal.SIGKILL)  # close every inherited pipe end (descendants too)
            try:
                _out, err_bytes = proc.communicate(timeout=_KILL_GRACE_S)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                err_bytes = b""
        duration = time.monotonic() - start
        stderr_tail = (err_bytes or b"")[-_STDERR_TAIL_BYTES:].decode("utf-8", "replace")

        if timed_out:
            return InvocationResult(status="timeout", duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_TIMEOUT)
        if proc.returncode != 0:
            return InvocationResult(status="nonzero_exit", duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_TRANSPORT)
        try:
            with open(out_path, "r", encoding="utf-8") as fh:
                payload = fh.read()
        except OSError:
            payload = ""
        if not payload.strip():
            # exit 0 with no answer file is NOT an answer — fail closed, never fall back to stdout.
            return InvocationResult(status="parse_error", duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_INVALID)
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            return InvocationResult(status="parse_error", result_text=payload, duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_INVALID)
        if not isinstance(obj, dict):
            return InvocationResult(status="parse_error", result_text=payload, duration_s=duration,
                                    stderr_tail=stderr_tail, diagnostic_code=_DIAG_INVALID)
        return InvocationResult(status="ok", result_text=payload, envelope=obj,
                                duration_s=duration, stderr_tail=stderr_tail)
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def models_match(alias: str, reported) -> bool:
    """Public form of the requested-vs-reported token rule (`_model_confirmed`), for callers that
    must compare two model identities — e.g. the eval's cross-model guard (judge != engine)."""
    return _model_confirmed(alias, list(reported or []))


def invoke_judge(
    request: str,
    *,
    model: str,
    schema: dict,
    timeout_s: float = 180.0,
    executable: Optional[str] = None,
    status_sink: Optional[dict] = None,
    reasoning_effort: str = "medium",
) -> Optional[dict]:
    """CLOSED public judge seam (#102). Returns the schema-shaped JSON object the judge wrote, or
    ``None`` on ANY failure (logged with a diagnostic code; never raises on an environmental
    failure). The caller validates the object's CONTENT — this seam only guarantees "a JSON
    object came back from a run that exited 0".

    ``status_sink`` follows `invoke_semantic`'s contract (sticky-worst ``invocation_status``) and
    additionally carries ``model_confirmed`` — always ``False`` for this transport, because the
    Codex CLI reports no model identity in its output; the model is pinned by ``-m`` only.
    """
    if not model:
        raise ValueError("model must be a non-empty string")
    if not isinstance(schema, dict) or not schema:
        raise ValueError("schema must be a non-empty dict")
    if status_sink is not None:
        status_sink["model_confirmed"] = False
    exe = executable if executable is not None else shutil.which("codex")
    if not exe:
        _LOG.warning("%s: codex executable not found (which('codex') is None)", _DIAG_TRANSPORT)
        _record_status(status_sink, "cli_missing")
        return None
    result = _run_codex(request, model=model, timeout_s=timeout_s, executable=exe, schema=schema,
                        reasoning_effort=reasoning_effort)
    if result.status != "ok":
        _LOG.warning("%s: judge invocation failed (status=%s)", result.diagnostic_code, result.status)
        _record_status(status_sink, result.status)
        return None
    _record_status(status_sink, "ok")
    return result.envelope
