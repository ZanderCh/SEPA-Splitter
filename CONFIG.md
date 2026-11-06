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
| Files/OutputDirectory | same_as_source | same_as_source |
| Files/FilenameSeparator | 0–3 Zeichen | _ |
| Files/FilenameSuffixMode | letters, numbers | letters |
| Files/OverwriteMode | ask, abort, overwrite | ask |
| SEPA/* und Files/PreserveOriginal | **gesperrt**, müssen true bleiben (false wird gemeldet und ignoriert) | true |
| GUI/WindowWidth, WindowHeight | 640–4000, 480–3000 | 950, 680 |
| GUI/ShowPreview | true/false | true |
| Logging/Enabled, LogLevel, LogFile | true/false; DEBUG–ERROR; Dateiname | true, INFO, SEPA-Splitter.log |

Der zuletzt verwendete Ordner wird in `SEPA-Splitter.state` neben der INI abgelegt. BasePath wirkt nur auf den Startordner
des Öffnen-Dialogs; Ausgabedateien und Protokoll liegen immer beim Original.
Filter des Dialogs: „SEPA-XML-Dateien (*.xml *.XML *.Xml)“ (vorausgewählt) und „Alle Dateien (*)“.
