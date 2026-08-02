#!/usr/bin/env python3
import os
import re

from view8_util import next_visible_line, create_dirs, export_to_file, get_declared_children, get_included_functions


FUNC_REF_RE = re.compile(r'\b(func_[A-Za-z0-9_$]+)\b')
FUNC_CALL_RE = re.compile(r'\b(func_[A-Za-z0-9_$]+)\s*\(')


def get_used_functions(functions, curr_func, calls_only=True):
    """
    Return functions directly used by curr_func.

    In calls-only mode, collect visible textual invocations.
    In reference mode, collect all visible textual references.
    """
    func = functions.get(curr_func)
    if func is None or not func.visible:
        return set()

    regex = FUNC_CALL_RE if calls_only else FUNC_REF_RE
    used = set()

    indx = -1
    while True:
        indx = next_visible_line(func, indx)
        if indx is None:
            break

        line = func.code[indx].decompiled
        for name in regex.findall(line):
            if name == curr_func:
                continue
            if name not in functions:
                continue
            if not functions[name].visible:
                continue
            used.add(name)

    return used


def build_usage_map(functions, calls_only=True):
    """
    Build adjacency map:

        function_name -> set(directly_used_function_names)

    calls_only=True:
        follow only apparent direct calls, e.g. func_x(...)

    calls_only=False:
        follow all visible textual references, including callbacks,
        exports, route handlers, etc.
    """
    usage_map = {}

    for func_name, func in functions.items():
        if not func.visible:
            continue

        usage_map[func_name] = get_used_functions(
            functions,
            func_name,
            calls_only=calls_only
        )

    return usage_map

def collect_reachable_functions(
    usage_map,
    start_func,
    max_depth=None,
    initial_depth=0,
    blocked=None
):
    """
    Collect nodes reachable from start_func.

    blocked:
        Nodes that must not be entered. This prevents a branch from
        looping back through the selected split root and absorbing
        sibling branches.
    """
    blocked = set() if blocked is None else set(blocked)
    visited = set()
    stack = [(start_func, initial_depth)]

    while stack:
        curr_func, depth = stack.pop()

        if curr_func in blocked or curr_func in visited:
            continue

        if max_depth is not None and depth > max_depth:
            continue

        visited.add(curr_func)

        if max_depth is not None and depth == max_depth:
            continue

        for child in usage_map.get(curr_func, set()):
            stack.append((child, depth + 1))

    return visited


def split_usage_trees(functions, curr_func, calls_only=True, max_depth=None, usage_map=None):
    if curr_func not in functions:
        return None

    if usage_map is None:
        usage_map = build_usage_map(functions, calls_only=calls_only)

    children = sorted(usage_map.get(curr_func, set()))
    items_map = {}

    for child in children:
        reachable = collect_reachable_functions(
            usage_map,
            child,
            max_depth=max_depth,
            initial_depth=1,
            blocked={curr_func}
        )

        items_map[child] = {
            name: functions[name]
            for name in reachable
            if name in functions
        }

    return dict(sorted(items_map.items(), key=lambda item: len(item[1])))


def split_trees(functions, curr_func):
    sfi = functions.get(curr_func)
    if sfi is None:
        return None
    print("Tree root: " + sfi.name)
    if sfi.declarer is None:
        print("Declarer Root")
    else:
        print("Parent: " + sfi.declarer)
    children = get_declared_children(functions, curr_func)
    my_map = dict()
    for c in children:
        family = get_included_functions(functions, [c])
        my_map[c] = family
    sorted_map = dict(sorted(my_map.items(), key=lambda item: len(item[1])))
    return sorted_map


###

def save_trees(
    all_functions,
    main_func,
    inline_branch_limit,
    items_map,
    out_dir,
    export_format,
    excluded_list,
    usage_map=None,
    inline_depth=0,
    include_branch_roots=True,
):
    def _as_name_set(func_collection):
        if not func_collection:
            return set()
        if isinstance(func_collection, dict):
            return set(func_collection.keys())
        return set(func_collection)

    def _collect_reachable_by_depth(start_func, max_depth):
        if usage_map is None:
            return {start_func}

        if max_depth is None:
            max_depth = 0

        if max_depth < 0:
            return set()

        visited = set()
        stack = [(start_func, 0)]

        while stack:
            curr_func, depth = stack.pop()

            if curr_func in visited:
                continue

            if curr_func not in all_functions:
                continue

            visited.add(curr_func)

            if depth >= max_depth:
                continue

            for child in usage_map.get(curr_func, set()):
                if child not in visited:
                    stack.append((child, depth + 1))

        return visited

    main_set = set()

    # In calls/references mode this includes graph-depth context.
    # In declarer mode usage_map is None, so this becomes only {main_func}.
    main_set.update(_collect_reachable_by_depth(main_func, inline_depth))

    for branch_root, branch_funcs in items_map.items():
        branch_names = _as_name_set(branch_funcs)

        # In usage modes, branch roots should be visible only when inline_depth >= 1.
        if include_branch_roots:
            main_set.add(branch_root)

            # Inline small complete branches only when child branches are allowed
            # to appear in the main file at all.
            if len(branch_names) <= inline_branch_limit:
                main_set.update(branch_names)

    create_dirs(out_dir)

    main_file_name = f"{main_func}.txt"
    main_out_path = os.path.join(out_dir, main_file_name)

    export_to_file(
        main_out_path,
        all_functions,
        export_format,
        main_set,
        excluded_list
    )

    for branch_root, branch_funcs in items_map.items():
        branch_names = _as_name_set(branch_funcs)

        if len(branch_names) <= inline_branch_limit:
            continue

        print(f"Name: {branch_root}, List Length: {len(branch_names)}")

        subdir = f"{len(branch_names)}"
        branch_dir = os.path.join(out_dir, subdir)
        create_dirs(branch_dir)

        branch_file_name = f"{branch_root}.txt"
        branch_out_path = os.path.join(branch_dir, branch_file_name)

        export_to_file(
            branch_out_path,
            all_functions,
            export_format,
            branch_names,
            excluded_list
        )