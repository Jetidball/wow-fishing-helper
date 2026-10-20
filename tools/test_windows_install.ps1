$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('targeting-install-' + [guid]::NewGuid().ToString('N'))
$output = Join-Path $repo 'data\install-verification'
New-Item -ItemType Directory -Path $output -Force | Out-Null
py -3.12 -m venv $testRoot
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
$python = Join-Path $testRoot 'Scripts\python.exe'
& $python -m pip install -r (Join-Path $repo 'requirements-inference.txt') $repo
if ($LASTEXITCODE -ne 0) { throw 'clean install failed' }
& $python -m pip freeze | Out-File (Join-Path $output 'freeze.txt') -Encoding utf8
& $python (Join-Path $repo 'tools\install_smoke.py') (Join-Path $output 'result.json')
if ($LASTEXITCODE -ne 0) { throw 'installed GUI smoke failed' }
& (Join-Path $testRoot 'Scripts\targeting-task.exe') --help
if ($LASTEXITCODE -ne 0) { throw 'installed CLI failed' }
Write-Output "Verification saved in $output; isolated environment retained at $testRoot"
