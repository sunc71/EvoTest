import ast
import json
import sys
import os
import re

# 1. Utility functions

def clean_code(text):
    if not isinstance(text, str): return ""
    def repl(m): return "\n" * m.group(0).count("\n")
    return re.sub(r"\[\s*\.\.\..*?omitted.*?\]", repl, text, flags=re.DOTALL | re.IGNORECASE)

def get_lines_in_node(node):
    lines = set()
    for child in ast.walk(node):
        if hasattr(child, "lineno"):
            if hasattr(child, "end_lineno"):
                lines.update(range(child.lineno, child.end_lineno + 1))
            else:
                lines.add(child.lineno)
    return lines

def get_source_segment(source_lines, node):
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"): return ""
    return "\n".join(source_lines[node.lineno - 1: node.end_lineno])

def wrap_as_module(stmts):
    if sys.version_info >= (3, 8):
        return ast.Module(body=stmts, type_ignores=[])
    return ast.Module(body=stmts)

def extract_member_vars(node):
    vars_ = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
            if child.value.id == "self":
                vars_.add(f"self.{child.attr}")
    return sorted(list(vars_))

# 2. Difficulty Model: AST Nesting Level

def calculate_nesting_level(depth):
    """Return AST nesting depth of node."""
    return depth


def calculate_difficulty(node_type, depth, condition_node=None, exc_name=None):
    """
    Static exploration difficulty based on AST nesting depth.
    D(n) = NL(n)

    NL(n) = Nesting Level (structural depth)
    """
    return calculate_nesting_level(depth)

# 3. AST semantic analysis

