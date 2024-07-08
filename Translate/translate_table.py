import ast


def expand_reg_list(reg_rang):
    reg_range_split = reg_rang.split('-')
    start = reg_range_split[0][1:]
    end = reg_range_split[1][1:]
    if "this" in start or "this" in end:
        return ["<this>"]
    return ['r' + str(i) for i in range(int(start), int(end) + 1, 1)]


def get_typeof_value(typeof_num):
    typeof_dict = {
        "#0": "number",
        "#1": "string",
        "#2": "symbol",
        "#3": "boolean",
        "#4": "bigint",
        "#5": "undefined",
        "#6": "function",
        "#7": "object"
        }
    return typeof_dict.get(typeof_num, typeof_num)


def invoke_intrinsic(args):
    type_ = args[0][1:-1]
    if "_AsyncFunctionEnter" in type_:
        return ""
    if "_AsyncFunctionResolve" in type_:
        return f"ACCU = {', '.join(expand_reg_list(args[1])[1:])}"

    if "_AsyncFunctionReject" in type_:
        return f"ACCU = {', '.join(expand_reg_list(args[1])[1:])}"

    if "_AsyncFunctionAwait" in type_:
        return f"ACCU = await {', '.join(expand_reg_list(args[1])[1:])}"
    return f"ACCU = {args[0][1:-1]}({', '.join(expand_reg_list(args[1]))})"


def add_jump_blocks(obj, type_):
    jump_to = int(obj.args[-1].split(' ')[-1][:-1])

    if jump_to < obj.offset:
        obj.add_jump_to_table(jump_type="Loop", start=jump_to, end=obj.offset)
        return
    obj.add_jump_to_table(jump_type=type_, start=obj.offset, end=jump_to)


def add_switch_on(obj):
    line = ",".join(obj.args)
    dic = ast.literal_eval(line[line.find("{"):].replace("@", ""))
    # sort by jump to
    sorted_dic = sorted(dic.items(), key=lambda x: x[1])
    prev_case_start = obj.offset
    case_line = "switch (ACCU)\ndefault:\n"
    last_case = sorted_dic[-1][1]

    for key, case_start in sorted_dic:
        if case_start == prev_case_start:
            case_line += f"case ({key}):\n"
            continue

        obj.add_int_switch_to_table(start=prev_case_start, end=case_start, line=case_line, last=last_case)
        prev_case_start = case_start
        case_line = f"case ({key}):\n"

    obj.add_int_switch_to_table(start=prev_case_start, end=-1, line=case_line, last=last_case)


def get_scope_id(args):
    if "<context>" in args[0]:
        return f"CURRENT-{args[2][1:-1]}"
    return f"{args[0]}-{args[2][1:-1]}"


