import re
from collections import defaultdict


def replace_global_scope(all_functions, verbosity):
    scope_assignments = {}
    scope_counts = defaultdict(int)
    
    # Regex pattern to match Scope[num][num] = value
    pattern = re.compile(r'Scope\[(\d+)\]\[(\d+)\] = (\S+)')

    # First pass: Find all unique Scope assignments
    for func in all_functions.values():
        for line_obj in func.code:
            line = line_obj.decompiled
            match = pattern.search(line)
            if match:
                if verbosity > 0:
                    print(f"Matched: {line}")
                key = (match.group(1), match.group(2))
                value = match.group(3)
                if value in ("null", "undefined"):
                    line_obj.decompiled = ""
                    continue
                if key in scope_assignments or not value.startswith("func_"):
                    # If the same Scope is assigned different values, mark it as invalid
                    scope_assignments[key] = None
                else:
                    scope_assignments[key] = value
                scope_counts[key] += 1

    pattern = re.compile(r'Scope\[(\d+)\]\[(\d+)\]')
    # Second pass: Replace Scope[num][num] with value if it's set only once
    for func in all_functions.values():
        for line_obj in func.code:
            line = line_obj.decompiled
            match = pattern.search(line)
            if match:
                key = (match.group(1), match.group(2))
                if scope_counts[key] == 1 and scope_assignments[key] is not None:
                    new_line = line.replace(match.group(0), scope_assignments[key])
                    line_obj.decompiled = new_line
                    if verbosity > 0:
                        print(f"Replaced:\n\t{line}\n\t{new_line}")
                    
