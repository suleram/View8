import re
from collections import defaultdict


def replace_global_scope(all_functions):
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
                key = (match.group(1), match.group(2))
                value = match.group(3)
                if value in ("null", "undefined"):
                    continue
                if key in scope_assignments or not value.startswith("func_"):
                    # If the same Scope is assigned different values, mark it as invalid
                    scope_assignments[key] = None
                else:
                    scope_assignments[key] = value
                scope_counts[key] += 1

    # Second pass: Replace Scope[num][num] with value if it's set only once
    for func in all_functions.values():
        for line_obj in func.code:
            new_line = line_obj.decompiled
            for key, count in scope_counts.items():
                if count == 1 and scope_assignments[key] is not None:
                    scope_pattern = re.escape(f'Scope[{key[0]}][{key[1]}]')
                    new_line = re.sub(scope_pattern, scope_assignments[key], new_line)
            line_obj.decompiled = new_line



