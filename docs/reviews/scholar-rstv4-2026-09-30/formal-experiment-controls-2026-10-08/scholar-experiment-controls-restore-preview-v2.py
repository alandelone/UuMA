from pathlib import Path
import subprocess

prior = Path(__file__).with_name('scholar-experiment-controls-restore-preview-v1.py')
source = prior.read_text(encoding='utf-8').replace('preview-original-v1', 'preview-original-v2')
source = source.replace('preview-authority-v1', 'preview-authority-v2')
source = source.replace("$_.CommandLine -like '*scholar-", "$_.Name -eq 'python.exe' -and $_.CommandLine -like '*scholar-")
start = source.index('$frontMatches=@(')
end = source.index('\n', start)
source = source[:start] + "$frontMatches=@($all|Where-Object {$_.Name -eq 'node.exe' -and $_.CommandLine -like '*writing-studio*vinext*cli.js*start*--port 3000*'})" + source[end:]
source = source.replace('$matches', '$taskMatches')
try:
    exec(compile(source, str(prior), 'exec'))
except subprocess.CalledProcessError as error:
    with Path(__file__).with_suffix('.error.log').open('x', encoding='utf-8') as handle:
        handle.write(error.stderr or '')
    print(error.stderr or 'Preview guard failed before a verified change')
    raise SystemExit(error.returncode)
