import re
from collections import defaultdict

def _print_assignments(scope_assignments):
    for key in scope_assignments.keys():
        if scope_assignments[key] is None:
             continue
        (x,y) = key
        print(f"Scope[{x}][{y}] = {scope_assignments[key]}")

def _replace_global_scope2_func(all_functions, verbosity) -> int:
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
            if '=' in line:
                lhs, rhs = line.split('=', 1)

                # Only replace Scope[x][y] if it appears **not** in LHS
                def replace_usage(match):
                    key = (match.group(1), match.group(2))
                    if scope_counts[key] == 1 and scope_assignments[key] is not None:
                        return scope_assignments[key]
                    return match.group(0)
                new_rhs = pattern2.sub(replace_usage, rhs)
                new_line = lhs + '=' + new_rhs
            else:
                # No assignment; apply replacements freely
                new_line = pattern2.sub(lambda m: (
                    scope_assignments[(m.group(1), m.group(2))]
                    if scope_counts[(m.group(1), m.group(2))] == 1 and scope_assignments[(m.group(1), m.group(2))] is not None
                    else m.group(0)
                ), line)

            if new_line != line:
                replaced_count += 1
                if verbosity > 0:
                    print(f"[G] Replaced:\n\t{line}\n\t{new_line}")
            line_obj.decompiled = new_line
    return replaced_count

def replace_global_scope(all_functions, verbosity) -> int:
    total_repl = 0
    round = 0
    while True:
        repl_cnt = _replace_global_scope2_func(all_functions, verbosity)
        if not repl_cnt:
            break
        total_repl += repl_cnt
        if verbosity:
            print(f"[G] Replaced count: {repl_cnt}")
    return total_repl
