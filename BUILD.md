# Build

Gebaut wird **auf dem jeweiligen Zielsystem** (PyInstaller kann nicht kreuz-kompilieren):

| Ziel | Befehl |
|---|---|
| Windows x64 | `powershell -File build\build_windows.ps1` |
| Linux x86_64 / aarch64 | `build/build_unix.sh` (je Architektur auf passender Maschine) |
| macOS arm64 und x86_64 | `build/build_unix.sh` auf Apple-Silicon- bzw. Intel-Mac (oder universal2-Python für ein Universal-Binary) |

Die Skripte führen zuerst alle Tests aus, bauen mit PyInstaller (`--windowed`, onedir) und legen die INI
neben die Anwendung. Der Quellcode ist auf allen Plattformen identisch; plattformspezifisch ist nur Paketierung.

**Status:** `build_unix.sh` wurde unter Linux x86_64 (Ubuntu 24.04, Python 3.12) ausgeführt. Das Paket startet,
findet die INI neben der ausführbaren Datei (unabhängig vom Arbeitsverzeichnis, legt sie bei Bedarf an) und zeigt
die Oberfläche (xcb und offscreen). Windows und macOS werden über GitHub Actions gebaut
(`.github/workflows/build.yml`). Nuitka ist als Alternative möglich
(`python -m nuitka --standalone --enable-plugin=pyside6 run_sepa_splitter.py`).

## Installer
Aufsetzend auf dem portablen Build (zuerst das Build-Skript oben ausführen), jeweils auf dem Zielsystem:

| Ziel | Befehl | Werkzeug | Ergebnis in `dist/` |
|---|---|---|---|
| Windows | `powershell -File build\installer\build_windows_installer.ps1` | [Inno Setup 6.3+](https://jrsoftware.org/isinfo.php) (`choco install innosetup`) | `SEPA-Splitter-<V>-Windows-x64-Setup.exe` |
| macOS | `build/installer/build_macos_dmg.sh` | Bordmittel (`hdiutil`, `codesign`) | `SEPA-Splitter-<V>-macOS-<arch>.dmg` |
| Linux | `build/installer/build_linux_packages.sh` | `dpkg-deb`, `rpmbuild` (Ubuntu: `sudo apt install rpm`) | `sepa-splitter_<V>-1_amd64.deb`, `sepa-splitter-<V>-1.x86_64.rpm` |

Alle Installer legen die Markierung `build/installer/SEPA-Splitter.installed` neben das Programm (macOS: in
`Contents/Resources`) und lassen die INI weg; die installierte Anwendung legt ihre Einstellungen im Benutzerordner an
(CONFIG.md). Die Windows-`AppId` in `SEPA-Splitter.iss` nie ändern, sonst erkennt Windows Updates nicht als solche.
GitHub Actions baut alle Installer, installiert sie einmal testweise und stellt sie bei einem Tag `v<Version>` (muss
`__version__` entsprechen) zusammen mit der SBOM als GitHub-Release bereit.

### Signieren (optional)
Ohne Zertifikate entstehen unsignierte Installer (macOS: ad hoc signiert); Hinweise für Anwender in INSTALL.md.
Wer später Zertifikate hat, braucht nichts am Code zu ändern:

* **Windows:** `WINDOWS_SIGN_PFX` (Pfad) oder `WINDOWS_SIGN_PFX_BASE64` sowie `WINDOWS_SIGN_PASSWORD` setzen;
  signiert werden Programmdatei, Installer und Deinstallationsprogramm (signtool aus dem Windows SDK).
* **macOS:** `MACOS_SIGN_IDENTITY` („Developer ID Application: …“, im Schlüsselbund), für die Notarisierung zusätzlich
  `MACOS_NOTARY_APPLE_ID`, `MACOS_NOTARY_TEAM_ID`, `MACOS_NOTARY_PASSWORD`.
* **GitHub Actions:** dieselben Namen als Repository-Secrets; für macOS zusätzlich `MACOS_SIGN_P12_BASE64` und
  `MACOS_SIGN_P12_PASSWORD` (Zertifikat als .p12). Fehlende Secrets bedeuten: unsigniert.
* **Linux:** Pakete bleiben unsigniert (kostenlos mit eigenem GPG-Schlüssel möglich, sinnvoll erst mit eigenem Repository).

## macOS Signierung/Notarisierung
```
codesign --deep --force --options runtime --timestamp --sign "Developer ID Application: NAME (TEAMID)" SEPA-Splitter.app
ditto -c -k --keepParent SEPA-Splitter.app SEPA-Splitter.zip
xcrun notarytool submit SEPA-Splitter.zip --apple-id ID --team-id TEAMID --password APP-PASSWORT --wait
xcrun stapler staple SEPA-Splitter.app
```
Hinweis: Die INI liegt neben dem Bundle; ein Schreiben in ein notarisiertes/„translocated“ Bundle-Umfeld kann scheitern
(App in `/Programme` oder Benutzerordner verschieben).

## Linux
Auf dem ältesten unterstützten System bauen. Qt benötigt `libxcb-cursor0`; unter Wayland ggf. `QT_QPA_PLATFORM=xcb`.

## SBOM
`sbom.cdx.json` (CycloneDX 1.6) listet alle mitgelieferten Bestandteile (Python, PySide6/Qt, lxml mit libxml2/libxslt)
sowie die reinen Build-/Testwerkzeuge (`scope: excluded`). Nach Versionswechseln mit dem Python der Build-Umgebung neu
erzeugen: `.venv-build/bin/python build/make_sbom.py` (Windows: `.venv-build\Scripts\python build\make_sbom.py`).
