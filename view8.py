#!/usr/bin/env python3
import argparse
import os

from Parser.parse_v8cache import parse_v8cache_file, parse_disassembled_file
from Parser.shared_function_info import GlobalVars, load_functions_from_file
from Parser.normalize import normalize_function_names
from Simplify.global_scope_replace import replace_global_scope
from split_util import save_trees, build_usage_map, split_usage_trees, split_trees

from view8_util import (
    export_to_file,
    find_functions_by_name,
    get_start_function,
    print_funcs
)
####

_AUTO_NORMALIZE_MAP = "__AUTO_NORMALIZE_MAP__"


def resolve_normalize_map_path(requested_path, out_path, input_path,
                               output_is_directory=False):
    """Resolve --normalize-map, including its path-less automatic form."""
    if requested_path is None:
        return None
    if requested_path != _AUTO_NORMALIZE_MAP:
        return requested_path

    if out_path and output_is_directory:
        input_stem = os.path.splitext(os.path.basename(input_path))[0]
        return os.path.join(out_path, f"{input_stem}.name_map.csv")

    base_path = out_path or input_path
    root, _ = os.path.splitext(base_path)
    return f"{root}.name_map.csv"

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
    global_vars = GlobalVars()
    print(f"Decompiling {len(all_functions)} functions.")
    for name in list(all_functions)[::-1]:
        all_functions[name].decompile(global_vars)

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
            deobf_funcs = set()
            for line in file:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                deobf_funcs.add(stripped)
            return deobf_funcs
    except FileNotFoundError:
        return None
    return None

