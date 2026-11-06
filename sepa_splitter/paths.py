"""Pfad-Hilfen: Anwendungsverzeichnis, Startordner des Öffnen-Dialogs."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional


def app_dir() -> Path:
    """Verzeichnis der ausführbaren Anwendung (NICHT das Arbeitsverzeichnis).

    - PyInstaller/Nuitka: Ordner der ausführbaren Datei; unter macOS der Ordner,
      der das .app-Bundle enthält (dort liegt die INI-Datei).
    - Quellcode-Betrieb: Projektwurzel (Elternordner des Pakets).
    """
    frozen = getattr(sys, "frozen", False) or "__compiled__" in globals()
    if frozen:
        exe = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            for parent in exe.parents:
                if parent.suffix == ".app":
                    return parent.parent
        return exe.parent
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- Startordner

_SCHEME_RE = None


def render_name_scheme(scheme: str, today: date) -> str:
    """Setzt ein Namensschema (z. B. ``JJJJ/Qn``) für das Datum ``today`` um.

    JJJJ = vierstelliges Jahr, JJ = zweistellig, Qn = Q1..Q4, Mnn = M01..M12.
    Trenner ``/`` oder ``\\`` werden in den plattformüblichen Trenner übersetzt.
    """
    out = scheme.strip()
    out = out.replace("JJJJ", f"{today.year:04d}")
    out = out.replace("JJ", f"{today.year % 100:02d}")
    quarter = (today.month - 1) // 3 + 1
    out = out.replace("Qn", f"Q{quarter}")
    out = out.replace("Mnn", f"M{today.month:02d}")
    out = out.replace("/", os.sep).replace("\\", os.sep)
    return out.strip(os.sep)


@dataclass
class StartDirResult:
    path: Path
    message: str = ""     # nicht leer, wenn ein Ersatzpfad verwendet wurde


def _usable(p: Path) -> bool:
    return p.is_dir() and os.access(p, os.R_OK | os.X_OK)


def resolve_base_path(base_path: str) -> Path:
    """Leer -> Benutzerverzeichnis; relativ -> relativ zum Benutzerverzeichnis."""
    home = Path.home()
    if not base_path.strip():
        return home
    p = Path(os.path.expanduser(base_path.strip()))
    if not p.is_absolute():
        p = home / p
    return p


def resolve_start_dir(base_path: str, name_scheme: str, today: date,
                      last_dir: Optional[str] = None, remember_last: bool = True,
                      last_overrides: bool = False) -> StartDirResult:
    """Ermittelt den Startordner des Öffnen-Dialogs (beeinflusst nie den Ausgabeort)."""
    if remember_last and last_overrides and last_dir and _usable(Path(last_dir)):
        return StartDirResult(Path(last_dir))
    base = resolve_base_path(base_path)
    target = base / render_name_scheme(name_scheme, today) if name_scheme.strip() else base
    if _usable(target):
        return StartDirResult(target)
    if _usable(base):
        return StartDirResult(
            base, f"Der Ordner „{target}“ existiert nicht oder ist nicht lesbar. "
                  f"Es wird stattdessen „{base}“ geöffnet.")
    home = Path.home()
    return StartDirResult(
        home, f"Der Basispfad „{base}“ existiert nicht oder ist nicht lesbar. "
              f"Es wird stattdessen das Benutzerverzeichnis „{home}“ geöffnet.")


def dialog_filters() -> "tuple[str, str]":
    """Dateifilter des Öffnen-Dialogs: (Filterliste, vorausgewählter Filter).
    Der XML-Filter steht an erster Stelle und ist immer vorausgewählt; Endungen
    werden unabhängig von Groß-/Kleinschreibung angeboten."""
    xml = "SEPA-XML-Dateien (*.xml *.XML *.Xml)"
    return f"{xml};;Alle Dateien (*)", xml
