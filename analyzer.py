import ast
import os

SEED = ['cv2']

class Analyzer(ast.NodeVisitor):
    def __init__(self, names = set(SEED)):  # set(["caffe"])):
        self.names = names
        self.names_from_import = {}  # {module: set(method1, method2, method3)}
        self.stats = {}  # {method:[l1, l3, l5...]}
        self.current_path = ''
        self.current_folder = []  # used when imports import other modules
        # self.visited_list = []  # TO BE DECOMISSIONED: this is just used by ast.ImportFrom and ast.Import to avoid
        self.attempted_paths = set([])  # visiting the same file twice


    def pre_visit(self, node, file, path):  # only used one time
        self.current_path = path
        self.current_file = file
        self.visit(node)

    #import mod1.mod2.mod3
    def update_folder_and_visit(self, node, folder):  # used by imports
        if folder[0] not in self.current_folder:  # enqueue
            self.current_folder.append(folder[0])
        self.visit(node)
        if folder[-1] in self.current_folder:  # dequeue
            self.current_folder.remove(folder[-1])

    def visit_Call(self, node):
        # NOTE: this only gets the number of occurrences of a given call. We need this to capture calls that
        #  are not ast.Assignments (i.e. we will need this method anyways)
        # TODO: must keep track of passed parameters and then check function definitions for returned
        #  objects
        first_name = self.get_id_from_node(node)
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
        try:  # try is necessary to ensure safety when, for instance, node is bool object
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

            module_names = imp.name.split('.')  # [module1.script]
            #possible_import = imp.name.replace('.', '/')  # module/script
            #print(possible_import)

            possible_path = self.current_path
            for folder in self.current_folder:
                possible_path = f'{os.path.join(possible_path, folder)}'
            for mods in module_names:
                possible_path = f'{os.path.join(possible_path, mods)}'
            possible_path = f'{possible_path}.py'

            second_possible_path = self.current_path
            if len(self.current_folder) > 0: # sometimes imports reference project root dir
                for mods in module_names:  # instead of the current dir
                    second_possible_path = f'{os.path.join(second_possible_path, mods)}'
                second_possible_path = f'{second_possible_path}.py'


            if possible_path not in self.attempted_paths:  # check if already visited

                # add to attempted visited paths:
                self.attempted_paths.add(possible_path)
                
                # check for aliases e.g import cv2 as cv
                # check either the first or the last name-e.g. import torch.nn as nn OR import folder.mymodule as module
                if module_names[-1] in self.names or module_names[0] in self.names:
                    if imp.asname is not None:
                        self.names.add(imp.asname)
                        
                try:
                    print(f'[DEBUG] Trying to open {possible_path}...')
                    with open(possible_path) as new_file:
                        print(f'[DEBUG] {module_names[-1]} found! Starting analysis...')
                        tree = ast.parse(new_file.read())
                        if len(module_names) == 1:
                            self.visit(tree)
                        else:
                            self.update_folder_and_visit(tree, module_names)
    
                        print(f'[DEBUG] Successfully analysed {possible_path}!')
                except FileNotFoundError:
                    # TODO: try PYTHONPATH, try path from root directory
                    if second_possible_path != self.current_path:
                        try:
                            self.attempted_paths.add(second_possible_path)
                            print(f'[DEBUG] Trying to open {second_possible_path}...')
                            with open(second_possible_path) as new_file:
                                print(f'[DEBUG] {module_names[-1]} found! Starting analysis...')
                                tree = ast.parse(new_file.read())
                                if len(module_names) == 1:
                                    self.visit(tree)
                                else:
                                    self.update_folder_and_visit(tree, module_names)
                                print(f'[DEBUG] Successfully analysed {possible_path}!')
                        except FileNotFoundError:
                            pass
                    # print(f'[WARNING] Could not open {import_file_name}')
                finally:
                    self.generic_visit(node)
            else:
                self.generic_visit(node)

    # PROBLEM with this is that we can import anything from the target name:
    # from folder import module # need to import module
    #   need to check two things:
    #   1. check path with current_folder
    #   2. check path without current_folder
    # from module import function (or global var?) # need to import module #TODO: visit only the function!
    #   need to check two things:
    #   1. check path with current_folder
    #   2. check path without current_folder
    # TODO: there is probably a better way to do this with actually importing the module...
    def visit_ImportFrom(self, node):

        if node.module is not None:
            module_names = node.module.split('.')
        else:
            module_names = [node.names[0].name]  # e.g. from . import somemodule

        # it's possible we are already in the import folder importing other things
        if len(self.current_folder) > 0 and self.current_folder[0] == module_names[0]:
            del module_names[0]

        possible_path = self.current_path
        for folder in self.current_folder:
            possible_path = f'{os.path.join(possible_path, folder)}'
        for mods in module_names:
            possible_path = f'{os.path.join(possible_path, mods)}'

        # from 1 import 2
        possible_path_1 = f'{possible_path}.py'
        possible_path_2 = f'{os.path.join(possible_path, node.names[0].name)}.py'

        # sometimes imports reference project root dir instead of local folder
        possible_path_1_no_folder = self.current_path
        possible_path_2_no_folder = self.current_path
        if len(self.current_folder) > 0:
            for mods in module_names:
                possible_path_1_no_folder = f'{os.path.join(possible_path_1_no_folder, mods)}'
            possible_path_2_no_folder = f'{os.path.join(possible_path_1_no_folder, node.names[0].name)}.py'
            possible_path_1_no_folder = f'{possible_path_1_no_folder}.py'

        if possible_path_1 not in self.attempted_paths:  # check if already visited

            self.attempted_paths.add(possible_path_1) # add to attempted
            # check for aliases e.g import cv2 as cv
            if module_names[-1] in self.names:
                if node.names[0].asname is not None:
                    self.names.add(node.names[0].asname)

            """
            # Don't need this, since get_import_file_path() takes care of current_folder
            # check if import is in current directory:
            this_path = self.current_path
            if node.level == 1 and len(self.current_folder) != 0:  # just one for now; this does not work with function analyzer
                this_path = os.path.join(self.current_path, self.current_folder[0])  # add current folder to path
            """
            try:
                print(f'[DEBUG] Trying to open {possible_path_1}...')
                with open(possible_path_1) as new_file:
                    print(f'[DEBUG] File found! Starting analysis...')
                    tree = ast.parse(new_file.read())
                    if len(module_names) == 1:
                        self.visit(tree)
                    else:
                        self.update_folder_and_visit(tree, module_names)
                    print(f'[DEBUG] Successfully analysed {possible_path_1}!')
            except FileNotFoundError:
                # print(f'[WARNING] Could not find {module_names[0]}.py!')
                # TODO: also try PYTHONPATH
                if possible_path_2 not in self.attempted_paths:
                    try:
                        self.attempted_paths.add(possible_path_2)
                        print(f'[DEBUG] Trying to open {possible_path_2}...')
                        with open(possible_path_2) as new_file:
                            print(f'[DEBUG] File found! Starting analysis...')
                            tree = ast.parse(new_file.read())
                            if len(module_names) == 1:
                                self.visit(tree)
                            else:
                                self.update_folder_and_visit(tree, module_names)
                            print(f'[DEBUG] Successfully analysed {possible_path_2}!')
                    except FileNotFoundError:
                        if possible_path_1_no_folder != self.current_path and possible_path_1_no_folder not in self.attempted_paths:
                            try:
                                self.attempted_paths.add(possible_path_1_no_folder)
                                print(f'[DEBUG] Trying to open {possible_path_1_no_folder}...')
                                with open(possible_path_1_no_folder) as new_file:
                                    print(f'[DEBUG] File found! Starting analysis...')
                                    tree = ast.parse(new_file.read())
                                    if len(module_names) == 1:
                                        self.visit(tree)
                                    else:
                                        self.update_folder_and_visit(tree, module_names)
                                    print(f'[DEBUG] Successfully analysed {possible_path_1_no_folder}!')
                            except FileNotFoundError:
                                if possible_path_2_no_folder not in self.attempted_paths:
                                    try:
                                        self.attempted_paths.add(possible_path_2_no_folder)
                                        print(f'[DEBUG] Trying to open {possible_path_2_no_folder}...')
                                        with open(possible_path_2_no_folder) as new_file:
                                            print(f'[DEBUG] File found! Starting analysis...')
                                            tree = ast.parse(new_file.read())
                                            if len(module_names) == 1:
                                                self.visit(tree)
                                            else:
                                                self.update_folder_and_visit(tree, module_names)
                                            print(f'[DEBUG] Successfully analysed {possible_path_2_no_folder}!')
                                    except FileNotFoundError:
                                        pass
            finally:
                self.generic_visit(node)
        else:
            self.generic_visit(node)

    def report(self):
        print(f'names: {self.names}')

        stats_keys = sorted(self.stats.keys(), key=lambda n: n.split('.')[-1].lower())

        #for stat in sorted(self.stats):
        #    print(f'{stat}; {self.stats[stat]}; count={len(self.stats[stat])}')
        prev = ''
        for key in stats_keys:
            local_key = key.split('.')[-1].lower()
            if local_key != prev:
                print()
            print(f'{key}; {self.stats[key]}; count={len(self.stats[key])}')
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
    def __init__(self, function_name, names=set(SEED)):  # set(['caffe'])):
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
        self.stats = SEED  # ['caffe']  # TODO: change this list to set

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
