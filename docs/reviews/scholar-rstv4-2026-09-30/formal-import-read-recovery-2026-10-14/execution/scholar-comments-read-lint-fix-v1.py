from pathlib import Path
p=Path(__file__).resolve().parents[2]/'writing-studio/components/studio-workspace.tsx'
b=p.read_bytes()
for old,new in [
    ('<p role="status">正在读取返修轮次与意见…</p>', '<output className="block">正在读取返修轮次与意见…</output>'),
    ('<p role="status">意见或轮次已保存；读取结果暂未确认。请重新读取，无需再次提交。</p>', '<output className="block">意见或轮次已保存；读取结果暂未确认。请重新读取，无需再次提交。</output>'),
]:
    assert b.count(old.encode())==1
    b=b.replace(old.encode(),new.encode())
p.write_bytes(b)
