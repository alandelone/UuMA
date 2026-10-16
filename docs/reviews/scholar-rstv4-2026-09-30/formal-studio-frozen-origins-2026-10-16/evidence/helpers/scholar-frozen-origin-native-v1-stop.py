from pathlib import Path
code = Path(__file__).with_name('scholar-studio-current-native-restart-v10-stop-owned.py').read_text(encoding='utf8')
old = "HERE=REPO/'.tmp/scholar-studio-current-native-restart-v10'"
assert code.count(old) == 1
exec(compile(code.replace(old,"HERE=REPO/'.tmp/scholar-frozen-origin-native-v1'"),__file__,'exec'))