class SemanticAnalyzer:
    def __init__(self, source_code, missing_lines):
        self.source_code = clean_code(source_code)
        self.source_lines = self.source_code.splitlines()
        self.missing_lines = set(missing_lines)
        self.targets = []
        self.seen = set()

    def get_condition_text(self, node):
        target = node.test if hasattr(node, "test") else node
        seg = get_source_segment(self.source_lines, target)
        return seg.strip() if seg else ast.dump(target)

    def make_dedup_key(self, prefix_tuple, constraints):
        # Deterministic constraint key
        c_key = tuple((c["line"], c["expect"], c["type"]) for c in constraints)
        return prefix_tuple + c_key

    def add_target(self, key, payload):
        if key in self.seen: return
        self.seen.add(key)
        self.targets.append(payload)

    def has_direct_missed_lines(self, body_nodes):
        """
        Check if 'body_nodes' contain missed lines that are NOT claimed 
        by immediate child control structures.
        """
        block_lines = set()
        for node in body_nodes:
            block_lines.update(get_lines_in_node(node))
        
        sub_control_lines = set()
        for node in body_nodes:
            if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.FunctionDef, ast.ClassDef)):
                sub_control_lines.update(get_lines_in_node(node))
        
        direct_lines = block_lines - sub_control_lines
        return bool(direct_lines & self.missing_lines)

    def visit(self, node, depth=0, constraints=None, try_context=None):
        constraints = constraints or []

        # 1. Class / Function Definition
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Fallback Strategy:
            count_before = len(self.targets)
            
            new_depth = depth + 1
            for child in node.body:
                self.visit(child, new_depth, constraints, try_context)
            
            count_after = len(self.targets)
            
            # Only suggest calling if no internal targets found & def line missed
            if count_after == count_before and node.lineno in self.missing_lines:
                t_type = "class" if isinstance(node, ast.ClassDef) else "function"
                self.add_target(
                    (t_type, node.lineno),
                    {
                        "type": t_type,
                        "name": node.name,
                        "lines": f"{node.lineno}-{node.end_lineno}",
                        "difficulty": calculate_difficulty(t_type, depth),
                        "action": f"Call/Init `{node.name}` directly",
                        "context_variables": extract_member_vars(node),
                        "missed_lines": sorted(list(get_lines_in_node(node) & self.missing_lines))
                    }
                )
            return

        # 2. If / Elif
        elif isinstance(node, ast.If):
            self.visit(node.test, depth, constraints, try_context)
            cond_text = self.get_condition_text(node)
            
            c_true = {"code": cond_text, "expect": True, "line": node.lineno, "type": "if_condition"}
            c_false = {"code": cond_text, "expect": False, "line": node.lineno, "type": "if_condition"}

            if self.has_direct_missed_lines(node.body):
                key = self.make_dedup_key(("branch_true", node.lineno), constraints)
                self.add_target(key, {
                    "type": "branch_true",
                    "difficulty": calculate_difficulty("if", depth, node.test),
                    "action": f"Make `{cond_text}` == True",
                    "condition": cond_text,
                    "target_branch": True,
                    "path_constraints": constraints,
                    "context_variables": extract_member_vars(node),
                    "missed_lines": sorted(list(get_lines_in_node(wrap_as_module(node.body)) & self.missing_lines))
                })

            if node.orelse and self.has_direct_missed_lines(node.orelse):
                is_elif = len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)
                if not is_elif: # Pure Else
                    key = self.make_dedup_key(("branch_false", node.lineno), constraints)
                    self.add_target(key, {
                        "type": "branch_false",
                        "difficulty": calculate_difficulty("if", depth, node.test),
                        "action": f"Make `{cond_text}` == False",
                        "condition": cond_text,
                        "target_branch": False,
                        "path_constraints": constraints,
                        "context_variables": extract_member_vars(node),
                        "missed_lines": sorted(list(get_lines_in_node(wrap_as_module(node.orelse)) & self.missing_lines))
                    })

            for child in node.body:
                self.visit(child, depth + 1, constraints + [c_true], try_context)
            for child in node.orelse:
                self.visit(child, depth + 1, constraints + [c_false], try_context)
            return

        # 3. Loops
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            iter_node = node.iter if hasattr(node, "iter") else node.test
            self.visit(iter_node, depth, constraints, try_context)
            
            cond_text = self.get_condition_text(node)
            c_entry = {"code": cond_text, "expect": True, "line": node.lineno, "type": "loop_entry"}

            if self.has_direct_missed_lines(node.body):
                key = self.make_dedup_key(("loop", node.lineno), constraints)
                self.add_target(key, {
                    "type": "loop",
                    "difficulty": calculate_difficulty("loop", depth),
                    "action": "Ensure loop body executes (iterable not empty / condition true)",
                    "condition": cond_text,
                    "path_constraints": constraints,
                    "context_variables": extract_member_vars(node),
                    "missed_lines": sorted(list(get_lines_in_node(node) & self.missing_lines))
                })
            
            for child in node.body:
                self.visit(child, depth + 1, constraints + [c_entry], try_context)
            return

        # 4. Try / Except
        elif isinstance(node, ast.Try):
            current_try_code = get_source_segment(self.source_lines, wrap_as_module(node.body))
            for child in node.body:
                self.visit(child, depth + 1, constraints, current_try_code)
            for handler in node.handlers:
                self.visit(handler, depth + 1, constraints, current_try_code)
            for child in node.finalbody + node.orelse:
                self.visit(child, depth + 1, constraints, try_context)
            return

        elif isinstance(node, ast.ExceptHandler):
            if self.has_direct_missed_lines(node.body):
                exc_name = get_source_segment(self.source_lines, node.type) if node.type else "Exception"
                key = self.make_dedup_key(("except", node.lineno), constraints)
                self.add_target(key, {
                    "type": "exception",
                    "difficulty": calculate_difficulty("except", depth, exc_name=exc_name),
                    "action": f"Raise `{exc_name}` inside the Try block",
                    "exception_type": exc_name,
                    "try_block_sample": try_context[:200] + "..." if try_context and len(try_context) > 200 else try_context,
                    "path_constraints": constraints,
                    "context_variables": extract_member_vars(node),
                    "missed_lines": sorted(list(get_lines_in_node(wrap_as_module(node.body)) & self.missing_lines))
                })
            for child in node.body:
                self.visit(child, depth + 1, constraints, try_context)
            return

        for child in ast.iter_child_nodes(node):
            self.visit(child, depth, constraints, try_context)

    def analyze(self):
        try:
            tree = ast.parse(self.source_code)
            self.visit(tree)
            self.targets.sort(key=lambda x: (x.get("difficulty", 100), -len(x.get("missed_lines", []))))
        except Exception:
            pass
        return self.targets

# 4. Main flow and interface adaptation

