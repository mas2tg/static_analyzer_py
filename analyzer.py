import ast
import os


class Analyzer(ast.NodeVisitor):
    def __init__(self, names=set(["cv2"])):
        self.names = names
        self.names_from_import = {}  # {module: set(method1, method2, method3)}
        self.stats = {}  # {method:[l1, l3, l5...]}
        self.current_path = ''
        self.current_file = ''
        self.visited_list = []  # this is just used by ast.ImportFrom and ast.Import to avoid
        #  visiting the same file twice

    def pre_visit(self, node, file, path):  # this is only necessary when visiting multiple files
        self.current_path = path
        self.current_file = file
        self.visit(node)

    def visit_Call(self, node):
        # NOTE: this only gets the number of occurrences of a given call. We need this to capture calls that
        #  are not ast.Assignments

        # e.g.: method_of_interest()
        if 'id' in node.func._fields and node.func.id in self.names:
            method = f'{node.func.id}'
            if self.stats.get(method) is not None:
                self.stats[method].append(node.func.lineno)  # only line number
            else:
                self.stats[method] = [node.func.lineno]

        # e.g.: some_module.method_of_interest()
        if 'value' in node.func._fields and 'id' in node.func.value._fields:  # check if fields exist
            if node.func.value.id in self.names:  # check if in set
                method = f'{node.func.value.id}.{node.func.attr}'
                if self.stats.get(method) is not None:
                    # self.stats[method].append(self.current_file + "@L:" + str(node.func.lineno))
                    self.stats[method].append(node.func.lineno)  # only line number
                else:
                    self.stats[method] = [node.func.lineno]

        # e.g.: some_module.name_of_interest.method_of_interest()
        if 'value' in node.func._fields and 'attr' in node.func.value._fields \
                and node.func.value.attr in self.names:
            method = f'{node.func.value.value.id}.{node.func.value.attr}.{node.func.attr}'
            if self.stats.get(method) is not None:
                # self.stats[method].append(self.current_file + "@L:" + str(node.func.lineno))
                self.stats[method].append(node.func.lineno)  # only line number
            else:
                self.stats[method] = [node.func.lineno]

        self.generic_visit(node)

    def visit_Assign(self, node):
        # TODO: need to find a way to traverse the tree automatically and get to the leaf node
        # NOTE: First check for ast.Subscript
        # e.g.: video_capture.read()[1]
        if ('value' in node.value._fields and
            type(node.value.value) is not bool and
            node.value.value is not None and
            'func' in node.value.value._fields and
            'value' in node.value.value.func._fields and
                'id' in node.value.value.func.value._fields):
            if node.value.value.func.value.id in self.names:  # check if id is in self.name (and derived from cv2)
                self.add_targets_to_names(node)

        # NOTE: Second check for ast.Call
        elif ('func' in node.value._fields):
            # e.g.: localvar = method()
            if 'id' in node.value.func._fields and node.value.func.id in self.names:
                self.add_targets_to_names(node)

            # e.g.: localvar = somemodule.method()
            if('value' in node.value.func._fields and
                    'id' in node.value.func.value._fields):
                if node.value.func.value.id in self.names:  # check if id in self.name (and derived from cv2)
                    self.add_targets_to_names(node)
                # e.g.: mylocalvar = somemodule.relevantname.somemethod()
                elif 'attr' in node.value.func._fields and node.value.func.attr in self.names:
                    self.add_targets_to_names(node)

        # NOTE: Third check for ast.Attribute i.e. immediate element after '.'
        # e.g.: mylocalvar = somemodule.globalvar
        elif ('attr' in node.value._fields and
                type(node.value.attr) is not bool and
                node.value.attr is not None and
                node.value.attr in self.names):
            self.add_targets_to_names(node)

        self.generic_visit(node)

    # TODO: need to store global variables in a different data structure e.g.: {'module':[method1, method2]}
    def visit_Import(self, node):
        for imp in node.names:
            possible_path = imp.name.split('.')
            if possible_path[-1] not in self.visited_list:  # check if already visited
                # e.g.: import some_module
                if len(possible_path) < 2:
                    import_file_name = f'{imp.name}.py'
                    try:
                        print(f'[DEBUG] Trying to open {os.path.join(self.current_path, import_file_name)}...')
                        with open(os.path.join(self.current_path, import_file_name)) as new_file:
                            print(f'[DEBUG] {import_file_name} found!')
                            tree = ast.parse(new_file.read())
                            self.visit(tree)
                            self.visited_list.append(import_file_name)  # add file to list of visited names
                            print(f'[DEBUG] Successfully analysed {os.path.join(self.current_path, import_file_name)}!')
                    except FileNotFoundError:
                        print(f'[WARNING] Could not open {os.path.join(self.current_path, import_file_name)}')
                    finally:
                        self.generic_visit(node)
                # e.g.: import something.some_module
                elif len(possible_path) == 2:  # assume two e.g.: some_module.submodule
                    try:
                        print(f'[DEBUG] Trying to open {os.path.join(self.current_path, imp.name)}...')
                        with open(os.path.join(self.current_path, possible_path[0], f'{possible_path[1]}.py')) as new_file:
                            print(f'[DEBUG] {import_file_name} found!')
                            tree = ast.parse(new_file.read())
                            self.visit(tree)
                            self.visited_list.append(import_file_name)  # add file to list of visited names
                            print(f'[DEBUG] Successfully analysed {os.path.join(self.current_path, possible_path[0], possible_path[1])}!')
                    except FileNotFoundError:
                        print(f'[WARNING] Could not open {os.path.join(self.current_path, possible_path[0], possible_path[1])}.')
                    finally:
                        self.generic_visit(node)
            else:
                self.generic_visit(node)


    def visit_ImportFrom(self, node):

        module_names = node.module.split('.')
        if module_names[-1] not in self.visited_list:  # check if already visited
            # e.g.: from somemodule import method
            if len(module_names) == 1:
                try:
                    print(f'[DEBUG] Trying to open {os.path.join(self.current_path, module_names[0])}.py...')
                    with open(os.path.join(self.current_path, f'{module_names[0]}.py')) as new_file:
                        print(f'[DEBUG] {module_names[0]}.py found!')
                        tree = ast.parse(new_file.read())
                        self.visit(tree)
                        self.visited_list.append(module_names[-1])
                        print(f'[DEBUG] Successfully analysed {os.path.join(self.current_path, module_names[0])}.py!')
                except FileNotFoundError:
                    print(f'[WARNING] Could not find {module_names[0]}.py!')
                finally:
                    self.generic_visit(node)
            # e.g.: from somemodule.submodule import method
            elif len(module_names) == 2:
                try:
                    print(f'[DEBUG] Trying to open {os.path.join(self.current_path, module_names[0] ,module_names[1])}.py...')
                    with open(os.path.join(self.current_path, f'{module_names[0]}', f'{module_names[1]}.py')) as new_file:
                        print(f'[DEBUG] {module_names[1]}.py found!')
                        tree = ast.parse(new_file.read())
                        self.visit(tree)
                        self.visited_list.append(module_names[-1])
                        print(f'[DEBUG] Successfully analysed {os.path.join(self.current_path, module_names[1])}.py!')
                except FileNotFoundError:
                    print(f'[WARNING] Could not find {module_names[1]}.py!')
                finally:
                    self.generic_visit(node)
        else:
            self.generic_visit(node)

    def report(self):
        print(f'names: {self.names}')
        for stat in self.stats:
            print(f'{stat}; {self.stats[stat]}; count={len(self.stats[stat])}')

    def add_targets_to_names(self, node):
        for target in node.targets:
            if 'id' in target._fields:
                self.names.add(f'{target.id}')
            elif 'attr' in target._fields:
                self.names.add(f'{target.attr}')


