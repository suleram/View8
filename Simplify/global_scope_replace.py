import re
from collections import defaultdict
from typing import Optional

def find_assignment_op(line: str) -> Optional[int]:
    """
    Return the index of the first assignment '=' in `line` that is not part of
    ==, ===, !=, <=, >=, =>. Ignores '=' inside single or double quoted strings.
    Note: backtick/template strings are not tracked (they don't appear in
    decompiled bytecode output).
    """
    in_sq = False   # inside single-quoted string
    in_dq = False   # inside double-quoted string
    esc = False

    for i, ch in enumerate(line):
        if esc:
            esc = False
            continue
        if ch == '\\' and (in_sq or in_dq):
            esc = True
            continue
        if ch == "'" and not in_dq:
            in_sq = not in_sq
            continue
        if ch == '"' and not in_sq:
            in_dq = not in_dq
            continue
        if in_sq or in_dq:
            continue
        if ch == '=':
            prev = line[i - 1] if i > 0 else ''
            nxt  = line[i + 1] if i + 1 < len(line) else ''
            if nxt in ('=', '>'):        # == / === / =>
                continue
            if prev in ('!', '<', '>', '='):  # != / <= / >= / == / ===
                continue
            return i
    return None

###

def _print_assignments(scope_assignments):
    for key in scope_assignments.keys():
        if scope_assignments[key] is None:
             continue
        (x,y) = key
        print(f"Scope[{x}][{y}] = {scope_assignments[key]}")

def _replace_global_scope2_func(all_functions, verbosity) -> int:
    """
    Collect 2 dimensional Scope definitions, i.e. `Scope[x][y] = value`
    Replace their occurrences in the code with the literal value.
    Only the Scope values that are assigned once are used for the replacements.
    """

    def _replace_value(match):
        key = (match.group(1), match.group(2))
        cnt = scope_counts.get(key, 0)
        val = scope_assignments.get(key)
        if cnt == 1 and val is not None:
            return val
        return match.group(0)

    scope_assignments = {}
    scope_counts = defaultdict(int)
    
    # Regex pattern to match Scope[num][num] = value
    pattern = re.compile(r'Scope\[(\d+)\]\[(\d+)\] = (\S+)$')
    value_pattern = re.compile(r'([\w#$]+|\"[\w#$]+\")$')
    exclusion_pattern = re.compile(r'(ACCU|r\d+|a\d+)$')

    # First pass: Find all unique Scope assignments
    for func in all_functions.values():
        for line_obj in func.code:
            line = line_obj.decompiled.strip()
            match = pattern.match(line)
            if match:
                key = (match.group(1), match.group(2))
                value = match.group(3)
                if value in ("null", "undefined"):
                    line_obj.visible = False
                    continue
                
                if key in scope_assignments.keys() or not value_pattern.match(value) or exclusion_pattern.match(value):
                    # If the same Scope is assigned different values, mark it as invalid
                    scope_assignments[key] = None
                else:
                    scope_assignments[key] = value
                scope_counts[key] += 1
    if verbosity > 1:
        _print_assignments(scope_assignments)

    pattern2 = re.compile(r'Scope\[(\d+)\]\[(\d+)\](?![\[])')  #  Scope[num][num] but not: Scope[num][num][num]
    replaced_count = 0
    # Second pass: Replace Scope[num][num] with value if it's set only once
    for func in all_functions.values():
        for line_obj in func.code:
            line = line_obj.decompiled

            # Split into left-hand and right-hand side of assignment
            idx = find_assignment_op(line)
            if idx is not None:
                lhs = line[:idx]
                rhs = line[idx + 1:]

                # Only replace Scope[x][y] if it appears **not** in LHS
                new_rhs = pattern2.sub(_replace_value, rhs)
                new_line = lhs + '=' + new_rhs
            else:
                # No assignment; apply replacements freely
                new_line = pattern2.sub(_replace_value, line)

            if new_line != line:
                replaced_count += 1
                if verbosity > 0:
                    print(f"[G] Replaced:\n\t{line}\n\t{new_line}")
            line_obj.decompiled = new_line
    return replaced_count

def replace_global_scope(all_functions, verbosity) -> int:
    total_repl = 0
    while True:
        repl_cnt = _replace_global_scope2_func(all_functions, verbosity)
        if not repl_cnt:
            break
        total_repl += repl_cnt
        if verbosity:
            print(f"[G] Replaced count: {repl_cnt}")
    return total_repl
