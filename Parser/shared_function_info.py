from Translate.translate import translate_bytecode
from Simplify.simplify import simplify_translated_bytecode
import re
import pickle
from typing import List, Optional

class CodeLine:
    def __init__(self, opcode="", line="", inst="", translated="", decompiled=""):
        self.v8_opcode = opcode
        self.line_num = line
        self.v8_instruction = inst
        self.translated = translated
        self.decompiled = decompiled
        self.visible = True


class SharedFunctionInfo:
    def __init__(self):
        self.name = None
        self.declarer = None
        self.function_header = None
        self.argument_count = None
        self.register_count = None
        self.code = None
        self.const_pool = None
        self.exception_table = None

    def is_fully_parsed(self):
        return all(
            value is not None for value in [
                self.argument_count, self.register_count,
                self.const_pool, self.exception_table, self.code
            ]
        )

    def create_function_header(self):
        return f"function {self.name}({', '.join([f'a{i}' for i in range(int(self.argument_count) - 1)])})"

    def translate_bytecode(self):
        translate_bytecode(self.name, self.code, self.exception_table)

    def simplify_bytecode(self):
        simplify_translated_bytecode(self, self.code)

    def replace_const_pool(self):
    
        def replacement(match):
            index = int(match.group(2))
            value = self.const_pool[index]
            if match.group(1) == "ConstPool": #Not ConstPoolLiteral
                return value.strip('"')
            return value
    
        # Regular expression to match patterns A[NUMBER] or B[NUMBER]
        pattern = r'(ConstPoolLiteral|ConstPool)\[(\d+)\]'

        #replacements = {f"ConstPool[{idx}]": var.strip('"') for idx, var in enumerate(self.const_pool)}
        #replacements.update({f"ConstPoolLiteral[{idx}]": var for idx, var in enumerate(self.const_pool)})
        
        for line in self.code:
            if "ConstPool" not in line.decompiled:
                continue
            
            line.decompiled = re.sub(pattern, replacement, line.decompiled)

    def decompile(self):
        self.translate_bytecode()
        self.simplify_bytecode()
        self.replace_const_pool()

    def export(self, export_v8code=False, export_translated=False, export_decompiled=True):
        export_func = self.create_function_header() + '\n'
        for line in self.code:
            if (not line.visible or not line.decompiled) and not export_v8code and not export_translated:
                continue

            export_line = ""
            if export_v8code:
                export_line += f'{line.line_num:<6}'
                export_line += f'{line.v8_instruction:<50}'
            if export_translated:
                export_line += f'{line.translated:<60}'
            if export_decompiled:
                export_line += f'{line.decompiled}' * line.visible
            if export_line:
                export_func += export_line + '\n'
        return export_func

####

# Helper function for serializing multiple functions
def serialize_functions(functions: List[SharedFunctionInfo]) -> bytes:
    """Serialize a list of SharedFunctionInfo objects"""
    return pickle.dumps(functions, protocol=pickle.HIGHEST_PROTOCOL)


def deserialize_functions(data: bytes) -> List[SharedFunctionInfo]:
    """Deserialize a list of SharedFunctionInfo objects"""
    return pickle.loads(data)


def save_functions_to_file(functions: List[SharedFunctionInfo], filename: str):
    """Save multiple functions to a file"""
    with open(filename, 'wb') as f:
        f.write(serialize_functions(functions))


def load_functions_from_file(filename: str) -> List[SharedFunctionInfo]:
    """Load multiple functions from a file"""
    with open(filename, 'rb') as f:
        return deserialize_functions(f.read())
