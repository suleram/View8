import argparse
import os
from Parser.parse_v8cache import parse_v8cache_file, parse_disassembled_file
from Simplify.global_scope_replace import replace_global_scope


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
    replace_global_scope(all_functions)


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

def export_to_file(out_name, all_functions, format_list):
    print(f"Exporting to file {out_name}.")
    with open(out_name, "w") as f:
        for function_name in list(all_functions)[::-1]:
            f.write(all_functions[function_name].export(export_v8code="v8_opcode" in format_list, export_translated="translated" in format_list, export_decompiled="decompiled" in format_list))
            

def main():
    parser = argparse.ArgumentParser(description="View8: V8 cache decompiler.")
    parser.add_argument('input_file', help="The input file name.")
    parser.add_argument('output_file', help="The output file name.")
    parser.add_argument('--path', '-p', help="Path to disassembler binary.", default=None)
    parser.add_argument('--disassembled', '-d', action='store_true', help="Indicate if the input file is already disassembled.")
    parser.add_argument('--export_format', '-e', nargs='+', choices=['v8_opcode', 'translated', 'decompiled'], 
                        help="Specify the export format(s). Options are 'v8_opcode', 'translated', and 'decompiled'. Multiple options can be combined.", 
                        default=['decompiled'])
    parser.add_argument('--include', '-i', nargs='+', help="Functions tree to Include.", default=[])
    parser.add_argument('--exclude', '-x', nargs='+', help="Functions tree to Exclude.", default=[])

    args = parser.parse_args()
    
    if not os.path.isfile(args.input_file):
        raise FileNotFoundError(f"The input file {args.input_file} does not exist.")

    all_func = disassemble(args.input_file, args.disassembled, args.path)
    
    if args.exclude:
        remove_exclude_functions(all_func, args.exclude) #["func_unknown_0x1445baf27101", "func_unknown_0x95277699f59"])
    
    decompile(all_func)
    
    if args.include:
        all_func = get_included_functions(all_func, args.include)
        
    export_to_file(args.output_file, all_func, args.export_format)
    print(f"Done.")


if __name__ == "__main__":
    main()
