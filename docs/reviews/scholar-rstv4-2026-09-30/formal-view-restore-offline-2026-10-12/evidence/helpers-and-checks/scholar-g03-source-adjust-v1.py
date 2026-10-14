from pathlib import Path
import hashlib, json

p = Path('../writing-studio/components/studio-workspace.tsx')
s = p.read_text(encoding='utf-8')
start = s.index('    let cancelled = false;\n    const restoreSerial = ++sourceRestoreSerial.current;')
end = s.index('    try {\n      const raw = window.sessionStorage.getItem(historyKey);', start)
block = s[start:end]
s = s[:start] + s[end:]
needle = "  useEffect(() => {\n    try {\n      const saved = JSON.parse(window.localStorage.getItem(viewStateKey) || '{}');"
assert s.count(needle) == 1
s = s.replace(needle, "  useEffect(() => {\n" + block + "    try {\n      const saved = JSON.parse(window.localStorage.getItem(viewStateKey) || '{}');")
needle = '  const generatedContent = generatedVersion?.content || latestGeneratedContent(workspace);'
assert s.count(needle) == 1
s = s.replace(needle, "  const generatedContent = generatedVersion?.content || (readingVersionId ? '' : latestGeneratedContent(workspace));")
p.write_text(s, encoding='utf-8')
print(json.dumps({'file': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}))
