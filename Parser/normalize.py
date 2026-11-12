"""
Deterministic function-name normalization for View8.

Problem
-------
The V8 disassembly embeds live heap addresses in every SharedFunctionInfo /
BytecodeArray header, and View8 folds that address into each function name:

    func_<label>_0x<heap_address>        e.g. func_start_0xd64c9c1dcd9

The heap base is ASLR-randomized, so disassembling the same JSC file twice yields
different addresses and therefore different names -- the decompiled output is
non-deterministic and diffs are full of spurious churn. Worse, address-derived
schemes (even rebasing to a fixed base) also drift across *different disassembler
/ V8 builds*, because the relative object layout -- not just the base -- changes
between builds.

Model: index onto a hardcoded base
----------------------------------
Each function is named by its position in the parse traversal, offset from a
fixed virtual base:

    normalized_name = func_<label>_0x<VIRTUAL_BASE + parse_index>

The parse index follows the recursive-descent walk of the disassembly structure
(function nesting / constant-pool order), which is a property of the compiled
program's *structure*, not of the heap layout. So the names are identical:

  * across re-disassembly of the same file (different ASLR base), and
  * across different disassembler / decompiler builds that lay the same program
    out at different addresses,

as long as the set of functions and their traversal order are the same. Folding
in VIRTUAL_BASE keeps the familiar func_<label>_0x<va> shape so the output reads
like the disassembly rather than a bare counter.

(Note: index is stable against address/layout changes, but it is positional --
adding or removing a function shifts the indices of everything after it. That is
inherent to any structural naming and is the intended trade for layout
independence.)

This is a *post-parse* pass: the parser's reference bookkeeping is untouched
(every const-pool reference, `declarer` link and dict key already points at the
exact same name string), so normalization rewrites that string everywhere via an
exact alternation of the known names -- robust to labels containing spaces or
other characters (e.g. accessors emitted as `func_get entries_0x..`). New names
are sanitized to clean identifiers so downstream tooling keeps working.
"""

import csv
import os
import re
from typing import Dict, List, Optional, Pattern

# Recovers the <label> from an address-based name. `.*` is greedy and tolerates
# spaces / dots / any character in the label.
_LABEL_RE = re.compile(r'^func_(.*)_0x[0-9a-fA-F]+$')

# Characters kept verbatim in a normalized label; everything else -> '_'.
_NON_IDENT_RE = re.compile(r'[^A-Za-z0-9_$]')

# Hardcoded virtual base folded into every normalized name so it reads like an
# address (func_<label>_0x<base + index>).
K_VIRTUAL_BASE = 0x100000000

# Code-line attributes that may embed function names once decompilation has run.
# Empty on a freshly parsed function (normalization runs before decompile), but
# sweeping them keeps this pass correct if applied to already-decompiled input.
_CODE_TEXT_ATTRS = ("inst", "translated", "decompiled")


def _short_label(old_name: str) -> str:
    """Recover the raw <label> portion of a function name, defensively."""
    m = _LABEL_RE.match(old_name)
    if m:
        return m.group(1) or "unknown"
    if old_name.startswith("func_"):
        stripped = old_name[len("func_"):]
        return stripped.rsplit("_", 1)[0] if "_" in stripped else stripped
    return old_name


def _sanitize_label(label: str) -> str:
    """Turn an arbitrary V8 name into a clean identifier fragment.

    'get entries' -> 'get_entries'. Collisions between distinct raw labels are
    harmless: uniqueness of the final name is guaranteed by the index.
    """
    clean = _NON_IDENT_RE.sub("_", label).strip("_")
    return clean or "unknown"


def _build_name_matcher(old_names: List[str]) -> Pattern:
    """Compile a regex matching exactly the known function names.

    Longest-first alternation of escaped names, bounded by non-identifier
    lookarounds so a shorter name can never match inside a longer one. Robust to
    any character a V8 name may contain (spaces, dots, '$', etc.).
    """
    ordered = sorted(old_names, key=len, reverse=True)
    alternation = "|".join(re.escape(n) for n in ordered)
    return re.compile(r'(?<![A-Za-z0-9_$])(?:' + alternation + r')(?![A-Za-z0-9_$])')