def parse_missing_lines(entry, target_file=None):
    raw = str(entry)
    if isinstance(entry, dict):
        raw = entry.get("report", {}).get("coverage_output") or entry.get("coverage_output") or raw
    
    missed = set()
    target_base = os.path.basename(target_file) if target_file else None

    # Try JSON
    try:
        if raw.strip().startswith("{"):
            data = json.loads(raw)
            for fname, info in data.get("files", {}).items():
                if not target_file or target_base in fname or fname in target_file:
                    missed.update(info.get("missing_lines", []))
            return missed
    except: pass

    # Try Text
    for line in raw.splitlines():
        if target_base and target_base not in line: continue
        parts = line.split()
        try:
            idx = next(i for i, p in enumerate(parts) if "%" in p)
            if idx + 1 < len(parts):
                ranges = "".join(parts[idx + 1:]).split(",")
                for r in ranges:
                    if "-" in r:
                        s, e = map(int, r.split("-"))
                        missed.update(range(s, e + 1))
                    elif r.strip().isdigit():
                        missed.add(int(r))
        except: pass
    return missed

def generate_report(source, coverage_data, filename, mode="sorted"):
    """
    Main entry point for command line usage.
    mode: "sorted" (default) - sort by nesting depth (ascending)
          "random" - shuffle targets (for ablation)
    """
    missing_lines = parse_missing_lines(coverage_data, filename)
    if not missing_lines:
    # If target file never appears in report, treat as error
        if filename and os.path.basename(filename) not in str(coverage_data):
            return json.dumps({
                "status": "error",
                "message": "Target file not found in coverage report. Likely --include path mismatch. Use relative include patterns."
            }, indent=2)
        return json.dumps({"status":"success","message":"No missing lines detected."}, indent=2)

    analyzer = SemanticAnalyzer(source, missing_lines)
    targets = analyzer.analyze()

    if mode == "random":
        import random as _random
        _random.shuffle(targets)

    return json.dumps({
        "file": filename,
        "total_missing_lines": len(missing_lines),
        "suggested_targets": targets[:5]
    }, indent=2)

# Adapter for run_infer.py
def analyze_instance_coverage(code_src, test_result, target_file=None):
    """
    Adapter function to be imported by run_infer.py.
    Maps parameters to generate_report logic.
    """
    # run_infer passes 'test_result' which might be the full dictionary
    # generate_report's parse_missing_lines handles dicts with 'coverage_output' key
    return generate_report(code_src, test_result, target_file)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(0)
    target_file = sys.argv[1]
    
    # [Modify] Enhanced path resolution logic
    # 1. Try absolute path directly
    if os.path.exists(target_file):
        real_path = target_file
    else:
        # 2. Try removing /testbed prefix (common in swe-bench)
        stripped = target_file.replace("/testbed/", "")
        if os.path.exists(stripped):
            real_path = stripped
        # 3. Try prepending /testbed (if script runs in root but file is in /testbed)
        elif os.path.exists(f"/testbed/{target_file}"):
            real_path = f"/testbed/{target_file}"
        # 4. Try prepending /testbed + stripped
        elif os.path.exists(f"/testbed/{stripped}"):
            real_path = f"/testbed/{stripped}"
        # 5. Try /opt/ paths (for REB instances)
        elif os.path.exists(f"/opt/{target_file}"):
            real_path = f"/opt/{target_file}"
        elif os.path.exists(f"/opt/{stripped}"):
            real_path = f"/opt/{stripped}"
        else:
            # 6. Fallback: try to find the file in current directory recursively (risky but helpful)
            real_path = None
            
    if not real_path or not os.path.exists(real_path):
        # Print debugging info to stderr so it doesn't break JSON output but is visible in logs
        print(f"[DEBUG] CWD: {os.getcwd()}", file=sys.stderr)
        print(f"[DEBUG] Target: {target_file}", file=sys.stderr)
        print(f"[DEBUG] List /testbed: {os.listdir('/testbed') if os.path.exists('/testbed') else 'N/A'}", file=sys.stderr)
        print(json.dumps({"error": f"File not found: {target_file}"}))
        sys.exit(1)

    # Read stdin safely
    try:
        # Some environments might have issues with sys.stdin.read() blocking if no input
        # But here we expect input from pipe. 
        # We'll use a timeout-like approach or just read if not isatty.
        if not sys.stdin.isatty():
            cov_input = sys.stdin.read()
        else:
            cov_input = ""
    except Exception as e:
        print(json.dumps({"error": f"Failed to read stdin: {str(e)}"}))
        sys.exit(1)

    try:
        with open(real_path, "r", errors="replace") as f: src = f.read()
        mode = os.environ.get("DIFFICULTY_SORT", "sorted")
        print(generate_report(src, cov_input, target_file, mode=mode))
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": f"Analysis failed: {str(e)}"}))