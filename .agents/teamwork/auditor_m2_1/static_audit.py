"""Static Analysis for Forensic Integrity Audit (M2)."""
import ast
import sys
from pathlib import Path

FILES = [
    Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_skeleton_views.py"),
    Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\src\rstv4\catalog_skeleton_themes.py"),
]

def analyze_ast(path):
    print(f"\n--- AST Analysis: {path.name} ---")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    
    # Check all function definitions
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check if body is just `pass`, `return <const>`, or `raise NotImplementedError`
            body = node.body
            if len(body) == 1:
                stmt = body[0]
                if isinstance(stmt, ast.Pass):
                    print(f"  [SUSPICIOUS] Empty function with pass: {node.name} at line {node.lineno}")
                elif isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant):
                    print(f"  [CHECK] Constant return: {node.name} returns {stmt.value.value} at line {node.lineno}")
                elif isinstance(stmt, ast.Raise) and isinstance(stmt.exc, ast.Call) and getattr(stmt.exc.func, 'id', None) == 'NotImplementedError':
                    print(f"  [SUSPICIOUS] NotImplementedError in: {node.name} at line {node.lineno}")
            
            # Check for hardcoded condition returns (e.g. `if paper_id == ... return ...`)
            for stmt in body:
                if isinstance(stmt, ast.If):
                    test = stmt.test
                    if isinstance(test, ast.Compare):
                        # check if comparing against literal strings
                        left = test.left
                        for comparator in test.comparators:
                            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                                if any(x in comparator.value for x in ["paper_", "skeleton_", "test", "fake", "mock"]):
                                    print(f"  [CHECK] Comparison with literal ID '{comparator.value}' in {node.name} at line {stmt.lineno}")

def grep_suspicious(path):
    print(f"\n--- Grep Patterns: {path.name} ---")
    lines = path.read_text(encoding="utf-8").splitlines()
    keywords = ["mock", "fake", "facade", "dummy", "bypass", "todo", "fixme", "synthetic", "hardcode"]
    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        for kw in keywords:
            if kw in line_lower and not line.strip().startswith("#"):
                print(f"  Line {i}: [{kw}] {line.strip()[:100]}")

if __name__ == "__main__":
    for f in FILES:
        analyze_ast(f)
        grep_suspicious(f)
