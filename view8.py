#!/usr/bin/env python3
import argparse
import os

from view8_util import (
    export_to_file,
    find_functions_by_name,
    get_start_function,
    print_funcs,
    save_trees,
    split_trees,
)
from Parser.parse_v8cache import parse_v8cache_file, parse_disassembled_file
from Parser.shared_function_info import load_functions_from_file
from Simplify.global_scope_replace import replace_global_scope
####

def disassemble(in_file, input_is_disassembled, disassembler):
    out_name = 'disasm.tmp'
    view8_dir = os.path.dirname(os.path.abspath(__file__))
    
    if input_is_disassembled:
        out_name = in_file
    else:
        # Disassemble the file
        parse_v8cache_file(in_file, out_name, view8_dir, disassembler)
    
    return parse_disassembled_file(out_name)

def decompile(all_functions):
    # Decompile
    print(f"Decompiling {len(all_functions)} functions.")
    for name in list(all_functions)[::-1]:
        all_functions[name].decompile()

def propagate_global_scope(all_func, verbosity):
    if replace_global_scope(all_func, verbosity):
        if verbosity:
            print("Replace global scope done.")
        return True
    return False

###

def load_functions_set(filename):
    try:
        with open(filename, "r") as file:
            deobf_funcs = set(line.strip() for line in file)
            return deobf_funcs
    except FileNotFoundError:
        return None
    return None

def main():
    parser = argparse.ArgumentParser(description="View8: V8 cache decompiler.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--input_format', '-f', choices=['raw', 'serialized', 'disassembled'],
        help="Specify the input format. Options are: 'raw', 'serialized' (pickle; trusted input only), 'disassembled' (mutually exclusive)", default='raw')
    parser.add_argument('--inp', '-i', help="The input file name.", default=None, required=True)
    parser.add_argument('--out', '-o', help="The output file name.", default=None)
    parser.add_argument('--path', '-p', help="Path to disassembler binary. Required if the input is in the raw format.", default=None)
    parser.add_argument('--export_format', '-e', nargs='+', choices=['v8_opcode', 'translated', 'decompiled', 'serialized'], 
                        help="Specify the export format(s). Options are 'v8_opcode', 'translated', 'decompiled', and 'serialized'. Multiple options can be combined.", 
                        default=['decompiled'])
    parser.add_argument('--scope', help="Propagate scope arguments.", default=1, type=int, required=False)
    parser.add_argument('--tree', '-t', help="Show functions tree, starting from a given node. To start from the default main function, use 'start'", default=None)
    parser.add_argument('--mainlimit', '-l', help="In tree mode: a tree with depth above this limit will be treated as different module than main", type=int, default=1)
    parser.add_argument('--include', '-n', help="Functions to Include (file containing a list)", default=None)
    parser.add_argument('--exclude', '-x', help="Functions to Exclude (file containing a list)", default=None)
    parser.add_argument('--func', help="A function to be displayed.", default=None, required=False)
    parser.add_argument('--show_all', help="Should show lines marked as hidden (in function display mode)", default=False, required=False, action='store_true')
    parser.add_argument('--verbosity', '-v', help="Verbosity level (0-3)", default=0, type=int, required=False)
    args = parser.parse_args()
    
    if not os.path.isfile(args.inp):
        raise FileNotFoundError(f"The input file {args.inp} does not exist.")

    funcs_to_include = None
    if args.include:
        funcs_to_include = load_functions_set(args.include)
    if funcs_to_include:
        print(f"Include: {len(funcs_to_include)} functions")

    funcs_to_exclude = None
    if args.exclude:
        funcs_to_exclude = load_functions_set(args.exclude)
    if funcs_to_exclude:
        print(f"Exclude: {len(funcs_to_exclude)} functions")

    if args.input_format == 'serialized':
        print(f"Reading from serialized, already decompiled input: {args.inp}")
        all_func = load_functions_from_file(args.inp)
    else:
        disassembled = False
        if args.input_format == 'disassembled':
            disassembled = True
        all_func = disassemble(args.inp, disassembled, args.path)
        decompile(all_func)

    if args.scope:
        print("Propagating scope arguments...")
        propagate_global_scope(all_func, args.verbosity)

    # print a single selected function:
    if args.func:
        func_name = args.func
        filtered = find_functions_by_name(all_func, func_name)
        if not func_name in filtered:
            print(f"Function {func_name} was not found. Found {len(filtered)} similar names.")
            for key in filtered.keys():
                print(key)
        if len(filtered) == 0:
            return
        print_funcs(filtered, args.show_all)
        return

    if args.tree:
        tree_root = args.tree
        if tree_root == "start":
            tree_root = get_start_function(all_func)
        items_map = split_trees(all_func, tree_root)
        if args.out:
            save_trees(all_func, tree_root, args.mainlimit, items_map, args.out, args.export_format, funcs_to_exclude)
            print(f"Done.")
            return

    if args.out:
        export_to_file(args.out, all_func, args.export_format, funcs_to_include, funcs_to_exclude)
    print(f"Done.")


if __name__ == "__main__":
    main()
