import re
from Simplify.function_context_stack import function_context_stack


def get_block_type(idx, lines):
    # Determine the type of code block based on the content of the first line.
    if idx == 0:
        return "function"

    first_block_line = lines[idx-1].decompiled

    block_types = {
        "try": "try",
        "catch": "catch",
        "while": "loop",
        "switch": "case",
        "case": "case",
        "if": "if",
        "else": "else"
    }

    for keyword, block_type in block_types.items():
        if keyword in first_block_line:
            return block_type

    return "unknown"


def reg_is_constant(reg, value):
    # Variable is ACCU
    if reg.startswith(("ACCU", "CASE_")):
        return True

    # Variable is set to a function result
    if re.search(r"[\w\]]\(", value):
        return False

    # Variable is set to a constant value
    if re.search(r"^[\(]*(Scope|ConstPool|<|true|false|Undefined|Null|null|[+-]?\d)", value):
        return True

    # Variable is set to register[ConstPool[idx]]
    if re.search(r"^[ra]\d+\[[\(]*ConstPool\[\d+\]", value):
        return True

    return False


def get_context_idx_from_var(var):
    if var.was_overwritten:
        return
    pattern = r"Scope\[(\d+)\]"
    match = re.match(pattern, var.value)
    if match:
        return int(match.group(1))
    return None


def is_reg_defined_in_reg_value(reg, value):
    reg_len = len(reg)
    idx = value.find(reg)
    while idx != -1:
        if idx + reg_len == len(value) or not value[idx+reg_len].isdigit():
            return True
        idx = value.find(reg, idx + 1)


def create_loop_reg_scope(prev_reg_scope):
    # Because loop regs can be overwritten during loop iteration we define prev scope as overwritten
    reg_scope = {k: Register("", v.all_initialized_index[0], True) for k, v in prev_reg_scope.items() if
                 not isinstance(v, int)}
    reg_scope["current_context"] = prev_reg_scope["current_context"]
    return reg_scope


def close_loop_reg_scope(prev_reg_scope, reg_scope):
    # Because we defined all reg scope as overwritten (with no value) we need to make sure if it was really
    # overwritten and change prev reg scope
    for k, v in reg_scope.items():
        if isinstance(v, int):
            continue
        if v.was_overwritten and len(v.all_initialized_index) > 1 and k in prev_reg_scope and not prev_reg_scope[k].was_overwritten:
            prev_reg_scope[k].was_overwritten = True
            prev_reg_scope[k].all_initialized_index += reg_scope[k].all_initialized_index[1:]


class Register:
    def __init__(self, value, init_index, was_overwritten=False):
        self.value = value
        self.was_overwritten = was_overwritten
        self.all_initialized_index = [init_index]


