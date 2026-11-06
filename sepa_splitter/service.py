"""Verarbeitungsablauf: Prüfen, Planen, Schreiben (temporär), Verifizieren, Bereitstellen."""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, List, Optional

from . import analyzer, splitter, verifier
from .config import Config
from .errors import FidelityError, InputError, OutputError, ValidationError
from .protocol import Protocol

Progress = Optional[Callable[[int, str], None]]


@dataclass
class CheckResult:
    doc: analyzer.SepaDocument
    plans: List[splitter.PartPlan]
    names: List[Path]
    sha256: str

    @property
    def split_needed(self) -> bool:
        return bool(self.plans)


@dataclass
class SplitResult:
    files: List[Path]
    structure_ok: bool
    fidelity_ok: bool
    messages: List[str] = field(default_factory=list)
    changes: List[str] = field(default_factory=list)


def output_names(src: Path, count: int, cfg: Config) -> List[Path]:
    names = []
    for i in range(count):
        suf = splitter.letter_suffix(i) if cfg.suffix_mode == "letters" else splitter.number_suffix(i, count)
        names.append(src.with_name(f"{src.stem}{cfg.filename_separator}{suf}{src.suffix}"))
    return names


def check_file(path: Path, cfg: Config, protocol: Protocol, progress: Progress = None) -> CheckResult:
    path = Path(path).expanduser()
    protocol.attach_directory(path.resolve().parent)
    protocol.log("INFO", f"Prüfe Datei „{path.name}“")
    if progress:
        progress(5, "Datei wird gelesen und geprüft …")
    try:
        doc = analyzer.analyze(path, True)
    except Exception as e:
        protocol.log("ERROR", f"Prüfung fehlgeschlagen: {str(e).splitlines()[0] if str(e) else type(e).__name__}")
        raise
    protocol.log("INFO", f"pain-Version: {doc.version}; Transaktionen: {doc.total_tx}; "
                         f"PmtInf-Blöcke: {len(doc.pmtinfs)}")
    for i in doc.issues:
        protocol.log("ERROR" if i.level == "error" else "WARNING", i.text)
    plans: List[splitter.PartPlan] = []
    names: List[Path] = []
    if doc.ok:
        plans = splitter.make_plan(doc, cfg.max_transactions, cfg.suffix_mode)
        names = output_names(path.resolve(), len(plans), cfg) if plans else []
        protocol.log("INFO", f"Aufteilung nötig: {'ja' if plans else 'nein'}; geplante Ausgabedateien: {len(plans)}")
    if progress:
        progress(100, "Prüfung abgeschlossen.")
    return CheckResult(doc, plans, names, hashlib.sha256(doc.data).hexdigest())


