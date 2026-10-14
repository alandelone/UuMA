from pathlib import Path

repo = Path(__file__).resolve().parents[1]
note = '''

## 2026-10-08 执行环境来源字段澄清

新的实际 Windows 检查证明：清单按所选 PATH 解析到验证虚拟环境，但裸 python 的真实子进程落在 Anaconda；原断言失败后，清单和计划均改为固定绝对执行路径，原实际进程路径断言通过。Chrome 隔离实跑也确认执行 UuMA/.venv，而非控制服务的 RSTV4/.venv。

该实跑同时显示旧 python_version 字段取自控制服务 sys.version（3.11.4），不能冒充不同所选解释器的版本。新记录明确使用 observer_python_version／observer_executable／observer_platform，与所选 executable 和其固定摘要区分。不探测执行额外命令，不推断未记录的目标版本，不改写历史记录。原完整输出／输入／环境存在断言改为核验正确来源字段，并加强所选路径测试检查不再输出歧义字段；原保护条件保持。
'''
for name in ['stage-gates/03-execution-brief.md', 'repomemory/findings.md']:
    with (repo / name).open('a', encoding='utf-8') as h:
        h.write(note)
