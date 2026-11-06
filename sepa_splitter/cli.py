"""Kommandozeile (für Automatisierung und Tests): python -m sepa_splitter --cli DATEI [--check]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .errors import SepaSplitterError
from .protocol import Protocol
from . import service


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="SEPA-Splitter --cli")
    ap.add_argument("datei")
    ap.add_argument("--check", action="store_true", help="nur prüfen, nichts schreiben")
    ap.add_argument("--ini", help="Pfad zur INI-Datei")
    ap.add_argument("--overwrite", action="store_true", help="vorhandene Ausgabedateien ersetzen")
    a = ap.parse_args(argv)
    cfg = load_config(Path(a.ini) if a.ini else None)
    for p in cfg.problems:
        print("Hinweis:", p, file=sys.stderr)
    proto = Protocol(cfg.log_enabled, cfg.log_level, cfg.log_file)
    for p in cfg.problems:
        proto.log("WARNING", p)
    service.log_settings(proto, cfg)
    try:
        chk = service.check_file(Path(a.datei), cfg, proto)
        d = chk.doc
        print(f"Version {d.version}, {d.total_tx} Transaktionen in {len(d.pmtinfs)} PmtInf, Summe {d.total_sum} {d.currency}")
        for i in d.issues:
            print(f"  [{i.level}] {i.text}")
        if not d.ok:
            return 2
        if not chk.split_needed:
            print(f"Keine Aufteilung nötig (Grenzwert {cfg.max_transactions}).")
            return 0
        for n, p in zip(chk.names, chk.plans):
            print(f"  {n.name}: {p.count} Transaktionen, {p.total} {d.currency}")
        if a.check:
            return 0
        res = service.split_file(chk, cfg, proto, overwrite_decider=lambda _: a.overwrite)
        print("SEPA-Strukturprüfung erfolgreich; Originaltreue erfolgreich geprüft.")
        for f in res.files:
            print("  geschrieben:", f)
        return 0
    except SepaSplitterError as e:
        print("FEHLER:", e, file=sys.stderr)
        return 1
