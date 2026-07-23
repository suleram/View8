import re
from collections import deque
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
    if re.search(r"^[\(]*(Scope|ConstPool|ConstPoolLiteral|<|true|false|Undefined|Null|null|[+-]?\d)", value):
        return True

    # Variable is set to register[ConstPool[idx]]
    if re.search(r"^[ra]\d+\[[\(]*(ConstPool|ConstPoolLiteral)\[\d+\]", value):
        return True

    return False


def get_context_idx_from_var(var):
    #if var.was_overwritten:
    #    return
    pattern = r"^Scope\[(\d+)\]$"
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
    reg_scope = {}
    # Because loop regs can be overwritten during loop iteration we define prev scope as overwritten
    for k,v in prev_reg_scope.items():
        if isinstance(v, int):
            continue
        if get_context_idx_from_var(v) is not None:
            reg_scope[k] = prev_reg_scope[k]
            continue
        reg_scope[k] = Register("", v.all_initialized_index[0], True)
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
        self.context_id_by_line = {}
        self.context_state_by_line = {}

    @staticmethod
    def _copy_context_state(state):
        return {
            "current": frozenset(state["current"]),
            "accu": frozenset(state["accu"]),
            "regs": {reg: frozenset(values) for reg, values in state["regs"].items()},
        }

    @staticmethod
    def _merge_context_states(old, new):
        if old is None:
            return SimplifyCode._copy_context_state(new), True

        merged_current = old["current"] | new["current"]
        merged_accu = old["accu"] | new["accu"]
        merged_regs = {}
        for reg in old["regs"].keys() | new["regs"].keys():
            values = old["regs"].get(reg, frozenset()) | new["regs"].get(reg, frozenset())
            if values:
                merged_regs[reg] = values

        merged = {
            "current": merged_current,
            "accu": merged_accu,
            "regs": merged_regs,
        }
        return merged, merged != old

    @staticmethod
    def _single_context(values):
        if values and len(values) == 1:
            return next(iter(values))
        return None

    @staticmethod
    def _jump_targets(instruction):
        return [int(value) for value in re.findall(r"@\s*(\d+)", instruction or "")]

    @staticmethod
    def _is_unconditional_jump(opcode):
        return opcode in {"Jump", "JumpConstant", "JumpLoop"}

    @staticmethod
    def _is_terminal_instruction(opcode):
        return opcode in {"Return", "Throw", "ReThrow", "Abort"}

    def _context_successors(self, actual_indexes, line_to_index, exception_table):
        position = {index: pos for pos, index in enumerate(actual_indexes)}
        successors = {index: set() for index in actual_indexes}

        for index in actual_indexes:
            line_obj = self.code[index]
            opcode, _ = self._parse_instruction(line_obj.v8_instruction)
            targets = self._jump_targets(line_obj.v8_instruction)
            # Resume targets of SwitchOnGeneratorState restore a suspended
            # register file and context.  Propagating the function-entry state
            # directly to them incorrectly merges the outer captured context
            # into the function's active context.  Analyze the initial
            # fallthrough path here; resumed paths retain the structured
            # simplifier fallback unless reconstructed from a suspension edge.
            if opcode != "SwitchOnGeneratorState":
                for target in targets:
                    target_index = line_to_index.get(target)
                    if target_index is not None:
                        successors[index].add(target_index)

            pos = position[index]
            next_index = actual_indexes[pos + 1] if pos + 1 < len(actual_indexes) else None
            if next_index is None or self._is_terminal_instruction(opcode):
                continue
            if not self._is_unconditional_jump(opcode):
                successors[index].add(next_index)

        # Exception handlers resume with the lexical context active at the
        # beginning of the protected region.  Seed the handler from that entry
        # rather than from arbitrary throwing instructions inside nested scopes.
        for handler_offset, protected in (exception_table or {}).items():
            if not protected:
                continue
            try_start = protected[0]
            source = line_to_index.get(try_start)
            handler = line_to_index.get(handler_offset)
            if source is not None and handler is not None:
                successors[source].add(handler)

        return successors

    def _transfer_context_state(self, index, state):
        state = self._copy_context_state(state)
        instruction = getattr(self.code[index], "v8_instruction", "") or ""
        opcode, args = self._parse_instruction(instruction)
        current = state["current"]
        regs = state["regs"]

        if opcode in {
            "CreateFunctionContext", "CreateBlockContext", "CreateCatchContext",
            "CreateEvalContext", "CreateWithContext"
        }:
            context_id = self.context_id_by_line[index]
            state["accu"] = frozenset({context_id})
            return state

        if opcode == "PushContext" and args:
            regs[args[0]] = current
            if state["accu"]:
                state["current"] = state["accu"]
            return state

        if opcode == "PopContext" and args:
            restored = regs.get(args[0], frozenset())
            if restored:
                state["current"] = restored
            return state

        if opcode == "Ldar" and args:
            state["accu"] = regs.get(args[0], frozenset())
            return state

        if opcode.startswith("Star"):
            if opcode == "Star" and args:
                target = args[0]
            else:
                suffix = opcode[4:]
                target = f"r{suffix}" if suffix.isdigit() else None
            if target:
                if state["accu"]:
                    regs[target] = state["accu"]
                else:
                    regs.pop(target, None)
            return state

        if opcode == "Mov" and len(args) >= 2:
            source, target = args[0], args[1]
            if source == "<context>":
                values = current
            else:
                values = regs.get(source, frozenset())
            if values:
                regs[target] = values
            else:
                regs.pop(target, None)
            return state

        # Most remaining bytecodes overwrite the accumulator with a regular JS
        # value.  Jumps and a few bookkeeping instructions preserve it.
        if not (
            opcode.startswith("Jump")
            or opcode in {"Nop", "SetPendingMessage", "SuspendGenerator"}
        ):
            state["accu"] = frozenset()
        return state

    def prepare_context_flow(self, entry_context, exception_table):
        """Compute branch-aware current-context and context-register states.

        Synthetic Scope IDs are allocated in bytecode order, exactly as the old
        linear simplifier did, but their parent links and active ranges are
        derived from the bytecode control-flow graph.
        """
        actual_indexes = [
            index for index, line_obj in enumerate(self.code)
            if getattr(line_obj, "v8_instruction", "")
        ]
        if not actual_indexes:
            return

        # Allocate stable IDs first; parent edges are filled after dataflow.
        context_opcodes = []
        for index in actual_indexes:
            opcode, _ = self._parse_instruction(self.code[index].v8_instruction)
            if opcode in {
                "CreateFunctionContext", "CreateBlockContext", "CreateCatchContext",
                "CreateEvalContext", "CreateWithContext"
            }:
                self.context_id_by_line[index] = function_context_stack.add_new_context(0)
            if opcode in {
                "CreateFunctionContext", "CreateBlockContext", "CreateCatchContext",
                "CreateEvalContext", "CreateWithContext", "PushContext", "PopContext"
            }:
                context_opcodes.append((index, opcode))

        # The overwhelmingly common case is one function context activated at
        # entry and never popped.  It is path-insensitive and does not justify a
        # CFG walk over very large generated functions.
        if (
            len(self.context_id_by_line) == 1
            and [opcode for _, opcode in context_opcodes].count("PushContext") == 1
            and not any(opcode == "PopContext" for _, opcode in context_opcodes)
        ):
            context_id = next(iter(self.context_id_by_line.values()))
            function_context_stack.context_stack[context_id] = entry_context
            return

        line_to_index = {
            int(self.code[index].line_num): index
            for index in actual_indexes
            if str(self.code[index].line_num).lstrip("-").isdigit()
        }
        successors = self._context_successors(actual_indexes, line_to_index, exception_table)

        entry_state = {
            "current": frozenset({entry_context}),
            "accu": frozenset(),
            "regs": {},
        }
        states = {actual_indexes[0]: entry_state}
        queue = deque([actual_indexes[0]])

        while queue:
            index = queue.popleft()
            out_state = self._transfer_context_state(index, states[index])
            for successor in successors.get(index, ()):
                merged, changed = self._merge_context_states(states.get(successor), out_state)
                if changed:
                    states[successor] = merged
                    queue.append(successor)

        self.context_state_by_line = states

        # Fill parent links of newly allocated contexts from their unique entry
        # context.  Ambiguous/unreachable creates retain parent 0 and fall back
        # to the structured simplifier for their uses.
        for index, context_id in self.context_id_by_line.items():
            state = states.get(index)
            parent = self._single_context(state["current"]) if state else None
            if parent is not None:
                function_context_stack.context_stack[context_id] = parent

    def _flow_state(self):
        return self.context_state_by_line.get(self.line_index)

    def _flow_current_context(self):
        state = self._flow_state()
        return self._single_context(state["current"]) if state else None

    def _flow_register_context(self, reg):
        state = self._flow_state()
        if not state:
            return None
        return self._single_context(state["regs"].get(reg, frozenset()))

    def get_next_line(self):
        self.line_index += 1
        if self.line_index >= len(self.code):
            print("Error decompiling {self.sfi.name}, no more lines.")
        line_obj = self.code[self.line_index]
        return line_obj.translated

    def add_simplified_line(self, line):
        self.code[self.line_index].decompiled = '\t' * self.tab_level + line if line else ""

    @staticmethod
    def _parse_instruction(instruction):
        """Return the normalized opcode and comma-separated operands."""
        instruction = (instruction or "").strip()
        if not instruction:
            return "", []
        opcode, *rest = instruction.split(" ", 1)
        opcode = opcode.split(".", 1)[0]
        args = rest[0].split(", ") if rest else []
        return opcode, args

    @staticmethod
    def _context_from_register(reg, reg_scope, prev_reg_scope):
        """Resolve a synthetic Scope ID currently held in a V8 register."""
        for scope in (reg_scope, prev_reg_scope):
            value = scope.get(reg)
            context_id = get_context_idx_from_var(value) if value is not None else None
            if context_id is not None:
                return context_id
        return None

    def _create_context(self, reg_scope):
        """Materialize the context ID preallocated for this instruction."""
        new_context = self.context_id_by_line.get(self.line_index)
        if new_context is None:
            new_context = function_context_stack.add_new_context(reg_scope["current_context"])
        return f"ACCU = Scope[{new_context}]"

    def _push_context(self, target_reg, reg_scope, prev_reg_scope):
        """Apply the real PushContext register semantics."""
        previous_context = self._flow_current_context()
        if previous_context is None:
            previous_context = reg_scope["current_context"]
        state = self._flow_state()
        new_context = self._single_context(state["accu"]) if state else None
        if new_context is None:
            new_context = self._context_from_register("ACCU", reg_scope, prev_reg_scope)
        if new_context is None:
            new_context = previous_context
        reg_scope["current_context"] = new_context
        return f"{target_reg} = Scope[{previous_context}]"

    def _pop_context(self, source_reg, reg_scope, prev_reg_scope):
        """Restore the exact context saved in the PopContext operand."""
        restored_context = self._flow_register_context(source_reg)
        if restored_context is None:
            restored_context = self._context_from_register(source_reg, reg_scope, prev_reg_scope)
        if restored_context is None:
            # Compatibility fallback: older View8 assumed one lexical level.
            restored_context = function_context_stack.get_context(reg_scope["current_context"], 1)
        reg_scope["current_context"] = restored_context
        # PopContext changes V8's current-context register, not the accumulator.
        return ""

    def add_current_context_to_sub_function(self, line, reg_scope):
        # Inherit the current context to sub-function
        match = re.search(r"ConstPool\[(\d+)\]", line)
        if match:
            const_pool_index = int(match.group(1))
            if len(self.sfi.const_pool) > const_pool_index:
                name = self.sfi.const_pool[const_pool_index]
                closure_context = self._flow_current_context()
                if closure_context is None:
                    closure_context = reg_scope['current_context']
                function_context_stack.add_function_context(name, closure_context)
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

            # Already materialized synthetic context IDs do not need another
            # stack lookup.
            if scope.isdigit():
                return f"Scope[{scope}]"

            # If the scope is "CURRENT", replace it with the current context
            if scope == "CURRENT":
                current_context = self._flow_current_context()
                if current_context is None:
                    current_context = reg_scope['current_context']
                return f"Scope[{current_context}]"

            # Handles cases like CURRENT-1, r1-2

            scope_start, steps = scope.split("-", 1)
            start_context = self._flow_current_context()
            if start_context is None:
                start_context = reg_scope['current_context']

            flow_context = self._flow_register_context(scope_start)
            if flow_context is not None:
                start_context = flow_context
            elif (scope_start in reg_scope) and (get_context_idx_from_var(reg_scope[scope_start]) is not None):
                start_context = get_context_idx_from_var(reg_scope[scope_start])
            elif (scope_start in prev_reg_scope) and (get_context_idx_from_var(prev_reg_scope[scope_start]) is not None):
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


    def find_previous_store_of_accu_value(self, value):
        """
        Find the most recent visible register assignment that materialized the
        current accumulator value.

        Bytecode often ends with:
            <compute value into ACCU>
            StarN        -> rN = ACCU
            Return       -> return ACCU

        Once the StarN line has been materialized as `rN = <expr>`, returning
        `<expr>` duplicates the expression in the pseudocode. For calls this is
        semantically dangerous because it looks like a second call; for pure
        expressions it is still noisy and contradicts the bytecode shape.
        """
        for idx in range(self.line_index - 1, -1, -1):
            line_obj = self.code[idx]
            if not line_obj.visible or not line_obj.decompiled:
                continue

            line = line_obj.decompiled.strip()
            match = re.match(r"^([ra]\d+) = (.+)$", line)
            if match and match.group(2) == value:
                return match.group(1)

            # Do not scan past another explicit accumulator assignment.
            if line.startswith("ACCU = "):
                break

        return None

    def simplify_return_line(self, line, reg_scope):
        """
        Simplify `return ACCU` without duplicating an accumulator expression
        that was already materialized into a register.

        Example:
            ACCU = ("Hello" + ", World!")
            r0 = ACCU
            return ACCU

        Old output:
            r0 = ("Hello" + ", World!")
            return ("Hello" + ", World!")

        Better output:
            r0 = ("Hello" + ", World!")
            return r0
        """
        if line.strip() != "return ACCU":
            return None

        accu = reg_scope.get("ACCU")
        if not accu or accu.was_overwritten:
            return None

        stored_reg = self.find_previous_store_of_accu_value(accu.value)
        if stored_reg:
            return f"return {stored_reg}"

        return None

    def simplify_line(self, line, reg_scope, prev_reg_scope, overwritten_regs):
        instruction = getattr(self.code[self.line_index], "v8_instruction", "") or ""
        opcode, args = self._parse_instruction(instruction)

        flow_current = self._flow_current_context()
        if flow_current is not None:
            reg_scope["current_context"] = flow_current

        # Model context creation, activation, and restoration as three distinct
        # V8 operations.  The previous implementation activated a context on
        # Create*Context and treated PopContext as a one-level parent walk,
        # which fails for branch exits and nested catch/block contexts.
        if opcode in {
            "CreateFunctionContext", "CreateBlockContext", "CreateCatchContext",
            "CreateEvalContext", "CreateWithContext"
        }:
            line = self._create_context(reg_scope)
            self.code[self.line_index].visible = False
        elif opcode == "PushContext" and args:
            line = self._push_context(args[0], reg_scope, prev_reg_scope)
        elif opcode == "PopContext" and args:
            line = self._pop_context(args[0], reg_scope, prev_reg_scope)

        # `<context>` is V8's current-context register.  Materialize it so Mov
        # and context-register-based Lda/Sta instructions can participate in
        # normal register propagation.
        if "<context>" in line:
            line = line.replace("<context>", f"Scope[{reg_scope['current_context']}]")

        if "new func" in line:
            line = self.add_current_context_to_sub_function(line, reg_scope)

        # Fix the context var with context stack index
        line = self.replace_scope_stack_with_idx(line, reg_scope, prev_reg_scope)

        # replace constant regs
        if not re.search(r"^(ACCU|CASE_\d+|[ra]\d+) = ", line):
            simplified_return = self.simplify_return_line(line, reg_scope)
            if simplified_return is not None:
                return simplified_return
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
    entry_context = function_context_stack.get_func_context(sfi.name, sfi.declarer)
    simplify.prepare_context_flow(entry_context, sfi.exception_table)
    regs = {"current_context": entry_context}
    simplify.simplify_block(regs)
    if simplify.line_index != len(code) -1:
        print(f"Warning! failed to decompile {sfi.name} stopped after {simplify.line_index}/{len(code)-1}")


