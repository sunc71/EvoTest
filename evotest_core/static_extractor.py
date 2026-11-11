import ast
import os
import sys

# Common standard library modules to filter out from "Internal Dependencies"
STD_LIB_MODULES = {
    'abc', 'argparse', 'ast', 'asyncio', 'base64', 'collections', 'contextlib', 'copy', 'csv', 
    'datetime', 'decimal', 'difflib', 'enum', 'functools', 'glob', 'gzip', 'hashlib', 'heapq', 
    'hmac', 'html', 'http', 'importlib', 'inspect', 'io', 'itertools', 'json', 'logging', 'math', 
    'multiprocessing', 'os', 'pathlib', 'pickle', 'platform', 'pprint', 'random', 're', 'shutil', 
    'signal', 'socket', 'sqlite3', 'ssl', 'stat', 'string', 'struct', 'subprocess', 'sys', 
    'tempfile', 'threading', 'time', 'timeit', 'traceback', 'typing', 'unittest', 'urllib', 
    'uuid', 'warnings', 'weakref', 'xml', 'yaml', 'zipfile', 'zlib'
}

class ImportCollector(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()

    def visit_Import(self, node):
        for alias in node.names:
            self._add_import(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self._add_import(node.module)
        self.generic_visit(node)

    def _add_import(self, module_name):
        if not module_name:
            return
        base_module = module_name.split('.')[0]
        if base_module not in STD_LIB_MODULES:
            self.imports.add(module_name)

class StructurePrinter(ast.NodeVisitor):
    def __init__(self):
        self.indent_level = 0
        self.current_function_exceptions = set()
    
    def indent(self):
        return "    " * self.indent_level

    def visit_ClassDef(self, node):
        print(f"{self.indent()}class {node.name}:")
        self.indent_level += 1
        
        docstring = ast.get_docstring(node)
        if docstring:
            first_line = docstring.strip().split('\n')[0]
            print(f"{self.indent()}# Docstring: {first_line}")
            
        self.generic_visit(node)
        self.indent_level -= 1
        print("")

    def visit_FunctionDef(self, node):
        self._process_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._process_function(node, is_async=True)

    def _process_function(self, node, is_async=False):
        previous_exceptions = self.current_function_exceptions
        self.current_function_exceptions = set()

        args_str = self._format_args(node.args)
        return_annotation = ""
        if node.returns:
            try:
                return_annotation = f" -> {ast.unparse(node.returns)}"
            except:
                pass
        
        async_prefix = "async " if is_async else ""
        print(f"{self.indent()}{async_prefix}def {node.name}({args_str}){return_annotation}:")
        
        self.indent_level += 1
        
        docstring = ast.get_docstring(node)
        if docstring:
            first_line = docstring.strip().split('\n')[0]
            print(f"{self.indent()}# Docstring: {first_line}")
        
        self.generic_visit(node)
        
        if self.current_function_exceptions:
            exceptions_str = ", ".join(sorted(self.current_function_exceptions))
            print(f"{self.indent()}# RAISES EXCEPTIONS: {exceptions_str}")
        
        self.indent_level -= 1
        self.current_function_exceptions = previous_exceptions

    def visit_Raise(self, node):
        if node.exc:
            try:
                if isinstance(node.exc, ast.Name):
                    self.current_function_exceptions.add(node.exc.id)
                elif isinstance(node.exc, ast.Call):
                    if isinstance(node.exc.func, ast.Name):
                        self.current_function_exceptions.add(node.exc.func.id)
                    elif isinstance(node.exc.func, ast.Attribute):
                        try:
                            self.current_function_exceptions.add(ast.unparse(node.exc.func))
                        except:
                            pass
            except:
                pass
        self.generic_visit(node)

    def _format_args(self, args):
        arg_list = []
        
        # Helper to format individual arg with default
        def format_arg(arg, default=None):
            arg_str = arg.arg
            if arg.annotation:
                try:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                except:
                    pass
            if default is not None:
                try:
                    arg_str += f" = {ast.unparse(default)}"
                except:
                    pass
            return arg_str

        # Positional args with defaults
        # defaults are for the last len(defaults) arguments
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        
        for i, arg in enumerate(args.args):
            default = None
            if num_defaults > 0:
                if i >= (num_args - num_defaults):
                     default = args.defaults[i - (num_args - num_defaults)]
            arg_list.append(format_arg(arg, default))
            
        if args.vararg:
            arg_list.append(f"*{format_arg(args.vararg)}")
            
        # Keyword-only args
        for i, arg in enumerate(args.kwonlyargs):
            default = args.kw_defaults[i] if i < len(args.kw_defaults) else None
            arg_list.append(format_arg(arg, default))
            
        if args.kwarg:
            arg_list.append(f"**{format_arg(args.kwarg)}")
            
        return ", ".join(arg_list)

def main():
    if len(sys.argv) < 2:
        print("Usage: python static_extractor.py <file_path>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        sys.exit(1)
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
            
        tree = ast.parse(source_code)
        
        print(f"=== STATIC ANALYSIS REPORT FOR: {os.path.basename(file_path)} ===")
        
        # 1. Collect Imports
        collector = ImportCollector()
        collector.visit(tree)
        
        if collector.imports:
            print("\n--- INTERNAL DEPENDENCIES ---")
            for imp in sorted(collector.imports):
                print(f"- {imp}")
            print("-----------------------------\n")
        
        # 2. Print Structure
        print("--- CODE STRUCTURE & SIGNATURES ---")
        printer = StructurePrinter()
        printer.visit(tree)
        
    except Exception as e:
        print(f"Error analyzing file: {e}")

if __name__ == "__main__":
    main()