def _build_index_mapping(old_names: List[str], virtual_base: int) -> Dict[str, str]:
    """func_<label>_0x<addr>  ->  func_<clean label>_0x<virtual_base + parse index>.

    old_names is in parse (dict insertion) order, which reflects the deterministic
    recursive-descent traversal of the disassembly structure. The index is a
    global running position, so names are unique regardless of duplicate labels.
    """
    count = len(old_names)
    width = len(f"{virtual_base + max(count - 1, 0):x}")
    mapping = {}
    for i, old in enumerate(old_names):
        label = _sanitize_label(_short_label(old))
        mapping[old] = f"func_{label}_0x{virtual_base + i:0{width}x}"
    return mapping


def write_name_mapping_csv(mapping: Dict[str, str], output_path: str) -> None:
    """Write the original-to-normalized function-name mapping as CSV.

    The dictionary insertion order is preserved, so rows follow the same parse
    order used to assign normalized identifiers.
    """
    parent_dir = os.path.dirname(os.path.abspath(output_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["original_name", "normalized_name"])
        writer.writerows(mapping.items())


def _apply_mapping(all_func: Dict[str, object],
                   mapping: Dict[str, str],
                   name_matcher: Pattern) -> Dict[str, object]:
    """Rewrite every occurrence of an old name to its new name.

    Returns a new dict with rewritten keys, preserving insertion order (hence
    determinism). Rewrites, per SFI: `name`, `declarer`, constant-pool
    references, and any function names embedded in decompiled code text (a no-op
    for freshly parsed, not-yet-decompiled functions).
    """

    def sub_names(text: str) -> str:
        return name_matcher.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)

    for sfi in all_func.values():
        if getattr(sfi, "name", None) in mapping:
            sfi.name = mapping[sfi.name]
        if getattr(sfi, "declarer", None) in mapping:
            sfi.declarer = mapping[sfi.declarer]

        if sfi.const_pool:
            sfi.const_pool = [
                sub_names(e) if isinstance(e, str) else e
                for e in sfi.const_pool
            ]

        for line in (getattr(sfi, "code", None) or []):
            for attr in _CODE_TEXT_ATTRS:
                val = getattr(line, attr, None)
                if isinstance(val, str) and "func_" in val:
                    setattr(line, attr, sub_names(val))

    return {mapping.get(k, k): v for k, v in all_func.items()}


def normalize_function_names(all_func: Dict[str, object],
                             virtual_base: int = K_VIRTUAL_BASE,
                             verbosity: int = 0,
                             mapping_csv: Optional[str] = None) -> Dict[str, object]:
    """
    Rename functions by parse-order index onto a hardcoded virtual base.

    Parameters
    ----------
    all_func : dict[str, SharedFunctionInfo]
        The parsed function map (insertion order == deterministic parse order).
    virtual_base : int
        Base folded into every name (default K_VIRTUAL_BASE, 0x100000000).
    verbosity : int
        >0 prints a short summary.
    mapping_csv : str or None
        Optional path for a CSV containing ``original_name,normalized_name``.

    Returns the rebuilt function map. Callers must use the return value, since
    the dict keys are rewritten.
    """
    if not all_func:
        return all_func

    old_names = list(all_func.keys())
    name_matcher = _build_name_matcher(old_names)
    mapping = _build_index_mapping(old_names, virtual_base)

    # The mapping must be a bijection or references would alias.
    if len(set(mapping.values())) != len(mapping):
        raise RuntimeError("Name normalization produced a collision; aborting to avoid aliasing.")

    result = _apply_mapping(all_func, mapping, name_matcher)

    # Write the mapping only after all in-memory rewrites have succeeded, so a
    # CSV on disk always corresponds to a completed normalization pass.
    if mapping_csv:
        write_name_mapping_csv(mapping, mapping_csv)

    if verbosity:
        print(f"Normalized {len(mapping)} function names (index).")
    if mapping_csv:
        print(f"Function name mapping written to: {mapping_csv}")

    return result
