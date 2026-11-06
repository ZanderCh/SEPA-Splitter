# Build

Gebaut wird **auf dem jeweiligen Zielsystem** (PyInstaller kann nicht kreuz-kompilieren):

| Ziel | Befehl |
|---|---|
| Windows x64 | `powershell -File build\build_windows.ps1` |
| Linux x86_64 / aarch64 | `build/build_unix.sh` (je Architektur auf passender Maschine) |
| macOS arm64 und x86_64 | `build/build_unix.sh` auf Apple-Silicon- bzw. Intel-Mac (oder universal2-Python für ein Universal-Binary) |

Die Skripte führen zuerst alle Tests aus, bauen mit PyInstaller (`--windowed`, onedir) und legen INI und `schemas/`
neben die Anwendung. Der Quellcode ist auf allen Plattformen identisch; plattformspezifisch ist nur Paketierung.

**Status:** Die Skripte wurden in der Entwicklungsumgebung nicht ausgeführt (kein PyInstaller/Netz, nur ein Linux-System);
sie sind ungetestet und müssen auf jedem Zielsystem einmal durchlaufen. Nuitka ist als Alternative möglich
(`python -m nuitka --standalone --enable-plugin=pyside6 run_sepa_splitter.py`).

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
