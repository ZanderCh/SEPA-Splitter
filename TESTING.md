# Tests

```
python -m pytest -v                          # Kern- und GUI-Tests
python -m unittest discover -s tests -v     # nur Kerntests (test_core.py)
```
Abgedeckt (`tests/test_core.py`, ~50 Tests): Verteilungstabelle (1…3000), Suffixe (a…z, aa…), beide pain-Versionen,
LF/CRLF, Präfix/Default-Namespace, Tab-/Leer-Einrückung, Kommentare, bytegleiche Transaktionsblöcke, CtrlSum-Nachkommastellen,
fehlende optionale Felder, mehrere PmtInf mit verschiedenen Fälligkeiten/Sequenztypen, ID-Kürzung/Kollisionen, >26 Dateien,
große Datei (10.000 Tx), Manipulationserkennung des Verifiers, Scanner (`>` in Attributen, CDATA), Fehlerfälle
(ungültiges XML, unbekannte Version, falsche Summen, DOCTYPE/XXE, UTF-16, vorhandene Ausgabedateien, fehlende Schreibrechte,
Schreibfehler mit Rollback, geändertes Original), INI (fehlend/defekt/ungültig/gesperrt), Startordner/NameScheme, Protokoll ohne IBAN.

Oberfläche (`tests/test_gui.py`, pytest-qt, läuft offscreen ohne Bildschirm): Dateidialog (Startordner BasePath/JJJJ/Qn,
XML-Filter vorausgewählt, Ersatzordner-Hinweis), Prüfung im Hintergrund-Thread, Vorschau, Bestätigung (Ja/Nein), Fortschritt,
Ergebnis, kein zweites Aufteilen ohne neue Prüfung, „Ausgabeordner öffnen“, „Protokoll anzeigen“, Fehlerfall.
Die Dialoge werden dabei durch Aufzeichner ersetzt. Weiterhin manuell: Drag&Drop, echte native Dialoge, Vergleich mit Meld/WinMerge. Synthetische Dateien: `samples/` bzw. `sepa_splitter/samplegen.py`.
