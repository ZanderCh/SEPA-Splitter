# Baut das portable Paket für Windows 10/11 (x64). In PowerShell ausführen.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m venv .venv-build
& .\.venv-build\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests fehlgeschlagen" }
Remove-Item -Recurse -Force dist, build\work -ErrorAction SilentlyContinue
pyinstaller --noconfirm --clean --windowed --name SEPA-Splitter --workpath build\work --collect-submodules lxml run_sepa_splitter.py
$out = "dist\SEPA-Splitter-Windows"
New-Item -ItemType Directory -Force $out | Out-Null
Move-Item dist\SEPA-Splitter\* $out
Copy-Item SEPA-Splitter.ini $out
Copy-Item -Recurse schemas "$out\schemas"
Write-Host "Fertig: $out"
