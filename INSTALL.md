# Installation (portable Pakete)

Entpacken, Ordner beliebig ablegen. Die Datei `SEPA-Splitter.ini` muss **neben** der Anwendung liegen
(macOS: neben `SEPA-Splitter.app`). Fehlt sie, legt das Programm eine kommentierte Standarddatei an.
Eine separate Python-Installation ist nicht nötig.

* **Windows 10/11 (x64):** `SEPA-Splitter.exe` starten.
* **Linux (x86_64/aarch64):** `./SEPA-Splitter`. Benötigt glibc ≥ der Version des Build-Systems
  (Paket auf möglichst altem System bauen, z. B. Ubuntu 22.04 → glibc 2.35), X11 oder Wayland sowie
  `libxcb-cursor0` (Qt ≥ 6.5), `libegl1`, `libxkbcommon0`. Ausgabeordner öffnen nutzt `xdg-open`.
* **macOS (Intel / Apple Silicon):** `SEPA-Splitter.app` starten. Nicht signierte Apps: erster Start per
  Rechtsklick → „Öffnen“. Signierung/Notarisierung: BUILD.md.
