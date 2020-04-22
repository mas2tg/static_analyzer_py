import ast
import os

SEED = 'torch'

class Analyzer(ast.NodeVisitor):
    def __init__(self, names = set([SEED])):  # set(["caffe"])):
        self.names = names
        self.names_from_import = {}  # {module: set(method1, method2, method3)}
        self.stats = {}  # {method:[l1, l3, l5...]}
        self.current_path = ''
        self.current_folder = []  # used when imports import other modules
        self.current_file = ''  # legacy; not really used
        self.visited_list = []  # this is just used by ast.ImportFrom and ast.Import to avoid
        #  visiting the same file twice

    def pre_visit(self, node, file, path):  # only used one time
        self.current_path = path
        self.current_file = file
        self.visit(node)

    def update_folder_and_visit(self, node, folder):  # used by imports
        if folder not in self.current_folder:  # avoid double-adding
            self.current_folder.append(folder)  # we probably won't have duplicated names of folders
        self.visit(node)
        if folder in self.current_folder:
            self.current_folder.remove(folder)

    def visit_Call(self, node):
        # NOTE: this only gets the number of occurrences of a given call. We need this to capture calls that
        #  are not ast.Assignments (i.e. we will need this method anyways)
        first_name = self.get_id_from_node(node)  # TODO: trying without try
        cur_name = ''
        if first_name is not None and first_name in self.names:
            cur_name = self.recursive_add(node, cur_name)
            if self.stats.get(cur_name) is not None:
                self.stats[cur_name].append(node.lineno)
            else:
                self.stats[cur_name] = [node.lineno]
        self.generic_visit(node)

    def visit_Assign(self, node):
        #TODO: store and show assignments at end of execution
        assigment_id = ''
        try: # try is necessary to ensure safety when, for instance, node is bool object
            assigment_id = self.get_id_from_node(node)
        except AttributeError:
            pass

        if assigment_id is not None: # hardly will be None
            if assigment_id in self.names:
                self.add_targets_to_names(node)
            else:  # e.g. var = somemodule.api()
                try:
                    if node.value.func.attr in self.names:
                        self.add_targets_to_names(node)
                except AttributeError: # e.g var = somemodule.globalvar
                    try:
                        if node.value.attr in self.names:
                            self.add_targets_to_names(node)
                    except AttributeError:
                        pass
                        """
                        try: #e.g myvar = somemodule.globalvar.api()
                            if node.value.func.attr in self.names:
                                self.add_targets_to_names(node)
                        except AttributeError:
                            pass
                        """
        self.generic_visit(node)


    def visit_Import(self, node):
        for imp in node.names:
            possible_path = imp.name.split('.')
            # TODO: replace below with a set of paths of places we tried to visit
            if possible_path[-1] not in self.visited_list:  # check if already visited

                # check for aliases e.g import cv2 as cv
                # check either the first or the last name-e.g. import torch.nn as nn OR import folder.mymodule as module
                if possible_path[-1] in self.names or possible_path[0] in self.names:
                    if imp.asname is not None:
                        self.names.add(imp.asname)
                import_file_name = f'{possible_path[-1]}.py'

                # check if import is in current directory:
                this_path = self.current_path
                # if node.level == 1:
                #    this_path = os.path.join(self.current_path, self.current_folder[0])  # add current folder to path

                # e.g.: import some_module
                if len(possible_path) == 1:
                    try:
                        print(f'[DEBUG] Trying to open {os.path.join(this_path, import_file_name)}...')
                        with open(os.path.join(this_path, import_file_name)) as new_file:
                            print(f'[DEBUG] {import_file_name} found! Starting analysis...')
                            tree = ast.parse(new_file.read())
                            self.visited_list.append(possible_path[-1])  # add file to list of visited names; must
                            #                                       come before visit(), to avoid infinite recursion
                            self.visit(tree)

                            print(f'[DEBUG] Successfully analysed {os.path.join(this_path, import_file_name)}!')
                    except FileNotFoundError:
                        # print(f'[WARNING] Could not open {import_file_name}')
                        pass
                    finally:
                        self.generic_visit(node)
                # e.g.: import something.some_module
                elif len(possible_path) == 2:  # assuming two e.g.: some_module.submodule
                    try:
                        print(f'[DEBUG] Trying to open {os.path.join(this_path, possible_path[0], possible_path[1])}.py...')
                        with open(os.path.join(this_path, possible_path[0], f'{possible_path[1]}.py')) as new_file:
                            print(f'[DEBUG] {import_file_name} found! Starting analysis...')
                            tree = ast.parse(new_file.read())
                            self.visited_list.append(possible_path[-1])  # add file to list of visited names
                            self.update_folder_and_visit(tree, possible_path[0])
                            print(f'[DEBUG] Successfully analysed {os.path.join(this_path, possible_path[0], possible_path[1])}!')
                    except FileNotFoundError:
                        # print(f'[WARNING] Could not open {possible_path[1]}.')
                        pass
                    finally:
                        self.generic_visit(node)
            else:
                self.generic_visit(node)


    def visit_ImportFrom(self, node):

        if node.module is not None:
            module_names = node.module.split('.')
        else:
            module_names = [node.names[0].name] # e.g. from . import somemodule
        # TODO: replace below with a set of paths of places we tried to visit
        if module_names[-1] not in self.visited_list:  # check if already visited

            # check for aliases e.g import cv2 as cv
            if module_names[-1] in self.names:
                if node.names[0].asname is not None:
                    self.names.add(node.names[0].asname)

            # check if import is in current directory:
            this_path = self.current_path
            if node.level == 1 and len(self.current_folder) != 0:  # just one for now; this does not work with function analyzer
                this_path = os.path.join(self.current_path, self.current_folder[0])  # add current folder to path

            # e.g.: from somemodule import method
            if len(module_names) == 1:
                try:
                    print(f'[DEBUG] Trying to open {os.path.join(this_path, module_names[0])}.py...')
                    with open(os.path.join(this_path, f'{module_names[0]}.py')) as new_file:
                        print(f'[DEBUG] {module_names[0]}.py found! Starting analysis...')
                        tree = ast.parse(new_file.read())
                        self.visited_list.append(module_names[-1])
                        self.visit(tree)
                        print(f'[DEBUG] Successfully analysed {os.path.join(this_path, module_names[0])}.py!')
                except FileNotFoundError:
                    # print(f'[WARNING] Could not find {module_names[0]}.py!')
                    pass
                finally:
                    self.generic_visit(node)
            # e.g.: from somemodule.submodule import method
            elif len(module_names) == 2:
                try:
                    print(f'[DEBUG] Trying to open {os.path.join(this_path, module_names[0] ,module_names[1])}.py...')
                    with open(os.path.join(this_path, f'{module_names[0]}', f'{module_names[1]}.py')) as new_file:
                        print(f'[DEBUG] {module_names[1]}.py found! Starting analysis...')
                        tree = ast.parse(new_file.read())
                        self.visited_list.append(module_names[-1])
                        self.update_folder_and_visit(tree, module_names[0])
                        print(f'[DEBUG] Successfully analysed {os.path.join(this_path, module_names[0], module_names[1])}.py!')
                except FileNotFoundError:
                    # print(f'[WARNING] Could not find {module_names[1]}.py!')
                    pass
                finally:
                    self.generic_visit(node)
        else:
            self.generic_visit(node)

    def report(self):
        # TODO: sort by last word!
        print(f'names: {self.names}')

        stats_keys = sorted(self.stats.keys(), key=lambda n: n.split('.')[-1].lower())

        #for stat in sorted(self.stats):
        #    print(f'{stat}; {self.stats[stat]}; count={len(self.stats[stat])}')
        prev = ''
        for key in stats_keys:
            local_key = key.split('.')[-1].lower()
            if local_key != prev:
                print()
            print(f'{key}; {self.stats[key]}; count{len(self.stats[key])}')
            prev = local_key

    def add_targets_to_names(self, node):
        for target in node.targets:
            # TODO: (optional) gotta fix this with recursion
            # in practice targets are almost always 'somevar' instead of 'module.somevar'
            if 'id' in target._fields:
                self.names.add(f'{target.id}')
            elif 'attr' in target._fields:
                self.names.add(f'{target.attr}')

    # get full name of api call: mymodule.submodule.api() -> returns 'mymodule.submodule.api'
    def recursive_add(self, node, cur_name):
        try:
            cur_name = f'.{node.attr}{cur_name}' # append attribute to the end of string
        except AttributeError:
            pass
        for field, child in ast.iter_fields(node):
            if field == 'id':
                return f'{child}{cur_name}'
                # if we find id, we are done
            if field == 'value' or field == 'func' or field == 'elt':
                return self.recursive_add(child, cur_name)

    # get first name: mymodule.api() -> returns 'mymodule'
    def get_id_from_node(self, node):
        for field, value in ast.iter_fields(node):
            if field == 'id':
                return value
            if field == 'value' or field == 'func' or field == 'elt':
                return self.get_id_from_node(value)


class BodyAnalyzer(Analyzer):
    def __init__(self, function_name, names=set([SEED])):  # set(['caffe'])):
        self.function_name = function_name
        Analyzer.__init__(self, names)

    def visit_Return(self, node):
        try:
            if self.get_id_from_node(node) in self.names:
                self.names.add(f'{self.function_name}')  # add method name to self.names
        except AttributeError:
            try:
                if node.value.left.id in self.names or node.value.right.id in self.names:
                    self.names.add(f'{self.function_name}')
            except AttributeError:
                pass

        # self.generic_visit(node) # once we get to Return, no need to proceed


class FunctionAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.stats = [SEED]  # ['caffe']  # TODO: change this list to set

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
