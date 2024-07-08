class ContextStack:
    def __init__(self):
        self.last_context_id = 0
        self.context_stack = {}
        self.function_name_context = {}

    def add_new_context(self, current):
        self.last_context_id += 1
        self.context_stack[self.last_context_id] = current
        return self.last_context_id

    def get_context(self, current, steps):
        context = current
        for i in range(steps):
            context = self.context_stack.get(context, 0)
        return context

    def add_function_context(self, fn, current):
        self.function_name_context[fn] = current

    def get_func_context(self, name, declarer):
        if name in self.function_name_context:
            return self.function_name_context.get(name)

        if not self.function_name_context:
            self.function_name_context[name] = 0
            return 0

        if declarer in self.function_name_context:
            self.add_function_context(name, self.function_name_context.get(declarer))
            return self.function_name_context.get(declarer)

        print("Error: function", name, "is not in context stack.")
        return 0


function_context_stack = ContextStack()