operands = {
    #################
    # call operands #
    #################

    "CallProperty": lambda obj: f"ACCU = {obj.args[0]}({', '.join(expand_reg_list(obj.args[1])[1:])})",
    "CallProperty0": lambda obj: f"ACCU = {obj.args[0]}()",
    "CallProperty1": lambda obj: f"ACCU = {obj.args[0]}({obj.args[2]})",
    "CallProperty2": lambda obj: f"ACCU = {obj.args[0]}({obj.args[2]}, {obj.args[3]})",
    "CallAnyReceiver": lambda obj: f"ACCU = {obj.args[0]}({', '.join(expand_reg_list(obj.args[1]))})",
    "CallUndefinedReceiver": lambda obj: f"ACCU = {obj.args[0]}({', '.join(expand_reg_list(obj.args[1]))})",
    "CallUndefinedReceiver0": lambda obj: f"ACCU = {obj.args[0]}()",
    "CallUndefinedReceiver1": lambda obj: f"ACCU = {obj.args[0]}({obj.args[1]})",
    "CallUndefinedReceiver2": lambda obj: f"ACCU = {obj.args[0]}({obj.args[1]}, {obj.args[2]})",
    "CallWithSpread": lambda obj: f"ACCU = {obj.args[0]}(...{', '.join(expand_reg_list(obj.args[1]))})",
    "CallRuntime": lambda obj: f"ACCU = {obj.args[0][1:-1]}({', '.join(expand_reg_list(obj.args[1]))})",
    "CallJSRuntime": lambda obj: f"ACCU = {obj.args[0][1:-1]}({', '.join(expand_reg_list(obj.args[1]))})",
    "InvokeIntrinsic": lambda obj: invoke_intrinsic(obj.args),
    "Construct": lambda obj: f"ACCU = {obj.args[0]}({', '.join(expand_reg_list(obj.args[1]))})",
    "ConstructWithSpread": lambda obj: f"ACCU = {obj.args[0]}(...{', '.join(expand_reg_list(obj.args[1]))}))",

    ###################
    # Create operands #
    ###################

    "CreateEmptyArrayLiteral": lambda obj: f"ACCU = []",
    "CreateEmptyObjectLiteral": lambda obj: f"ACCU = {'{}'}",
    "CreateArrayLiteral": lambda obj: f"ACCU = new ConstPool{obj.args[0]}",
    "CreateObjectLiteral": lambda obj: f"ACCU = new ConstPool{obj.args[0]}",
    "CreateRegExpLiteral": lambda obj: f"ACCU = \\ConstPool{obj.args[0]}\\",
    "CreateArrayFromIterable": lambda obj: f"ACCU = Array.from(ACCU)",
    "CreateClosure": lambda obj: f"ACCU = new func ConstPool{obj.args[0]}",
    "CreateRestParameter": lambda obj: "ACCU = ...",
    "CreateMappedArguments": lambda obj: "ACCU = Array.map(a0)",
    "CreateUnmappedArguments": lambda obj: f"ACCU = unmapped(a0)",

    #################
    # Jump operands #
    #################

    "Jump": lambda obj: add_jump_blocks(obj, "Jump") or "",
    "JumpLoop": lambda obj: add_jump_blocks(obj, "JumpLoop") or "",
    "JumpIfTrue": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU)",
    "JumpIfFalse": lambda obj: add_jump_blocks(obj, "If") or "if (!ACCU)",
    "JumpIfNull": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU == null)",
    "JumpIfNotNull": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU != null)",
    "JumpIfUndefined": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU == undefined)",
    "JumpIfNotUndefined": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU != undefined)",
    "JumpIfUndefinedOrNull": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU == undefined)",
    "JumpIfToBooleanTrue": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU)",
    "JumpIfToBooleanFalse": lambda obj: add_jump_blocks(obj, "If") or "if (!ACCU)",
    "JumpIfJSReceiver": lambda obj: add_jump_blocks(obj, "IfJSReceiver") or "if (JumpIfJSReceiver(ACCU))",

    "JumpConstant": lambda obj: add_jump_blocks(obj, "Jump") or "",
    "JumpLoopConstant": lambda obj: add_jump_blocks(obj, "JumpLoop") or "",
    "JumpIfTrueConstant": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU)",
    "JumpIfFalseConstant": lambda obj: add_jump_blocks(obj, "If") or "if (!ACCU)",
    "JumpIfNullConstant": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU == null)",
    "JumpIfNotNullConstant": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU != null)",
    "JumpIfUndefinedConstant": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU == undefined)",
    "JumpIfNotUndefinedConstant": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU != undefined)",
    "JumpIfUndefinedOrNullConstant": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU == undefined)",
    "JumpIfToBooleanTrueConstant": lambda obj: add_jump_blocks(obj, "If") or "if (ACCU)",
    "JumpIfToBooleanFalseConstant": lambda obj: add_jump_blocks(obj, "If") or "if (!ACCU)",
    "JumpIfJSReceiverConstant": lambda obj: add_jump_blocks(obj, "IfJSReceiver") or "if (!JumpIfJSReceiver(ACCU))",

    #################
    # Load operands #
    #################

    'LdaZero': lambda obj: f"ACCU = 0",
    'LdaUndefined': lambda obj: f"ACCU = undefined",
    'LdaTrue': lambda obj: f"ACCU = true",
    'LdaFalse': lambda obj: f"ACCU = false",
    'LdaNull': lambda obj: f"ACCU = null",
    'LdaSmi': lambda obj: f"ACCU = {obj.args[0][1:-1]}",
    "Ldar": lambda obj: f"ACCU = {obj.args[0]}",
    "Ldar0": lambda obj: f"ACCU = r0",
    "Ldar1": lambda obj: f"ACCU = r1",
    "Ldar2": lambda obj: f"ACCU = r2",
    "Ldar3": lambda obj: f"ACCU = r3",
    "Ldar4": lambda obj: f"ACCU = r4",
    "Ldar5": lambda obj: f"ACCU = r5",
    "Ldar6": lambda obj: f"ACCU = r6",
    "Ldar7": lambda obj: f"ACCU = r7",
    "Ldar8": lambda obj: f"ACCU = r8",
    "Ldar9": lambda obj: f"ACCU = r9",
    "Ldar10": lambda obj: f"ACCU = r10",
    "Ldar11": lambda obj: f"ACCU = r11",
    "Ldar12": lambda obj: f"ACCU = r12",
    "Ldar13": lambda obj: f"ACCU = r13",
    "Ldar14": lambda obj: f"ACCU = r14",
    "Ldar15": lambda obj: f"ACCU = r15",
    "LdaGlobalInsideTypeof": lambda obj: f"ACCU = typeof(ConstPool{obj.args[0]})",
    "LdaGlobal": lambda obj: f"ACCU = ConstPool{obj.args[0]}",
    "LdaLookupGlobalSlot": lambda obj: f"ACCU = ConstPool{obj.args[0]}",
    "LdaLookupSlot": lambda obj: f"ACCU = ConstPool{obj.args[0]}",
    "LdaContextSlot": lambda obj: f"ACCU = Scope[{get_scope_id(obj.args)}]{obj.args[1]}",
    "LdaLookupContextSlot": lambda obj: f"ACCU = Scope[CURRENT-{obj.args[2][1:-1]}]{obj.args[1]}",
    "LdaConstant": lambda obj: f"ACCU = ConstPool{obj.args[0]}",
    "LdaNamedProperty": lambda obj: f"ACCU = {obj.args[0]}[ConstPool{obj.args[1]}]",
    "LdaNamedPropertyFromSuper": lambda obj: f"ACCU = ACCU[ConstPool{obj.args[1]}]",
    "GetNamedPropertyFromSuper": lambda obj: f"ACCU = ACCU[ConstPool{obj.args[1]}]",
    "GetNamedProperty": lambda obj: f"ACCU = {obj.args[0]}[ConstPool{obj.args[1]}]",
    "GetKeyedProperty": lambda obj: f"ACCU = {obj.args[0]}[ACCU]",
    "GetTemplateObject": lambda obj: f"ACCU = ConstPool{obj.args[0]}",
    "LdaKeyedProperty": lambda obj: f"ACCU = {obj.args[0]}[ACCU]",
    "LdaCurrentContextSlot": lambda obj: f"ACCU = Scope[CURRENT]{obj.args[0]}",
    'LdaImmutableCurrentContextSlot': lambda obj: f"ACCU = Scope[CURRENT]{obj.args[0]}",
    "LdaImmutableContextSlot": lambda obj: f"ACCU = Scope[{get_scope_id(obj.args)}]{obj.args[1]}",


    #################
    # Star operands #
    #################

    "Star0": lambda obj: f"r0 = ACCU",
    "Star1": lambda obj: f"r1 = ACCU",
    "Star2": lambda obj: f"r2 = ACCU",
    "Star3": lambda obj: f"r3 = ACCU",
    "Star4": lambda obj: f"r4 = ACCU",
    "Star5": lambda obj: f"r5 = ACCU",
    "Star6": lambda obj: f"r6 = ACCU",
    "Star7": lambda obj: f"r7 = ACCU",
    "Star8": lambda obj: f"r8 = ACCU",
    "Star9": lambda obj: f"r9 = ACCU",
    "Star10": lambda obj: f"r10 = ACCU",
    "Star11": lambda obj: f"r11 = ACCU",
    "Star12": lambda obj: f"r12 = ACCU",
    "Star13": lambda obj: f"r13 = ACCU",
    "Star14": lambda obj: f"r14 = ACCU",
    "Star15": lambda obj: f"r15 = ACCU",
    'Star': lambda obj: f"{obj.args[0]} = ACCU",
    "StaGlobal": lambda obj: f"ConstPool{obj.args[0]} = ACCU",
    "StaLookupSlot": lambda obj: f"ConstPool{obj.args[0]} = ACCU",
    "StaContextSlot": lambda obj: f"Scope[{get_scope_id(obj.args)}]{obj.args[1]} = ACCU",
    # "StaLookupContextSlot": lambda obj: f"Scope[{get_scope_id(obj.args)}]{obj.args[1]} = ACCU",
    "StaCurrentContextSlot": lambda obj: f"Scope[CURRENT]{obj.args[0]} = ACCU",
    "StaInArrayLiteral": lambda obj: f"{obj.args[0]}[{obj.args[1]}] = ACCU",
    "StaNamedOwnProperty": lambda obj: f"{obj.args[0]}[ConstPool{obj.args[1]}] = ACCU",
    "StaNamedProperty": lambda obj: f"{obj.args[0]}[ConstPool{obj.args[1]}] = ACCU",
    "StaKeyedProperty": lambda obj: f"{obj.args[0]}[{obj.args[1]}] = ACCU",
    "StaKeyedPropertyAsDefine": lambda obj: f"{obj.args[0]}[{obj.args[1]}] = ACCU",
    "StaDataPropertyInLiteral": lambda obj: f"{obj.args[0]}.{obj.args[1]} = ACCU",
    "SetNamedProperty": lambda obj: f"{obj.args[0]}[ConstPool{obj.args[1]}] = ACCU",
    "SetKeyedProperty": lambda obj: f"{obj.args[0]}[{obj.args[1]}] = ACCU",
    "DefineNamedOwnProperty": lambda obj: f"{obj.args[0]}[ConstPool{obj.args[1]}] = ACCU",
    "DefineKeyedOwnPropertyInLiteral": lambda obj: f"{obj.args[0]}[{obj.args[1]}] = ACCU",
    "DefineKeyedOwnProperty": lambda obj: f"{obj.args[0]}[{obj.args[1]}] = ACCU",

    #################
    # Test operands #
    #################

    "TestEqual": lambda obj: f"ACCU = {obj.args[0]} == ACCU",
    "TestEqualStrict": lambda obj: f"ACCU = {obj.args[0]} === ACCU",
    "TestGreaterThan": lambda obj: f"ACCU = {obj.args[0]} > ACCU",
    "TestGreaterThanOrEqual": lambda obj: f"ACCU = {obj.args[0]} >= ACCU",
    "TestLessThan": lambda obj: f"ACCU = {obj.args[0]} < ACCU",
    "TestLessThanOrEqual": lambda obj: f"ACCU = {obj.args[0]} <= ACCU",
    "TestIn": lambda obj: f"ACCU = {obj.args[0]} in ACCU",
    "TestInstanceOf": lambda obj: f"ACCU = {obj.args[0]} instanceof ACCU",
    "TestReferenceEqual": lambda obj: f"ACCU = {obj.args[0]} === ACCU",
    "TestUndetectable": lambda obj: f"ACCU = undetectable === ACCU",
    "TestTypeOf": lambda obj: f"ACCU = typeof(ACCU) == {get_typeof_value(obj.args[0])}",
    "TestNull": lambda obj: f"ACCU = null == ACCU",
    "TestUndefined": lambda obj: f"ACCU = undefined == ACCU",

    ###############
    # To operands #
    ###############

    "ToString": lambda obj: f"ACCU = String(ACCU)",
    "ToNumeric": lambda obj: f"ACCU = Number(ACCU)",
    "ToNumber": lambda obj: f"ACCU = Number(ACCU)",
    "ToObject": lambda obj: f"ACCU = ToObject(ACCU)",
    "ToName": lambda obj: f"ACCU = ToName(ACCU)",
    "ToBooleanLogicalNot": lambda obj: f"ACCU = !Boolean(ACCU)",
    "CloneObject": lambda obj: f"ACCU = CloneObject({obj.args[0]})",

    #######################
    # Arithmetic operands #
    #######################

    "Add": lambda obj: f"ACCU = ({obj.args[0]} + ACCU)",
    "Inc": lambda obj: f"ACCU = (ACCU + 1)",
    "Sub": lambda obj: f"ACCU = ({obj.args[0]} - ACCU)",
    "Dec": lambda obj: f"ACCU = (ACCU - 1)",
    "Mod": lambda obj: f"ACCU = ({obj.args[0]} % ACCU)",
    "Mul": lambda obj: f"ACCU = ({obj.args[0]} * ACCU)",
    "Exp": lambda obj: f"ACCU = ({obj.args[0]} ** ACCU)",
    "Div": lambda obj: f"ACCU = ({obj.args[0]} / ACCU)",
    "Negate": lambda obj: f"ACCU = (-ACCU)",
    "LogicalNot": lambda obj: f"ACCU = !(ACCU)",
    "BitwiseXor": lambda obj: f"ACCU = ({obj.args[0]} ^ ACCU)",
    "BitwiseOr": lambda obj: f"ACCU = ({obj.args[0]} | ACCU)",
    "BitwiseAnd": lambda obj: f"ACCU = ({obj.args[0]} & ACCU)",
    "BitwiseNot": lambda obj: f"ACCU = ~(ACCU)",
    "ShiftRightLogical": lambda obj: f"ACCU = ({obj.args[0]} >>> ACCU)",
    "ShiftRight": lambda obj: f"ACCU = ({obj.args[0]} >> ACCU)",
    "ShiftLeftLogical": lambda obj: f"ACCU = ({obj.args[0]} <<< ACCU)",
    "ShiftLeft": lambda obj: f"ACCU = ({obj.args[0]} << ACCU)",

    "AddSmi": lambda obj: f"ACCU = (ACCU + {obj.args[0][1:-1]})",
    "SubSmi": lambda obj: f"ACCU = (ACCU - {obj.args[0][1:-1]})",
    "ModSmi": lambda obj: f"ACCU = (ACCU % {obj.args[0][1:-1]})",
    "MulSmi": lambda obj: f"ACCU = (ACCU * {obj.args[0][1:-1]})",
    "ExpSmi": lambda obj: f"ACCU = (ACCU ** {obj.args[0]})",
    "DivSmi": lambda obj: f"ACCU = (ACCU \\ {obj.args[0][1:-1]})",
    "NegateSmi": lambda obj: f"ACCU = -(ACCU)",
    "BitwiseXorSmi": lambda obj: f"ACCU = (ACCU ^ {obj.args[0][1:-1]})",
    "BitwiseOrSmi": lambda obj: f"ACCU = (ACCU | {obj.args[0][1:-1]})",
    "BitwiseAndSmi": lambda obj: f"ACCU = (ACCU & {obj.args[0][1:-1]})",
    "BitwiseNotSmi": lambda obj: f"ACCU = ~(ACCU)",
    "ShiftRightLogicalSmi": lambda obj: f"ACCU = (ACCU >>> {obj.args[0][1:-1]})",
    "ShiftRightSmi": lambda obj: f"ACCU = (ACCU >> {obj.args[0][1:-1]})",
    "ShiftLeftLogicalSmi": lambda obj: f"ACCU = (ACCU <<< {obj.args[0][1:-1]})",
    "ShiftLeftSmi": lambda obj: f"ACCU = (ACCU << {obj.args[0][1:-1]})",

    ##################
    # throw operands #
    ##################

    "Throw": lambda obj: "",
    "ReThrow": lambda obj: "",
    "ThrowSuperNotCalledIfHole": lambda obj: "",
    "ThrowSuperAlreadyCalledIfNotHole": lambda obj: "",
    "ThrowIfNotSuperConstructor": lambda obj: "",
    "ThrowSymbolIteratorInvalid": lambda obj: "",
    "ThrowReferenceErrorIfHole": lambda obj: "",  # f"// ThrowReferenceErrorIfHole ConstPool{obj.args[0]}",

    #################
    # more operands #
    #################

    "Mov": lambda obj: f"{obj.args[1]} = {obj.args[0]}",
    "Return": lambda obj: f"return ACCU",
    "TypeOf": lambda obj: f"ACCU = TypeOf(ACCU)",
    "GetIterator": lambda obj: f"ACCU = GetIterator({obj.args[0]})",
    "GetSuperConstructor": lambda obj: f"{obj.args[0]} = supper",
    "DeletePropertySloppy": lambda obj: f"delete ACCU[{obj.args[0]}]",
    "DeletePropertyStrict": lambda obj: f"delete ACCU[{obj.args[0]}]",

    ###################
    # ignore operands #
    ###################

    "SuspendGenerator": lambda obj: f"",
    "ResumeGenerator": lambda obj: f"",
    "SetPendingMessage": lambda obj: f"",
    "SwitchOnGeneratorState": lambda obj: "",
    "SwitchOnSmiNoFeedback": lambda obj: add_switch_on(obj) or "",
    "LdaTheHole": lambda obj: f"ACCU = null",
    "Debugger": lambda obj: f"//Debugger",

    ###################
    # context operands #
    ###################

    "PopContext": lambda obj: f"PopContext()",
    "PushContext": lambda obj: f"{obj.args[0]} = ACCU",
    "CreateFunctionContext": lambda obj: f"ACCU = PushContext(\"Function\")",
    "CreateBlockContext": lambda obj: f"ACCU = PushContext(\"Block\")",
    "CreateCatchContext": lambda obj: f"ACCU = PushContext(\"Catch\")",
    "CreateEvalContext": lambda obj: f"ACCU = PushContext(\"Eval\")",
    "CreateWithContext": lambda obj: f"ACCU = PushContext(\"With\")",

    ############
    # for loop #
    ############
    "ForInEnumerate": lambda obj: f"{obj.args[0]} = Generator(ACCU)",
    "ForInPrepare": lambda obj: f"",
    "ForInContinue": lambda obj: f"ACCU = GeneratorContinue({obj.args[0]})",
    "ForInNext": lambda obj: f"ACCU = {obj.args[0]}.next().value",
    "ForInStep": lambda obj: f"ACCU = GeneratorStep({obj.args[0]})",

    "Not Found": lambda obj: input(f"Operator {obj.operator} was not found in table") and f"//{obj.operator})",

}

# more operators to add
# LdaLookupSlotInsideTypeof
# LdaLookupContextSlotInsideTypeof
# LdaLookupGlobalSlotInsideTypeof
#
# LdaModuleVariable
# StaModuleVariable
#
# CollectTypeProfile
#
# CallRuntimeForPair
#
# IncBlockCounter
# Abort
