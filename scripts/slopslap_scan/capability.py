"""Capability gate for the vendored CommonMark parser (design R4/R8).

The scanner uses the plugin-private vendored markdown-it-py, NEVER an environment copy.
The gate derives the vendor root from this file's real path, prepends it to sys.path,
imports markdown_it + mdurl, and verifies each module's resolved __file__ is BENEATH the
vendor root AND the pinned version matches. Any origin/version mismatch yields an
unavailable result with a reason — the gate never manually deletes, replaces, or aliases a
sys.modules entry (normal imports populate the fresh CLI process's cache; a failed check
leaves those entries untouched until process exit).
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

# scripts/slopslap_scan/capability.py -> scripts/slopslap_scan -> scripts -> repo -> repo/vendor/python
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENDOR_ROOT = os.path.join(_REPO, "vendor", "python")

PINNED = {"markdown_it": "3.0.0", "mdurl": "0.1.2"}


@dataclass
class Capability:
    available: bool
    reason: Optional[str] = None          # not_importable | version_mismatch | origin_mismatch
    detail: str = ""
    modules: dict = field(default_factory=dict)  # name -> {version, origin}
    markdown_it = None                    # the MarkdownIt class when available


def _under(path: str, root: str) -> bool:
    root = os.path.realpath(root)
    return os.path.realpath(path).startswith(root + os.sep)


def gate(vendor_root: str = VENDOR_ROOT) -> Capability:
    if not os.path.isdir(vendor_root):
        return Capability(False, "not_importable", f"vendor root missing: {vendor_root}")
    if vendor_root not in sys.path:
        sys.path.insert(0, vendor_root)
    importlib.invalidate_caches()
    try:
        import markdown_it  # noqa: PLC0415
        import mdurl  # noqa: PLC0415
    except Exception as err:  # noqa: BLE001
        return Capability(False, "not_importable", str(err))

    modules = {}
    for name, mod in (("markdown_it", markdown_it), ("mdurl", mdurl)):
        origin = getattr(mod, "__file__", "") or ""
        if not origin or not _under(origin, vendor_root):
            return Capability(
                False, "origin_mismatch", f"{name} loaded from {origin!r}, not the vendor tree"
            )
        version = getattr(mod, "__version__", None)
        if version != PINNED[name]:
            return Capability(
                False, "version_mismatch",
                f"{name} version {version!r} != pinned {PINNED[name]!r}",
            )
        modules[name] = {"version": version, "origin": os.path.realpath(origin)}

    cap = Capability(True, modules=modules)
    from markdown_it import MarkdownIt  # noqa: PLC0415

    cap.markdown_it = MarkdownIt
    return cap


def recheck_origins(vendor_root: str = VENDOR_ROOT) -> Optional[str]:
    """After parsing, re-verify every loaded parser module still resolves under the vendor
    root (lazy imports). Returns a reason string on mismatch, else None."""
    for name in ("markdown_it", "mdurl"):
        for modname, mod in list(sys.modules.items()):
            if modname == name or modname.startswith(name + "."):
                origin = getattr(mod, "__file__", "") or ""
                if origin and not _under(origin, vendor_root):
                    return f"origin_mismatch: {modname} at {origin}"
    return None
