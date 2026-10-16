from pathlib import Path
source=Path(__file__).with_name('scholar-studio-current-native-restart-v10-stop-owned.py').read_text(encoding='utf8')
old="HERE=REPO/'.tmp/scholar-studio-current-native-restart-v10'";assert source.count(old)==1
exec(compile(source.replace(old,"HERE=REPO/'.tmp/scholar-legacy-origins-native-v1'"),__file__,'exec'))
