#!/usr/bin/env python3
import os

from Parser.shared_function_info import *

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
    number_of_functoin = len(exclude_list)
    while exclude_list:
        current_function = exclude_list.pop()
        del all_functions[current_function]
        next_level = declaration_table.get(current_function, [])
        number_of_functoin += len(next_level)
        exclude_list += next_level
    print(f"Removed {number_of_functoin} functions")

def get_included_functions(all_functions, include_list):
    declaration_table = build_declaration_map(all_functions)
    number_of_functoin = len(include_list)
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
        print(f"Exporting to file {out_name}.")
        for function_name in list(all_functions)[::-1]:
            include = True
            if (excluded_list is not None and len(excluded_list)) and (function_name in excluded_list):
                include = False
            if (included_list is not None and len(included_list)) and (function_name not in included_list):
                include = False
            if include:
                f.write(all_functions[function_name].export(export_v8code="v8_opcode" in format_list, export_translated="translated" in format_list, export_decompiled="decompiled" in format_list))

def export_to_file(out_name, all_functions, format_list, included_list = None, excluded_list = None):
    serialize_only = False
    if ('serialized' in format_list):
        serialized_name = out_name
        if len(format_list) == 1:
            serialize_only = True
        else:
            serialized_name += ".pkl"
        print(f"Serializing to file: {serialized_name}")
        save_functions_to_file(all_functions, serialized_name)
        if serialize_only:
            return
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

def save_trees(all_functions, main_func, main_limit, items_map, out_dir, export_format):
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
        export_to_file(out_path, all_functions, export_format, filtered_func)
