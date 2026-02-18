#!/usr/bin/env python3
import os
import re

from Parser.shared_function_info import SharedFunctionInfo, save_functions_to_file

def is_root(sfi):
    if sfi.declarer is None:
        return True
    return False

def get_start_function(functions):
    curr_func = next(iter(functions))
    while True:
        sfi = functions.get(curr_func)
        if is_root(sfi):
            return curr_func
        if sfi is None:
            break
        if sfi.declarer is None:
            break
        curr_func = sfi.declarer
    return None

def get_all_children(functions, curr_func):
    children_list = [ ]
    for func_name, sfi in functions.items():
        declarer = sfi.declarer
        if declarer == curr_func:
            children_list.append(func_name)
    return children_list

def next_visible_line(func, indx, is_backward=False):
    """
    Next non-empty, visible line
    Returns Index
    """
    if is_backward:
        step = (-1)
    else:
        step = 1
    indx += step
    while (indx >= 0 and indx < len(func.code)):
        if ((not func.code[indx].visible) or (not func.code[indx].decompiled) or (func.code[indx].decompiled.strip() == "")):
            indx += step
            continue
        return indx
    return None

###

def _rename_functions(
    functions: dict[str, SharedFunctionInfo],
    renamed_dict: dict[str, str],
) -> int:
    renamed_count = 0
    new_functions: dict[str, SharedFunctionInfo] = {}

    for name, func in functions.items():
        if name in renamed_dict:
            new_name = renamed_dict[name]
            func.name = new_name
            new_functions[new_name] = func
            renamed_count += 1
        else:
            new_functions[name] = func

    # mutate the original dict in place (if callers hold a reference)
    functions.clear()
    functions.update(new_functions)
    return renamed_count

def rename_functions_in_code(
    functions: dict[str, SharedFunctionInfo],
    renamed_dict: dict[str, str],
    verbosity: int
) -> int:

    renamed = _rename_functions(functions, renamed_dict)
    if verbosity:
        print(f"Renamed functions: {renamed}")

    func_pattern = r'\b(func_[a-zA-Z0-9_$]+_0x[0-9a-fA-F]+)\b'
    regex = re.compile(func_pattern)
    
    for func in functions.values():
        indx = 0
        while True:
            indx = next_visible_line(func, indx)
            if indx is None:
                break

            line = func.code[indx].decompiled

            # Replace only if the found name is in renamed_dict
            def repl(m):
                name = m.group(1)
                return renamed_dict.get(name, name)

            new_line = regex.sub(repl, line)

            if new_line != line:
                func.code[indx].decompiled = new_line
                if verbosity:
                    print(f"REPL: {line.strip()} -> {new_line.strip()}")
    return renamed

###

def print_func(func_name, func, show_hidden=False, show_line_num=True, show_const=False, show_line_meta=False):
    print("###")
    print(f"# {func_name}")
    print(f"# Declarer: {func.declarer}")
    if func.metadata:
        print(f"Metadata: {func.metadata}")
    if show_const:
        print(f"# Const Pool")
        print(func.const_pool)
    print(f"# Code")
    indx = 0
    i = 0
    for i in range(len(func.code)):
        line_obj = func.code[i]
        if not line_obj.decompiled:
            continue
        if not show_hidden and not line_obj.visible:
            continue
        indx += 1
        line = line_obj.decompiled

        meta = ""
        if show_line_meta:
            if line_obj.metadata:
                meta = f" # {line_obj.metadata}"

        if show_line_num:
            if indx != i:
                print(f"{indx}|{i}|{line}{meta}")
            else:
                print(f"{indx}|{line}{meta}")
        else:
            print(f"{line}")
#

def print_funcs(functions, show_hidden=False, show_line_num=True, show_const=False, show_line_meta=False):
    for func_name, func in functions.items():
        print_func(func_name, func, show_hidden, show_line_num, show_const, show_line_meta)

def find_functions_by_name(all_func, name):
    funcs = dict()
    if name in all_func:
        funcs[name] = all_func[name]
        return funcs
    sub_name = "_" + name + "_"
    for key in all_func.keys():
        if sub_name in key:
            funcs[key] = all_func[key]
    return funcs
###

def build_declaration_map(functions):
    declared_by = {}

    for func_name, sfi in functions.items():
        declarer = sfi.declarer
        if declarer:
            if declarer not in declared_by:
                declared_by[declarer] = []
            declared_by[declarer].append(func_name)

    return declared_by

