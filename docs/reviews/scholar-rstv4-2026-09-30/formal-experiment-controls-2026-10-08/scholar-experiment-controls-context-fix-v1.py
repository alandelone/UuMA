from pathlib import Path

repo = Path(__file__).resolve().parents[1]
path = repo.parent / 'RSTV4/src/rstv4/catalog_experiments.js'
source = path.read_text(encoding='utf-8')
marker = '<p>执行环境：${esc(c.python_executable)}</p>'
assert source.count(marker) == 1
source = source.replace(marker, '<label>Python 执行环境<input name="executable" value="${esc(d.executable || c.python_executable)}" required${dis}></label>')
path.write_text(source, encoding='utf-8')
note = '''

## 2026-10-08 实验工作台验证的执行上下文

UuMA 会话历史 22550 条、约 51 MB payload；多次 MemoryError 出现在全历史读取与进度投影，且曾有 PowerShell 内存分配失败。内部生命周期现在按最新事件检查，进度逐条读取；公共全历史接口、原日志、完整 handoff 内容与快照／摘要关闭门保持。7 项 session 检查及完整 440 项／5 个子检查通过。

Scholar 完整 v2：950 passed／1 failed／20 warnings，产品与测试摘要前后稳定。旧 `test_unknown_or_other_scope_parent_rolls_back_before_model` 的真实数据库字节保护失败，单项原断言复跑通过；失败根因尚未证实。只读拒绝阶段现在先 shutdown 该夹具的讨论写入，再冻结物理字节基线；原 404、逐字节不变与一次模型调用断言全部保持。按 rules/testing-contracts.md 明确执行上下文，继续窄范围及完整复验；不改写原失败为 PASS。

预检查还保留导入排序、独占 inline 文件名、原 Studio 预览连接拒绝、PowerShell 脚本策略及缺 psutil 的实际诊断。修正排序和独占后继命名；没有修改权限或安装额外库。仅已核实的新浏览器软件夹具监听进程停止，原数据库和原服务不据猜测清理。
'''
for relative in ['repomemory/findings.md', 'stage-gates/03-execution-brief.md']:
    with (repo / relative).open('a', encoding='utf-8') as h:
        h.write(note)
