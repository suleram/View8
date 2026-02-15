#!/usr/bin/env python3
import argparse
import os

from view8_util import export_to_file
from Parser.parse_v8cache import parse_v8cache_file, parse_disassembled_file
from Simplify.global_scope_replace import *

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

def decompile(all_functions, verbosity):
    # Decompile
    print(f"Decompiling {len(all_functions)} functions.")
    for name in list(all_functions)[::-1]:
        all_functions[name].decompile()
    replace_global_scope(all_functions, verbosity)

###

def main():
    parser = argparse.ArgumentParser(description="View8: V8 cache decompiler.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--input_format', '-f', choices=['raw', 'serialized', 'disassembled'],
                        help="Specify the input format. Options are: 'raw', 'serialized', 'disassembled'(mutually exclusive)",
                        default='raw')
    parser.add_argument('--inp', '-i', help="The input file name.", default=None, required=True)
    parser.add_argument('--out', '-o', help="The output file name.", default=None)
    parser.add_argument('--path', '-p', help="Path to disassembler binary.", default=None)
    parser.add_argument('--export_format', '-e', nargs='+', choices=['v8_opcode', 'translated', 'decompiled', 'serialized'], 
                        help="Specify the export format(s). Options are 'v8_opcode', 'translated', and 'decompiled'. Multiple options can be combined.", 
                        default=['decompiled'])
    parser.add_argument('--tree', '-t', help="Show functions tree, starting from a given node. To start from the default main function, use 'start'", default=None)
    parser.add_argument('--mainlimit', '-l', help="In tree mode: a tree with depth above this limit will be treated as different module than main", type=int, default=1)
    parser.add_argument('--include', '-n', nargs='+', help="Functions tree to Include.", default=[])
    parser.add_argument('--exclude', '-x', nargs='+', help="Functions tree to Exclude.", default=[])
    parser.add_argument('--verbosity', '-v', help="Verbosity level (0-3)", default=0, type=int, required=False)
    args = parser.parse_args()
    
    if not os.path.isfile(args.inp):
        raise FileNotFoundError(f"The input file {args.inp} does not exist.")

    if ('serialized' in args.input_format):
        print(f"Reading from serialized, already decompiled input: {args.inp}")
        all_func = load_functions_from_file(args.inp)
    else:
        disassembled = False
        if 'disassembled' in args.input_format:
            disassembled = True
        all_func = disassemble(args.inp, disassembled, args.path)
        decompile(all_func, args.verbosity)

    if args.tree:
        tree_root = args.tree
        if tree_root == "start":
            tree_root = get_start_function(all_func)
        items_map = split_trees(all_func, tree_root)
        if args.out:
            save_trees(all_func, tree_root, args.mainlimit, items_map, args.out, args.export_format)
            print(f"Done.")
            return

    if args.out: 
        export_to_file(args.out, all_func, args.export_format, args.include, args.exclude)
    print(f"Done.")


if __name__ == "__main__":
    main()
