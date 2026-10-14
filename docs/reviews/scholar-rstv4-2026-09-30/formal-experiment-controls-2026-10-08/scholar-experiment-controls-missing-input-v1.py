from pathlib import Path

path = Path(__file__).resolve().parents[2] / 'RSTV4/src/rstv4/catalog_experiments.js'
source = path.read_text(encoding='utf-8')
marker = '<label>Python 执行环境'
assert source.count(marker) == 1
source = source.replace(marker, '${missingInputs}' + marker)
marker = "${choice('', d.script_path, '选择实际脚本')}"
assert source.count(marker) == 1
source = source.replace(marker, marker + '${unverifiedScript}')
path.write_text(source, encoding='utf-8')
