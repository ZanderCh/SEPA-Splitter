# Konfiguration (`SEPA-Splitter.ini`)

Die Datei wird aus dem Verzeichnis der Anwendung geladen (nicht aus dem Arbeitsverzeichnis). Fehlt sie, wird eine
vollständig kommentierte Standarddatei angelegt (Werte, Beispiele, Defaults). Ungültige Werte werden gemeldet; es
gilt der Default. Die Standarddatei steht in `sepa_splitter/config.py` (`DEFAULT_INI`) und im Projektordner.

| Abschnitt/Schlüssel | Werte | Default |
|---|---|---|
| General/MaxTransactions | 10–99999 (Hinweis bei >999) | 999 |
| General/CheckOnLoad | true/false | true |
| General/ConfirmBeforeSplit | true/false (zusätzliche Abfrage; die Vorschau und der Klick auf „Datei aufteilen“ sind immer nötig) | true |
| Paths/BasePath | Pfad; leer = Benutzerordner; relativ = relativ zum Benutzerordner | leer |
| Paths/RememberLastDirectory | true/false | true |
| Paths/LastDirectoryOverridesBasePath | true/false | false |
| Paths/NameScheme | JJJJ/Qn, JJJJ/Mnn, JJ/Mnn, JJ/Qn, JJJJQn, JJQn … | JJJJ/Qn |
| Files/FilenameSeparator | 0–3 Zeichen | _ |
| Files/FilenameSuffixMode | letters, numbers | letters |
| Files/OverwriteMode | ask, abort, overwrite | ask |
| GUI/WindowWidth, WindowHeight | 640–4000, 480–3000 | 950, 680 |
| GUI/ShowPreview | true/false | true |
| Logging/Enabled, LogLevel, LogFile | true/false; ERROR, WARNING, INFO, DEBUG (siehe unten); Dateiname | true, INFO, SEPA-Splitter.log |

**Nicht einstellbar (fest im Programm):** Das Original wird nie verändert; Teildateien und Protokoll liegen immer im
Ordner der Originaldatei; alle Prüfungen und die Originaltreue-Prüfung laufen immer. Ältere INI-Dateien mit
`[Files] OutputDirectory`/`PreserveOriginal` oder einem Abschnitt `[SEPA]` funktionieren weiter: Die Einträge werden
ignoriert, ein Versuch, eine Regel abzuschalten (false bzw. anderer Ausgabeordner), wird beim Start gemeldet.

Der zuletzt verwendete Ordner wird in `SEPA-Splitter.state` neben der INI abgelegt. BasePath wirkt nur auf den Startordner
des Öffnen-Dialogs; Ausgabedateien und Protokoll liegen immer beim Original.
Filter des Dialogs: „SEPA-XML-Dateien (*.xml *.XML *.Xml)“ (vorausgewählt) und „Alle Dateien (*)“.

## Protokoll (`SEPA-Splitter.log` im Ordner der bearbeiteten Datei)

Jede Stufe enthält alles der vorherigen und zusätzlich:

| LogLevel | zusätzliche Einträge |
|---|---|
| ERROR | nur Fehler: Prüffehler der Datei, fehlgeschlagene Struktur-/Originaltreue-Prüfung, Abbrüche |
| WARNING | Hinweise: ungültige INI-Werte, nicht vorhandener Startordner |
| INFO | Ablauf: Programmstart mit Version, pain-Version, PmtInf-Blöcke, Zeilenumbruch/Kodierung, Aufteilung ja/nein, Prüfergebnisse |
| DEBUG | Details: INI-Pfad und wirksame Einstellungen, vollständiger Pfad, Größe und SHA-256 des Originals, je PmtInf-Block Kennung/Anzahl/Fälligkeit/Sequenztyp, je Teildatei Transaktionsbereich und neue MsgId/PmtInfId |

**Immer** (unabhängig vom LogLevel, Kennzeichnung `[ERGEBNIS]`): bearbeitete Datei mit Anzahl Transaktionen und
Gesamtsumme; nach dem Aufteilen jede erzeugte Datei mit Anzahl Transaktionen und Summe sowie die Summe aller
Teildateien mit Abgleich gegen das Original. Mit `Enabled = false` wird gar kein Protokoll geschrieben.
