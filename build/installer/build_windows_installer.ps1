# Baut den Windows-Installer aus dem portablen Build (vorher build\build_windows.ps1 ausführen).
# Benötigt Inno Setup 6.3+ (https://jrsoftware.org/isinfo.php, kostenlos; z. B. "choco install innosetup").
#
# Signieren ist OPTIONAL. Ohne Zertifikat entsteht ein unsignierter Installer (SmartScreen-Hinweis, siehe INSTALL.md).
# Mit Zertifikat (Code-Signing, .pfx) vor dem Aufruf setzen:
#   $env:WINDOWS_SIGN_PFX          Pfad zur .pfx-Datei   (oder WINDOWS_SIGN_PFX_BASE64: Inhalt Base64-kodiert, für CI)
#   $env:WINDOWS_SIGN_PASSWORD     Kennwort der .pfx-Datei
#   $env:WINDOWS_SIGN_TIMESTAMP    optional, Zeitstempeldienst (Standard: http://timestamp.digicert.com)
# signtool.exe (Windows SDK) muss dann im PATH liegen oder gefunden werden.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

$version = (Select-String -Path sepa_splitter\__init__.py -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value
$source = (Resolve-Path "dist\SEPA-Splitter-Windows").Path
$outDir = (Resolve-Path "dist").Path

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
              "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) { throw "Inno Setup (ISCC.exe) nicht gefunden. Installation z. B.: choco install innosetup" }

$isccArgs = @("/DAppVersion=$version", "/DSourceDir=$source", "/DOutputDir=$outDir")

# ---- optionale Signatur
$pfx = $env:WINDOWS_SIGN_PFX
if (-not $pfx -and $env:WINDOWS_SIGN_PFX_BASE64) {
    $pfx = Join-Path $env:TEMP "sepa-splitter-sign.pfx"
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WINDOWS_SIGN_PFX_BASE64))
}
if ($pfx) {
    $signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
    if (-not $signtool) {
        $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $signtool) { throw "signtool.exe nicht gefunden (Windows SDK)." }
    $ts = if ($env:WINDOWS_SIGN_TIMESTAMP) { $env:WINDOWS_SIGN_TIMESTAMP } else { "http://timestamp.digicert.com" }
    Write-Host "Signiere SEPA-Splitter.exe ..."
    & $signtool sign /f $pfx /p $env:WINDOWS_SIGN_PASSWORD /fd sha256 /tr $ts /td sha256 "$source\SEPA-Splitter.exe"
    if ($LASTEXITCODE -ne 0) { throw "Signieren der Programmdatei fehlgeschlagen" }
    # Inno Setup signiert Installer und Deinstallationsprogramm selbst; $q = Anführungszeichen, $f = Datei
    $isccArgs += @("/DSign", "/Ssigntool=`$q$signtool`$q sign /f `$q$pfx`$q /p `$q$($env:WINDOWS_SIGN_PASSWORD)`$q /fd sha256 /tr $ts /td sha256 `$f")
} else {
    Write-Host "Kein Zertifikat angegeben: Installer wird nicht signiert."
}

& $iscc @isccArgs "build\installer\windows\SEPA-Splitter.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup fehlgeschlagen" }
if ($env:WINDOWS_SIGN_PFX_BASE64 -and $pfx) { Remove-Item $pfx -Force }
Write-Host "Fertig: dist\SEPA-Splitter-$version-Windows-x64-Setup.exe"