def split_file(chk: CheckResult, cfg: Config, protocol: Protocol,
               overwrite_decider: Optional[Callable[[List[Path]], bool]] = None,
               progress: Progress = None) -> SplitResult:
    doc = chk.doc
    if not doc.ok:
        raise ValidationError("Die Datei hat Prüffehler und wird nicht aufgeteilt (keine stillschweigende Korrektur).")
    if not chk.plans:
        raise ValidationError("Eine Aufteilung ist nicht erforderlich.")
    src = doc.path.resolve()
    outdir = src.parent
    if not os.access(outdir, os.W_OK):
        raise OutputError(f"Im Ordner „{outdir}“ fehlen die Schreibrechte.")
    # Original darf sich seit der Prüfung nicht geändert haben.
    if hashlib.sha256(analyzer.read_file(src)).hexdigest() != chk.sha256:
        raise InputError("Die Originaldatei wurde seit der Prüfung verändert. Bitte erneut prüfen.")
    existing = [p for p in chk.names if p.exists()]
    if src in chk.names:
        raise OutputError("Interner Schutz: Ausgabename entspricht der Originaldatei.")
    if existing:
        names = ", ".join(p.name for p in existing[:5]) + (" …" if len(existing) > 5 else "")
        if cfg.overwrite_mode == "abort":
            raise OutputError(f"Ausgabedateien existieren bereits ({names}). Es wurde nichts geschrieben.")
        if cfg.overwrite_mode == "ask" and not (overwrite_decider and overwrite_decider(existing)):
            raise OutputError(f"Ausgabedateien existieren bereits ({names}). Es wurde nichts geschrieben.")

    temps: List[Path] = []
    backups: List[tuple] = []
    finals: List[Path] = []
    try:
        blobs: List[bytes] = []
        n = len(chk.plans)
        for i, plan in enumerate(chk.plans):
            if progress:
                progress(int(5 + 40 * i / n), f"Erzeuge Teildatei {i + 1} von {n} …")
            blobs.append(splitter.build_part(doc, plan))
        for i, blob in enumerate(blobs):
            if progress:
                progress(int(45 + 15 * i / n), f"Schreibe temporäre Datei {i + 1} von {n} …")
            fd, tmp = tempfile.mkstemp(prefix=".sepa-splitter-", suffix=".tmp", dir=outdir)
            temps.append(Path(tmp))
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(blob)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                raise OutputError(f"Schreibfehler: {e.strerror or e}") from e
        # 1) SEPA-Strukturprüfung der erzeugten Dateien
        structure_ok, messages = True, []
        for i, tmp in enumerate(temps):
            if progress:
                progress(int(60 + 20 * i / n), f"Prüfe Struktur von Teildatei {i + 1} von {n} …")
            try:
                d2 = analyzer.analyze(tmp, True)
            except Exception as e:
                structure_ok = False
                messages.append(f"{chk.names[i].name}: {str(e).splitlines()[0]}")
                continue
            if not d2.ok or d2.version != doc.version or d2.total_tx > cfg.max_transactions:
                structure_ok = False
                messages += [f"{chk.names[i].name}: {x.text}" for x in d2.errors]
        # 2) Unabhängige Originaltreue-Prüfung
        if progress:
            progress(85, "Originaltreue-Prüfung …")
        vr = verifier.verify(doc.data, blobs, cfg.max_transactions)
        for tmp, blob in zip(temps, blobs):
            if tmp.read_bytes() != blob:
                vr.fail("Geschriebene Datei weicht vom erzeugten Inhalt ab.")
        messages += vr.messages
        structure_ok = structure_ok and vr.structure_ok
        protocol.log("INFO" if structure_ok else "ERROR", f"XML-/Strukturprüfung: {'erfolgreich' if structure_ok else 'FEHLER'}")
        protocol.log("INFO" if vr.fidelity_ok else "ERROR", f"Originaltreue-Prüfung: {'erfolgreich' if vr.fidelity_ok else 'FEHLER'}")
        if not (structure_ok and vr.fidelity_ok):
            for m in messages:
                protocol.log("ERROR", m)
            raise FidelityError("Die Prüfung der erzeugten Dateien ist fehlgeschlagen; es wurden keine Ausgabedateien "
                                "bereitgestellt.\n" + "\n".join(f"• {m}" for m in messages[:10]))
        # 3) Bereitstellen (mit Rollback)
        if progress:
            progress(92, "Dateien werden bereitgestellt …")
        for tmp, final in zip(temps, chk.names):
            if final.exists():
                bak = final.with_name(f".{final.name}.bak-{os.getpid()}")
                os.replace(final, bak)
                backups.append((final, bak))
            os.replace(tmp, final)
            finals.append(final)
        for _, bak in backups:
            try:
                bak.unlink()
            except OSError:
                pass
        if progress:
            progress(100, "Fertig.")
        protocol.log("INFO", f"Aufteilung erfolgreich: {len(finals)} Dateien ({', '.join(str(p.count) for p in chk.plans)} Transaktionen)")
        return SplitResult(finals, structure_ok, vr.fidelity_ok, messages, vr.changes)
    except Exception as e:
        for f in finals:
            try:
                f.unlink()
            except OSError:
                pass
        for final, bak in backups:
            try:
                os.replace(bak, final)
            except OSError:
                pass
        protocol.log("ERROR", f"Verarbeitung abgebrochen: {str(e).splitlines()[0] if str(e) else type(e).__name__}")
        if isinstance(e, (InputError, OutputError, ValidationError, FidelityError)):
            raise
        raise OutputError(f"Die Verarbeitung wurde abgebrochen: {e}") from e
    finally:
        for t in temps:
            try:
                if t.exists():
                    t.unlink()
            except OSError:
                pass