class BodyAnalyzer(Analyzer):
    def __init__(self, function_name, names=set(['cv2'])):
        self.function_name = function_name
        Analyzer.__init__(self, names)

    def visit_Return(self, node):
        if 'value' in node._fields and node.value is not None:
            if 'left' in node.value._fields:  # deal with BinOp
                if ('id' in node.value.left._fields and node.value.left.id in self.names) or \
                        ('right' in node.value._fields and 'id' in node.value.right._fields and \
                         node.value.right.id in self.names):
                    self.names.add(f'{self.function_name}')  # add method name to self.names

            elif 'id' in node.value._fields:
                if node.value.id in self.names:  # single value
                    self.names.add(f'{self.function_name}')  # add method name to self.names

            # NOTE: the below does not capture very complicated statements(e.g.: elf._cap_list[index].get(capture_prop))
            elif 'func' in node.value._fields:  # call in return statement
                if 'value' in node.value.func._fields:
                    if 'id' in node.value.func.value._fields:
                        if node.value.func.value.id in self.names:
                            self.names.add(f'{self.function_name}')  # add method name to self.names
        # self.generic_visit(node) # once we get to Return, no need to proceed


class FunctionAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.stats = ['cv2']  # list
        self.current_path = ''
        self.current_file = ''

    def visit_FunctionDef(self, node):
        print(f'[INFO] found function definition with name {node.name}')
        body_analyzer = BodyAnalyzer(node.name)  # need to use another analyzer to look at body
        body_analyzer.visit(node)
        ans = node.name in body_analyzer.names
        del body_analyzer
        if ans:
            self.stats.append(node.name)
        print(f'[INFO] finished analyzing function {node.name}')

    def report(self):
        print(f'[INFO] stats={self.stats}')
