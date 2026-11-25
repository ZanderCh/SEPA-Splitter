# Installation

Es gibt zwei Varianten mit identischem Programm. Beide bringen alles mit (Python, Qt, lxml); eine separate
Python-Installation ist nicht nötig.

| | Portabel (`.zip`, `.tar.gz`) | Installiert (Setup, DMG, `.deb`, `.rpm`) |
|---|---|---|
| Ablage | beliebiger Ordner, z. B. USB-Stick | Programmordner des Systems |
| Einstellungen (`SEPA-Splitter.ini`) | neben der Anwendung | im Benutzerordner (siehe CONFIG.md) |
| Menüeintrag, Deinstallation | nein | ja |

Die Installer sind **nicht signiert** (keine kostenpflichtigen Zertifikate). Das Betriebssystem warnt deshalb beim ersten
Mal; das ist bei unsignierter Software normal. Bezugsquelle sind die GitHub-Releases des Projekts; dort steht `SHA256SUMS.txt` zum Prüfen der Dateien
(`sha256sum -c SHA256SUMS.txt --ignore-missing`).

## Installer

* **Windows 10/11 (x64):** `SEPA-Splitter-<Version>-Windows-x64-Setup.exe` starten. Erscheint „Der Computer wurde durch
  Windows geschützt“ (SmartScreen): **Weitere Informationen → Trotzdem ausführen**. Standard ist die Installation nur für
  den eigenen Benutzer ohne Administratorrechte (`%LOCALAPPDATA%\Programs\SEPA-Splitter`); im Dialog wählbar: für alle
  Benutzer (`C:\Program Files`). Stille Installation: `/VERYSILENT /CURRENTUSER` bzw. `/ALLUSERS`.
  Deinstallation über „Apps“ in den Einstellungen. Die Einstellungen in `%APPDATA%\SEPA-Splitter` bleiben erhalten.
* **macOS (Intel / Apple Silicon):** `SEPA-Splitter-<Version>-macOS-<arm64|x86_64>.dmg` öffnen und `SEPA-Splitter.app` auf
  „Programme“ ziehen. Die App ist nur ad hoc signiert und nicht notarisiert. Beim ersten Start meldet macOS, dass
  die App nicht geöffnet werden kann: **Systemeinstellungen → Datenschutz & Sicherheit → „Dennoch öffnen“** (bis macOS 14 auch
  Rechtsklick → „Öffnen“). Alternativ im Terminal: `xattr -dr com.apple.quarantine /Applications/SEPA-Splitter.app`.
  Deinstallation: App in den Papierkorb; Einstellungen liegen in `~/Library/Application Support/SEPA-Splitter`.
* **Linux Debian/Ubuntu (x86_64):** `sudo apt install ./sepa-splitter_<Version>-1_amd64.deb`
  (zieht die nötigen Qt-Systembibliotheken nach). Entfernen: `sudo apt remove sepa-splitter`.
* **Linux Fedora/openSUSE/RHEL (x86_64):** `sudo dnf install ./sepa-splitter-<Version>-1.x86_64.rpm` bzw.
  `sudo zypper install ./sepa-splitter-…rpm`. Entfernen: `sudo dnf remove sepa-splitter`.
* Linux allgemein: Programm unter `/opt/sepa-splitter`, Start über das Anwendungsmenü oder `sepa-splitter`
  (Kommandozeile: `sepa-splitter --cli DATEI`). Einstellungen in `~/.config/sepa-splitter`. Benötigt eine glibc mindestens
  in der Version des Build-Systems (Ubuntu 22.04: 2.35).

Administratoren können eine `SEPA-Splitter.ini` neben die installierte Anwendung legen; sie wird beim ersten Start
jedes Benutzers als Vorlage übernommen.

## Portable Pakete

Entpacken, Ordner beliebig ablegen. Die Datei `SEPA-Splitter.ini` muss **neben** der Anwendung liegen
(macOS: neben `SEPA-Splitter.app`). Fehlt sie, legt das Programm eine kommentierte Standarddatei an.
Eine separate Python-Installation ist nicht nötig.

* **Windows 10/11 (x64):** `SEPA-Splitter.exe` starten.
* **Linux (x86_64/aarch64):** `./SEPA-Splitter`. Benötigt glibc ≥ der Version des Build-Systems
  (Paket auf möglichst altem System bauen, z. B. Ubuntu 22.04 → glibc 2.35), X11 oder Wayland sowie
  `libxcb-cursor0` (Qt ≥ 6.5), `libegl1`, `libxkbcommon0`. Ausgabeordner öffnen nutzt `xdg-open`.
* **macOS (Intel / Apple Silicon):** `SEPA-Splitter.app` starten. Nicht signierte Apps: erster Start per
  Rechtsklick → „Öffnen“. Signierung/Notarisierung: BUILD.md.
