# Tests

```
python -m unittest discover -s tests -v     # oder: pytest
```
Abgedeckt (`tests/test_core.py`, ~50 Tests): Verteilungstabelle (1…3000), Suffixe (a…z, aa…), beide pain-Versionen,
LF/CRLF, Präfix/Default-Namespace, Tab-/Leer-Einrückung, Kommentare, bytegleiche Transaktionsblöcke, CtrlSum-Nachkommastellen,
fehlende optionale Felder, mehrere PmtInf mit verschiedenen Fälligkeiten/Sequenztypen, ID-Kürzung/Kollisionen, >26 Dateien,
große Datei (10.000 Tx), Manipulationserkennung des Verifiers, Scanner (`>` in Attributen, CDATA), Fehlerfälle
(ungültiges XML, unbekannte Version, falsche Summen, DOCTYPE/XXE, UTF-16, vorhandene Ausgabedateien, fehlende Schreibrechte,
Schreibfehler mit Rollback, geändertes Original), INI (fehlend/defekt/ungültig/gesperrt), Startordner/NameScheme, Protokoll ohne IBAN.

Nicht automatisiert getestet: die PySide6-Oberfläche selbst (Drag&Drop, Dialoge) – manuelle Checkliste:
Datei wählen (Dialog startet in BasePath/JJJJ/Qn, XML-Filter aktiv), Vorschau, Bestätigung, Fortschritt, „Ausgabeordner öffnen“,
„Protokoll anzeigen“, Vergleich mit Meld/WinMerge. Synthetische Dateien: `samples/` bzw. `sepa_splitter/samplegen.py`.
