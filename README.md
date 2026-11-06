# SEPA-Splitter

Teilt SEPA-Lastschriftdateien (`pain.008.001.02`, `pain.008.001.08`) mit mehr als 999 Transaktionen
**originalgetreu** in möglichst gleich große Teildateien auf (Sparkasse-Weboberfläche: max. 999).

## Prinzip
* Die Originaldatei wird nie verändert. Teildateien liegen im selben Ordner (`name_a.xml`, `name_b.xml`, …).
* Es wird **nichts neu serialisiert**. Die Ausgabe entsteht aus den Originalbytes: nicht benötigte
  `DrctDbtTxInf`-/`PmtInf`-Blöcke werden samt vorangehendem Whitespace entfernt, ausschließlich
  `GrpHdr/NbOfTxs`, `GrpHdr/CtrlSum`, `PmtInf/NbOfTxs`, `PmtInf/CtrlSum`, `GrpHdr/MsgId`
  und `PmtInf/PmtInfId` werden ersetzt. Deklaration, Namespaces, Präfixe, Einrückung, LF/CRLF,
  Kommentare, Beträge/Datumsformate bleiben bytegleich.
* Aufteilung: `ceil(n / Max)` Dateien, Verteilung 667/667/666 usw.; Reihenfolge bleibt erhalten;
  ein PmtInf-Block darf auf mehrere Dateien verteilt werden, Metadaten bleiben unverändert.
* Ablauf: prüfen → Vorschau → Bestätigung → temporäre Dateien → SEPA-Strukturprüfung → **unabhängige
  Originaltreue-Prüfung** (`verifier.py`) → erst dann atomar bereitstellen (mit Rollback).
* Vollständig offline. Keine IBANs in Protokollen.

## Starten
```
pip install -r requirements.txt
python run_sepa_splitter.py              # Oberfläche
python run_sepa_splitter.py --cli DATEI  # Kommandozeile (--check = nur prüfen)
```
Weitere Dokumentation: INSTALL.md, BUILD.md, CONFIG.md, TESTING.md.

## Module
`xmlscan.py` (positionsgenauer Scanner) · `analyzer.py` (Prüfung/SEPA-Analyse) · `splitter.py`
(Planung + bytebewahrende Erzeugung) · `verifier.py` (unabhängige Prüfung) · `config.py` · `protocol.py`
· `paths.py` (Startordner) · `service.py` (Ablauf) · `gui.py` · `cli.py` · `samplegen.py` (synthetische Testdaten).

## Wichtige Grenzen (bitte lesen)
* **Keine XSD-Validierung.** Die Originale werden als wohlgeformt und bankseitig gültig vorausgesetzt. Geprüft werden
  Wohlgeformtheit, die eingebaute Strukturprüfung (Pflichtelemente, versionsspezifische BIC/BICFI-Regel), Anzahl-
  und Summenfelder sowie – entscheidend – die Originaltreue jeder Ausgabedatei gegenüber dem Original.
* Bankseitige Annahme durch die Sparkasse ist damit **nicht** garantiert.
* Unterstützt werden ASCII-kompatible Kodierungen (UTF-8 u. a.); UTF-16/32 und Dateien mit DOCTYPE werden abgelehnt.