def remove_exclude_functions(all_functions, exclude_list):
    declaration_table = build_declaration_map(all_functions)
    number_of_function = len(exclude_list)
    while exclude_list:
        current_function = exclude_list.pop()
        del all_functions[current_function]
        next_level = declaration_table.get(current_function, [])
        number_of_function += len(next_level)
        exclude_list += next_level
    print(f"Removed {number_of_function} functions")

def get_included_functions(all_functions, include_list):
    declaration_table = build_declaration_map(all_functions)
    number_of_function = len(include_list)
    new_all_func = {}
    while include_list:
        current_function = include_list.pop()
        new_all_func[current_function] = all_functions[current_function]
        next_level = declaration_table.get(current_function, [])
        number_of_functoin += len(next_level)
        include_list += next_level
    return new_all_func   
###

def _export_to_file(out_name, all_functions, format_list, included_list = None, excluded_list = None):
    with open(out_name, "w") as f:
        print(f"Exporting to file {out_name}")
        for function_name in list(all_functions)[::-1]:
            include = True
            if (excluded_list is not None and len(excluded_list)) and (function_name in excluded_list):
                include = False
            if (included_list is not None and len(included_list)) and (function_name not in included_list):
                include = False
            if not all_functions[function_name].visible:
                include = False
            if not include:
                continue
            f.write(all_functions[function_name].export(export_v8code="v8_opcode" in format_list, export_translated="translated" in format_list, export_decompiled="decompiled" in format_list))

def _get_extension(filename):
    ext = None
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[-1]
    return ext

def _add_or_replace_extension(filename, new_ext):
    if not new_ext.startswith('.'):
        new_ext = '.' + new_ext
    base = filename.rsplit('.', 1)[0] if '.' in filename else filename
    return base + new_ext

def export_to_file(out_name, all_functions, format_list, included_list = None, excluded_list = None):
    serialize_only = False
    serialized_ext = ".pkl"
    text_ext = ".txt"
    if ('serialized' in format_list):
        if len(format_list) == 1:
            serialize_only = True

        serialized_name = _add_or_replace_extension(out_name, serialized_ext)
        print(f"Serializing to file: {serialized_name}")
        save_functions_to_file(all_functions, serialized_name)

        if serialize_only:
            return
    if _get_extension(out_name) == serialized_ext:
        out_name = _add_or_replace_extension(out_name, text_ext)
    _export_to_file(out_name, all_functions, format_list, included_list, excluded_list)

###

def split_trees(functions, curr_func):
    sfi = functions.get(curr_func)
    print("Tree root: " + sfi.name)
    if sfi.declarer is None:
        print("Declarer Root")
    else:
        print("Parent: " + sfi.declarer)
    children = get_all_children(functions, curr_func)
    my_map = dict()
    for c in children:
        family = get_included_functions(functions, [c])
        my_map[c] = family
    sorted_map = dict(sorted(my_map.items(), key=lambda item: len(item[1])))
    return sorted_map

def create_dirs(nested_directory):
    is_ok = False
    try:
        os.makedirs(nested_directory)
        is_ok = True
    except FileExistsError:
        is_ok = True
    except Exception as e:
        print(f"An error occurred: {e}")
    return is_ok

def save_trees(all_functions, main_func, main_limit, items_map, out_dir, export_format, excluded_list):
    # export the root function and directly related:
    main_set = [main_func]
    for name, filtered_func in items_map.items():
        if len(filtered_func) <= main_limit:
            main_set += filtered_func
    file_name = f"{main_func}.txt"
    create_dirs(out_dir)
    out_path = os.path.join(out_dir, file_name)
    export_to_file(out_path, all_functions, export_format, main_set)

    # export the subtrees:
    for name, filtered_func in items_map.items():
        if len(filtered_func) <= main_limit:
            continue #skip
        print(f"Name: {name}, List Length: {len(filtered_func)}")
        subdir = f"{len(filtered_func)}"
        file_name = f"{name}.txt"
        dirs = os.path.join(out_dir, subdir)
        create_dirs(dirs)
        out_path = os.path.join(out_dir, subdir, file_name)
        export_to_file(out_path, all_functions, export_format, filtered_func, excluded_list)

###