def main():
    parser = argparse.ArgumentParser(description="View8: V8 cache decompiler.")
    parser.add_argument('--input_format', '-f', choices=['raw', 'serialized', 'disassembled'],
        help="Specify the input format. Options are: 'raw', 'serialized' (pickle; trusted input only), 'disassembled'.", default='raw')
    parser.add_argument('--inp', '-i', help="The input file name.", default=None, required=True)
    parser.add_argument('--out', '-o', help="The output file name.", default=None)
    parser.add_argument('--path', '-p', help="Path to disassembler binary. Required if the input is in the raw format.", default=None)
    parser.add_argument('--export_format', '-e', nargs='+', choices=['v8_opcode', 'translated', 'decompiled', 'serialized'], 
                        help="Specify the export format(s). Options are 'v8_opcode', 'translated', 'decompiled', and 'serialized'. Multiple options can be combined.", 
                        default=['decompiled'])
    parser.add_argument('--scope', help="Propagate scope arguments.", default=1, type=int, required=False)
    parser.add_argument('--normalize', action='store_true',
                        help="Rebase address-based function names onto a deterministic static base "
                             "so the same JSC file decompiles identically across runs, while "
                             "assigning identifiers by deterministic parse order.")
    parser.add_argument('--normalize-map', '--normalize_map', dest='normalize_map',
                        nargs='?', const=_AUTO_NORMALIZE_MAP, default=None, metavar='CSV',
                        help="Write an original_name -> normalized_name CSV while normalizing. "
                             "If CSV is omitted, derive '<output>.name_map.csv' from --out, "
                             "or from --inp when --out is not set. Requires --normalize.")
    parser.add_argument('--tree', '-t', default=None,
                        help="Show functions tree, starting from a given node. To start from the default main function, use 'start'"
    )
    parser.add_argument("--inline_branch_limit", "-l", metavar="N", type=int, default=1,
                        help=(
                            "Inline complete child branches with at most N functions into the main "
                            "tree file, but only when child branches are included by --inline_depth. "
                            "Larger branches are saved separately."
                        )
    )
    parser.add_argument("--inline_depth", "-d", metavar="N", type=int, default=0,
                        help=(
                            "Include functions reachable from the selected tree root up to depth N "
                            "in the main tree file. Depth 0 means only the root; depth 1 includes "
                            "direct callees/references; depth 2 includes their children. "
                            "Only used with --split_mode calls/references."
                        )
    )
    parser.add_argument('--split_depth', type=int, default=4,
                        help=(
                            "Maximum usage-graph depth counted from the selected tree root. "
                            "Only used with --tree in calls/references split modes."
                        )
    )
    parser.add_argument('--split_mode', choices=['declarers', 'calls', 'references'], default='declarers',
                        help="A mode in which the tree will be built if function splitting was requested. Only used with --tree."
    )
    parser.add_argument('--include', '-n', help="Functions to Include (file containing a list)", default=None)
    parser.add_argument('--exclude', '-x', help="Functions to Exclude (file containing a list)", default=None)
    parser.add_argument('--func', help="A function to be displayed.", default=None, required=False)
    parser.add_argument('--show_all', help="Should show lines marked as hidden (in function display mode)", default=False, required=False, action='store_true')
    parser.add_argument('--verbosity', '-v', help="Verbosity level (0-3)", default=0, type=int, required=False)
    args = parser.parse_args()

    if args.normalize_map is not None and not args.normalize:
        parser.error("--normalize-map requires --normalize")

    normalize_map_path = resolve_normalize_map_path(
        args.normalize_map,
        args.out,
        args.inp,
        output_is_directory=bool(args.tree),
    )
    
    if args.tree:
        if args.inline_depth < 0:
            parser.error("--inline_depth must be non-negative")

        if args.inline_branch_limit < 0:
            parser.error("--inline_branch_limit must be non-negative")

        if args.split_depth < 1:
            parser.error("--split_depth must be at least 1")

        if args.split_mode == "declarers" and args.inline_depth != 0:
            parser.error("--inline_depth is only supported with --split_mode calls/references")
            
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
        if args.normalize:
            all_func = normalize_function_names(
                all_func,
                verbosity=args.verbosity,
                mapping_csv=normalize_map_path,
            )
    else:
        disassembled = False
        if args.input_format == 'disassembled':
            disassembled = True
        all_func = disassemble(args.inp, disassembled, args.path)
        if args.normalize:
            # Normalize before decompilation so every downstream artifact
            # (decompiled code, scope propagation, tree splitting) uses the
            # deterministic names.
            all_func = normalize_function_names(
                all_func,
                verbosity=args.verbosity,
                mapping_csv=normalize_map_path,
            )
        decompile(all_func)

    if args.scope:
        print("Propagating scope arguments...")
        propagate_global_scope(all_func, args.verbosity)

    # print a single selected function:
    if args.func:
        func_name = args.func
        filtered = find_functions_by_name(all_func, func_name)
        if func_name not in filtered:
            print(f"Function {func_name} was not found. Found {len(filtered)} similar names.")
            for key in filtered:
                print(key)
        if len(filtered) == 0:
            return
        _show_const=False
        if args.verbosity:
            _show_const=True
        print_funcs(filtered, args.show_all, show_line_num=False, show_const=_show_const)
        return

    usage_map = None

    if args.split_mode in ("calls", "references"):
        calls_only = args.split_mode == "calls"
        usage_map = build_usage_map(all_func, calls_only=calls_only)
        
    if args.tree:
        tree_root = args.tree
        if tree_root == "start":
            tree_root = get_start_function(all_func)
        if not tree_root:
            print("Error: tree root function not found.")
            return
        if args.split_mode == 'declarers':
            items_map = split_trees(all_func, tree_root)
        else:
            _calls_only=True
            if args.split_mode == 'references':
                _calls_only=False
            items_map = split_usage_trees(
                all_func,
                tree_root,
                _calls_only,
                max_depth=args.split_depth,
                usage_map=usage_map,
            )
        if items_map is None:
            print(f"Error: could not build tree from root '{tree_root}'.")
            return

        if args.out:
            inline_depth = args.inline_depth
            include_branch_roots = False

            if args.split_mode == "declarers":
                inline_depth = 0
                include_branch_roots = False
            else:
                inline_depth = args.inline_depth
                include_branch_roots = args.inline_depth >= 1
            
            save_trees(
                all_func,
                tree_root,
                args.inline_branch_limit,
                items_map,
                args.out,
                args.export_format,
                funcs_to_exclude,
                usage_map=usage_map,
                inline_depth=inline_depth,
                include_branch_roots=include_branch_roots,
            )
            print("Done.")
            return 

    if args.out:
        export_to_file(args.out, all_func, args.export_format, funcs_to_include, funcs_to_exclude)
    print(f"Done.")


if __name__ == "__main__":
    main()
