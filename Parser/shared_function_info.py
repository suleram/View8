from Translate.translate import translate_bytecode
from Translate.jump_blocks import CodeLine
from Simplify.simplify import simplify_translated_bytecode

import re
import pickle
from typing import Dict, List, Optional, Union

###

class GlobalVars:
    def __init__(self):
        self.strings_set = None
        self.funcs_map = None

    def parse(self, value):

        def _extract_name(func):
            return func[len("func_"):func.rindex("_0x")]

        is_parsed = False
        _strings_set = set(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', value))
        _funcs_set = set(re.findall(r'\bfunc_[A-Za-z0-9_$]+\b', value))
        if _strings_set:
            is_parsed = True
            if not self.strings_set:
                self.strings_set = set()
            self.strings_set.update(_strings_set)

        if _funcs_set:
            is_parsed = True
            if not self.funcs_map:
                self.funcs_map = {}
            for func in _funcs_set:
                short_name = _extract_name(func)
                self.funcs_map[short_name] = func
        return is_parsed
     
    def is_filled(self):
        if self.strings_set or self.funcs_map:
            return True
        return False

    def has_value(self, value):
        if self.strings_set is not None:
            val = value.strip('"')
            if (value in self.strings_set or val in self.strings_set):
                return True
        if self.funcs_map is not None:
            if value in self.funcs_map.keys():
                return True
        return False
    
    def resolve_global_name(self, value):

        def _is_string(value):
            if value.startswith('"') and value.endswith('"'):
                return True
            return False

        if not self.is_filled():
            return None

        if not _is_string(value):
            return None

        val = value.strip('"')
        if self.strings_set is not None:
            if (value in self.strings_set or val in self.strings_set):
                return "global_" + val

        if self.funcs_map is not None:
            if val in self.funcs_map.keys():
                return self.funcs_map[val]

        return None    

###

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
        self.visible = True
        self.metadata = None

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

    def fill_global_variables(self, global_vars: GlobalVars):
        """
        If the Global Vars were defined anywhere in this function, fill them in and store in the global structure.
        """

        patternDef = re.compile(r'ConstPoolLiteral\[(\d+)\]')

        for obj in self.code:
            line = obj.decompiled
            if "DeclareGlobals(" not in line:
                continue
            match = re.search(patternDef, line.strip())
            if not match:
                continue
            index = int(match.group(1))
            if global_vars.parse(self.const_pool[index]):
                return True
        return False

    def replace_const_pool(self, global_vars: GlobalVars):

        def replacement(match):
            index = int(match.group(2))
            if index not in self.const_pool:
                return match.group(0) #Leave unchanged
            
            value = self.const_pool[index]
            if match.group(1) == "ConstPool": #Not ConstPoolLiteral

                global_symbol = global_vars.resolve_global_name(value)
                if global_symbol:
                    return global_symbol

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

    def decompile(self, global_vars: GlobalVars):
        self.translate_bytecode()
        self.simplify_bytecode()
        self.fill_global_variables(global_vars)
        self.replace_const_pool(global_vars)

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

FunctionsBlob = Union[Dict[str, "SharedFunctionInfo"], List["SharedFunctionInfo"]]

# Helper function for serializing multiple functions
def serialize_functions(functions: FunctionsBlob) -> bytes:
    """Serialize decompiled output using pickle.

    SECURITY NOTE:
      Pickle is unsafe for untrusted input. Only load serialized files that you
      generated yourself.
    """
    return pickle.dumps(functions, protocol=pickle.HIGHEST_PROTOCOL)


def deserialize_functions(data: bytes) -> FunctionsBlob:
    """Deserialize decompiled output using pickle.

    SECURITY NOTE:
      Unpickling can execute arbitrary code. Do not load files from untrusted
      sources.
    """
    return pickle.loads(data)


def save_functions_to_file(functions: FunctionsBlob, filename: str):
    """Save decompiled output to a file (pickle)."""
    with open(filename, 'wb') as f:
        f.write(serialize_functions(functions))


def load_functions_from_file(filename: str) -> FunctionsBlob:
    """Load decompiled output from a file (pickle)."""
    with open(filename, 'rb') as f:
        return deserialize_functions(f.read())
