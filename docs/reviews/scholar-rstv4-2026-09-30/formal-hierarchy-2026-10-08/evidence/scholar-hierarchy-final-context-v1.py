from pathlib import Path
repo=Path(__file__).resolve().parents[1]
appendix='''

## 2026-10-08 hierarchy native observer and owned production refresh context

Each native operation claimed as individually durable must await the save boundary and have its own resulting revision/change record. Early rapid L2 edit/delete and tree delete/undo actions coalesced: base36 Undo returns the unsaved local intermediate edge text, not base35's earlier server edge. Preserve that mismatch and the failed observer assertion; do not claim those rapid actions as individually durable acceptance. Repeat with save boundaries: actual base39 EDIT,40 DELETE,41 UNDO and42 DELETE_TREE,43 UNDO,44 REDO,45 UNDO must compare exact complete documents. This is the author UI's local Undo history versus server revision distinction, not permission to weaken product assertions.

Owned Windows service queries must output UTF-8 and return only the known process trees. The command line can invoke bare "node"; verify Win32_Process.ExecutablePath ends in node.exe, exact verified process creation/command, known build root in command, exact listener ancestry and served old build bytes before stopping only that owned listener. A GBK decode failure and the old node.exe-in-argv assumption both failed before any stop/write. Preserve both. The final frontend display adjustment is a new source version; rerun build, native visible layout, configured TSC/type-aware checks and stable full acceptance against that final source.
'''
for path in [repo/'rules/scholar-native-acceptance.md',repo/'stage-gates/03-execution-brief.md']:
    before=path.read_text(encoding='utf-8')
    with path.open('a',encoding='utf-8') as h:h.write(appendix)
    assert path.read_text(encoding='utf-8').startswith(before)
print('PASS observer, UTF8 and actual executable ownership context appended without rewriting prior history')
