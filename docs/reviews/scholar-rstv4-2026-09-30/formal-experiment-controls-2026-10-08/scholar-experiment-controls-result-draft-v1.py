from pathlib import Path

path = Path(__file__).resolve().parents[2] / 'RSTV4/src/rstv4/catalog_experiments.js'
source = path.read_text(encoding='utf-8')
marker = '<textarea name="statement" required${dis}></textarea>'
assert source.count(marker) == 1
source = source.replace(marker, '<textarea name="statement" required${dis}>${esc(d.results?.[r.run_id]?.statement || "")}</textarea>')
marker = "Object.keys(r.detail.metrics || {}).map(k => choice(k, '', k))"
assert source.count(marker) == 1
source = source.replace(marker, "Object.keys(r.detail.metrics || {}).map(k => choice(k, d.results?.[r.run_id]?.metric_key || '', k))")
path.write_text(source, encoding='utf-8')
