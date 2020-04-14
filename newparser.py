# NOTE: this script does not check for global variables!

import sys
import analyzer
import os
import ast


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f'[ERROR] Need to provide path for python project and python script!')
        exit(1)
    root = str(sys.argv[1])
    script = str(sys.argv[2])

    # check all python scripts for functions that return a cv2 object
    # NOTE: we don't do any static analysis on this step! we just get the relevant functions to track
    # TODO: do static analysis on functions and avoid doing it again in the future
    print(f'[INFO] Initiating function parser...')
    function_analyzer = analyzer.FunctionAnalyzer()

    for dirpath, subdir, files in os.walk(root):
        for file in files:
            cur_file = os.path.join(dirpath, file)
            print(f'[DEBUG]: checking file {cur_file}...')
            if file[-3:] == '.py':
                with open(cur_file, "r") as source:
                    tree = ast.parse(source.read())
                    function_analyzer.visit(tree)
                    print(f'[DEBUG]: finished checking file {file}!')
    function_analyzer.report()
    print(f'[INFO] function parser has finished!\n\n')

    # check main python script with detected functions of interest
    # now we do perform static analysis on my script and also on imports
    print(f'[INFO] Initiating script parser...')
    analyzer = analyzer.Analyzer(set(function_analyzer.stats))
    try:
        with open(script, "r") as file:
            filename = os.path.basename(script)
            print(f'[INFO]: inspecting file {script}...')
            tree = ast.parse(file.read())
            analyzer.pre_visit(tree, filename, root)
            print(f'[INFO]: finished checking file {script}!')
            analyzer.report()
    except FileNotFoundError:
        print(f'[ERROR] Could not open file {script}')

