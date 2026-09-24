#!/usr/bin/env python3
"""静态列出统计函数，并按代码结构提示需要人工检查的边界。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def function_hints(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    nodes = list(ast.walk(function))
    hints = []

    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len" for node in nodes):
        hints.append("检查空输入")
    if any(isinstance(node, ast.BinOp) and isinstance(node.op, (ast.FloorDiv, ast.Mod)) for node in nodes):
        hints.append("检查奇数、偶数和临界长度")
    if any(isinstance(node, ast.Subscript) for node in nodes):
        hints.append("检查索引范围和空容器")
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range" for node in nodes):
        hints.append("检查数量为 0、负数和超过输入长度")

    return hints or ["检查输入范围和返回值是否符合函数约定"]


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：python3 inspect_stats.py <Python 文件>", file=sys.stderr)
        return 2

    root = Path.cwd().resolve()
    target = (root / sys.argv[1]).resolve()
    if not target.is_relative_to(root) or target.suffix != ".py" or not target.is_file():
        print("目标必须是工作区内存在的 .py 文件。", file=sys.stderr)
        return 2

    try:
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        print(f"无法解析 {target.name}：{exc}", file=sys.stderr)
        return 1

    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not functions:
        print(f"{target.name} 中没有顶层函数。")
        return 0

    for function in functions:
        print(f"{function.name}（第 {function.lineno} 行）")
        for hint in function_hints(function):
            print(f"  - {hint}")

    print("\n以上是静态检查提示；请读取源码确认问题，不要把提示直接当成缺陷。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
