import re

from Translate.translate_table import operands
from Translate.jump_blocks import convert_jumps_to_logical_flow


class Jump:
    def __init__(self, jump_type, start, end):
        self.type = jump_type
        self.start = start
        self.end = end
        self.done = False


class SwitchJump(Jump):
    def __init__(self, jump_type, start, end, line, last_case):
        super().__init__(jump_type, start, end)
        self.case_line = line
        self.last_case_start = last_case


class TranslateBytecode:
    _TARGET_RE = re.compile(r"@\s*(-?\d+)")
    _TARGET_METADATA_KEYS = (
        "is_jump_target",
        "incoming_jump_count",
        "incoming_jumps",
    )

    def __init__(self):
        self.offset = None
        self.operator = None
        self.args = None
        self.jump_table = None

    @staticmethod
    def _base_opcode(instruction):
        instruction = (instruction or "").strip()
        if not instruction:
            return ""
        return instruction.split(None, 1)[0].split(".", 1)[0]

    @classmethod
    def _instruction_targets(cls, instruction):
        return [int(value) for value in cls._TARGET_RE.findall(instruction or "")]

    @staticmethod
    def _is_branch_opcode(opcode):
        return opcode.startswith("Jump") or opcode.startswith("SwitchOn")

    @classmethod
    def _clear_jump_target_metadata(cls, code):
        for line in code:
            for key in cls._TARGET_METADATA_KEYS:
                line.drop_metadata(key)

    @classmethod
    def annotate_jump_targets(cls, code, exception_table):
        """Annotate raw bytecode targets before jump tables are rewritten.

        Returns a result dictionary suitable for storing on the owning
        SharedFunctionInfo.  Metadata is committed only when every discovered
        target resolves to a real CodeLine, so consumers can fail closed.
        """
        cls._clear_jump_target_metadata(code)
        code_by_offset = {line.line_num: line for line in code}
        incoming_by_target = {}

        def add_edge(target, edge):
            if target not in code_by_offset:
                return False
            incoming_by_target.setdefault(target, []).append(edge)
            return True

        for line in code:
            opcode = cls._base_opcode(line.v8_instruction)
            if not cls._is_branch_opcode(opcode):
                continue

            for target in cls._instruction_targets(line.v8_instruction):
                edge = {
                    "source": line.line_num,
                    "target": target,
                    "type": opcode,
                }
                if not add_edge(target, edge):
                    return {
                        "available": False,
                        "error": (
                            f"unresolved {opcode} target {target} "
                            f"from bytecode offset {line.line_num}"
                        ),
                    }

        for handler_offset, protected_range in (exception_table or {}).items():
            if not protected_range:
                continue
            try_start = protected_range[0]
            try_end = protected_range[1] if len(protected_range) > 1 else None
            edge = {
                "source": try_start,
                "target": handler_offset,
                "type": "Exception",
                "protected_end": try_end,
            }
            if not add_edge(handler_offset, edge):
                return {
                    "available": False,
                    "error": (
                        f"unresolved exception target {handler_offset} "
                        f"for protected range {protected_range!r}"
                    ),
                }

        for target, incoming in incoming_by_target.items():
            target_line = code_by_offset[target]
            incoming.sort(
                key=lambda edge: (
                    edge["source"],
                    edge["type"],
                    edge.get("protected_end", -1),
                )
            )
            target_line.set_metadata("is_jump_target", True)
            target_line.set_metadata("incoming_jump_count", len(incoming))
            target_line.set_metadata("incoming_jumps", incoming)

        return {
            "available": True,
            "edge_count": sum(len(edges) for edges in incoming_by_target.values()),
            "target_count": len(incoming_by_target),
        }

    def add_exception_jumps(self, et):
        for catch_start, try_start in et.items():
            self.jump_table["Exception"][try_start[0]] = Jump(jump_type="Exception", start=try_start[0], end=catch_start)

    def add_jump_to_table(self, jump_type, start, end):
        table = self.jump_table.get(jump_type, None)
        if table is None:
            raise Exception(f"No Table for jump type {jump_type}")
        if table.get(start):
            raise Exception(f"Jump Table {jump_type} already has key {start}")
        table[start] = Jump(jump_type=jump_type, start=start, end=end)

    def add_int_switch_to_table(self, start, end, line, last):
        self.jump_table["IntSwitch"][start] = SwitchJump(jump_type="IntSwitch", start=start, end=end, line=line, last_case=last)

    def translate(self, name, code, exception_table):
        self.jump_table = {"Loop": {}, "Exception": {}, "Catch": {}, "IntSwitch": {}, "If": {}, "Jump": {}, "IfJSReceiver": {}}
        self.add_exception_jumps(exception_table)

        for line in code:
            self.offset = line.line_num
            self.operator, *self.args = line.v8_instruction.split(' ', 1)
            self.operator = self.operator.split('.')[0]
            self.args = self.args[0].split(", ") if self.args else []
            line.translated = operands.get(self.operator, operands["Not Found"])(self)

        jump_target_result = self.annotate_jump_targets(code, exception_table)
        convert_jumps_to_logical_flow(name, code, self.jump_table)
        return jump_target_result


def translate_bytecode(name, code, et):
    return TranslateBytecode().translate(name, code, et)
