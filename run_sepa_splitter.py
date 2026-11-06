#!/usr/bin/env python3
"""Startskript (Einstiegspunkt für PyInstaller/Nuitka und Quellcode-Betrieb)."""
import os
import sys


def _ensure_console_streams() -> None:
    """Fensteranwendungen (PyInstaller --windowed unter Windows) haben kein stdout/stderr.
    Für --cli an die Konsole des Aufrufers anhängen, sonst Ausgaben verwerfen statt abzustürzen."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = None
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):      # ATTACH_PARENT_PROCESS
                stream = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except (OSError, AttributeError):
            stream = None
    if stream is None:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


if "--cli" in sys.argv:
    sys.argv.remove("--cli")
    _ensure_console_streams()
    from sepa_splitter.cli import main
    sys.exit(main())
from sepa_splitter.gui import run
sys.exit(run())
