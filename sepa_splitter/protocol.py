"""Lokales Protokoll. Enthält keine vollständigen IBANs, Namen oder Mandatsdaten."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

_IBAN = re.compile(r"\b([A-Z]{2}\d{2})[A-Z0-9 ]{8,30}\b")
LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40,
          "ERGEBNIS": 100}   # Ergebniszeilen (Datei, Teildateien, Summen): unabhängig von LogLevel immer


def format_amount(v: Decimal, ccy: str = "") -> str:
    """Betrag in deutscher Schreibweise, mindestens 2 Nachkommastellen, keine Rundung (z. B. 97.940,00 EUR)."""
    places = max(2, -v.as_tuple().exponent if v.as_tuple().exponent < 0 else 0)
    s = f"{v:,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {ccy}".strip()


def mask(text: str) -> str:
    return _IBAN.sub(lambda m: m.group(1) + "…", text)


class Protocol:
    """Sammelt Einträge im Speicher und schreibt sie, sobald ein Ordner bekannt ist
    (Ordner der bearbeiteten Datei)."""

    def __init__(self, enabled: bool = True, level: str = "INFO", filename: str = "SEPA-Splitter.log"):
        self.enabled, self.level, self.filename = enabled, LEVELS[level], filename
        self.lines: List[str] = []
        self._dir: Optional[Path] = None
        self._flushed = 0
        self.write_error: str = ""
        from . import __version__
        self.log("INFO", f"Programmstart (SEPA-Splitter {__version__})")

    def attach_directory(self, directory: Path) -> None:
        self._dir = Path(directory)
        self._flush()

    @property
    def path(self) -> Optional[Path]:
        return self._dir / self.filename if self._dir else None

    def log(self, level: str, text: str) -> None:
        if not self.enabled or LEVELS[level] < self.level:
            return
        self.lines.append(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{level}] {mask(text)}")
        self._flush()

    def _flush(self) -> None:
        if not (self.enabled and self._dir) or self._flushed >= len(self.lines):
            return
        try:
            with open(self._dir / self.filename, "a", encoding="utf-8") as f:
                f.write("\n".join(self.lines[self._flushed:]) + "\n")
            self._flushed = len(self.lines)
            self.write_error = ""
        except OSError as e:
            self.write_error = f"Das Protokoll kann nicht geschrieben werden: {e.strerror or e}"

    def text(self) -> str:
        return "\n".join(self.lines)