class SimplifyCode:
    def __init__(self, code, sfi):
        self.code = code
        self.line_index = 0
        self.tab_level = 0
        self.sfi = sfi

    def get_next_line(self):
        self.line_index += 1
        if self.line_index >= len(self.code):
            print("Error decompiling {self.sfi.name}, no more lines.")
        line_obj = self.code[self.line_index]
        return line_obj.translated

    def add_simplified_line(self, line):
        self.code[self.line_index].decompiled = '\t' * self.tab_level + line if line else ""

    def change_context(self, line, reg_scope):
        # Change current_context index
        if "PushContext" in line:
            reg_scope["current_context"] = function_context_stack.add_new_context(reg_scope["current_context"])
            return f"ACCU = Scope[CURRENT-1]"
        # "PopContext" in line
        reg_scope["current_context"] = function_context_stack.get_context(reg_scope["current_context"], 1)
        return f"ACCU = Scope[CURRENT]"

    def add_current_context_to_sub_function(self, line, reg_scope):
        # Inherit the current context to sub-function
        match = re.search(r"ConstPool\[(\d+)\]", line)
        if match:
            const_pool_index = int(match.group(1))
            if len(self.sfi.const_pool) > const_pool_index:
                name = self.sfi.const_pool[const_pool_index]
                function_context_stack.add_function_context(name, reg_scope['current_context'])
            else:
                print("Error: ConstPool idx", const_pool_index, "out of range.", len(self.sfi.const_pool))
        else:
            print("Error: ConstPool index not found in line:", line)
        return line.replace(" new func ", " ")

    def handle_context_diff(self, block_type, reg_scope, prev_reg_scope):
        block_last_line = self.code[self.line_index-1].decompiled.strip()
        if block_type == "else" and not block_last_line.startswith(("return", "break", "continue")):
            prev_reg_scope["current_context"] = reg_scope.get("current_context")

    def replace_scope_stack_with_idx(self, line, reg_scope, prev_reg_scope):
        def replace_scope(match):
            scope = match.group(1)

            # If the scope is "CURRENT", replace it with the current context
            if scope == "CURRENT":
                return f"Scope[{reg_scope['current_context']}]"

            # Handles cases like CURRENT-1, r1-2

            scope_start, steps = scope.split("-")
            start_context = reg_scope['current_context']

            if scope_start in reg_scope:
                start_context = get_context_idx_from_var(reg_scope[scope_start])

            elif scope_start in prev_reg_scope:
                start_context = get_context_idx_from_var(prev_reg_scope[scope_start])

            return f"Scope[{function_context_stack.get_context(start_context, int(steps))}]"

        return re.sub(r"Scope\[([^\]]+)\]", replace_scope, line)

    def replace_reg_with_constant(self, line, reg_scope):
        def replace_reg(match):
            reg = match.group(1)
            if reg not in reg_scope:
                return reg

            # If the reg is in reg_scope and was not overwritten, return its value and mark the
            # first initialized_index line invisible
            if not reg_scope[reg].was_overwritten:
                self.code[reg_scope[reg].all_initialized_index[0]].visible = False
                return reg_scope[reg].value

            # If the reg was overwritten and now used again, ensure all all_initialized_index are set to visible
            for idx in reg_scope[reg].all_initialized_index:
                self.code[idx].visible = True
            return reg

        return re.sub(r"(ACCU|CASE_\d+|[ra]\d+)", replace_reg, line)

    def add_reg_to_reg_scope(self, reg, value, reg_scope, prev_reg_scope, overwritten_regs):
        if reg in reg_scope:
            del reg_scope[reg]

        # if the reg was used in prev_reg_scope mark it as was_overwritten and save the current idx to overwritten_regs
        if reg in prev_reg_scope:
            prev_reg_scope[reg].was_overwritten = True
            overwritten_regs[reg] = self.line_index

        # Check if a local reg value is now overwritten in any local variables
        for k, v in reg_scope.items():
            if type(v) == int:
                continue
            if is_reg_defined_in_reg_value(reg, v.value):
                reg_scope[k].was_overwritten = True

        # Add the reg to reg_scope dictionary
        if reg_is_constant(reg, value):
            reg_scope[reg] = Register(value, self.line_index)

    def simplify_line(self, line, reg_scope, prev_reg_scope, overwritten_regs):
        # Handle context change
        if "PopContext" in line or "PushContext" in line:
            line = self.change_context(line, reg_scope)
        if "new func" in line:
            line = self.add_current_context_to_sub_function(line, reg_scope)

        # Fix the context var with context stack index
        line = self.replace_scope_stack_with_idx(line, reg_scope, prev_reg_scope)

        # replace constant regs
        if not re.search(r"^(ACCU|CASE_\d+|[ra]\d+) = ", line):
            return self.replace_reg_with_constant(line, reg_scope)

        reg, value = line.split(" = ", 1)
        value = self.replace_reg_with_constant(value, reg_scope)

        # Add the new reg to the reg scope dictionary
        self.add_reg_to_reg_scope(reg, value, reg_scope, prev_reg_scope, overwritten_regs)
        return f"{reg} = {value}"

    def simplify_block(self, prev_reg_scope):
        block_type = get_block_type(self.line_index, self.code)

        reg_scope = prev_reg_scope.copy() if block_type != "loop" else create_loop_reg_scope(prev_reg_scope)
        overwritten_regs = {}

        self.add_simplified_line("{")
        self.tab_level += 1

        while (line := self.get_next_line()) != "}":
            if line == "{":
                self.simplify_block(prev_reg_scope | reg_scope)
                continue

            self.add_simplified_line(self.simplify_line(line, reg_scope, prev_reg_scope, overwritten_regs))

        self.tab_level -= 1
        self.add_simplified_line("}")

        # add the overwritten regs to all_initialized_index on prev reg dict
        if block_type == "loop":
            close_loop_reg_scope(prev_reg_scope, reg_scope)
        for k, v in overwritten_regs.items():
            prev_reg_scope[k].all_initialized_index.append(v)

        if prev_reg_scope.get("current_context") != reg_scope.get("current_context"):
            self.handle_context_diff(block_type, reg_scope, prev_reg_scope)

        return


def simplify_translated_bytecode(sfi, code):
    simplify = SimplifyCode(code, sfi)
    regs = {"current_context": function_context_stack.get_func_context(sfi.name, sfi.declarer)}
    simplify.simplify_block(regs)
    if simplify.line_index != len(code) -1:
        print(f"Warning! failed to decompile {sfi.name} stopped after {simplify.line_index}/{len(code)-1}")


