"""Startskript (Einstiegspunkt für PyInstaller/Nuitka und Quellcode-Betrieb)."""
import sys

if "--cli" in sys.argv:
    sys.argv.remove("--cli")
    from sepa_splitter.cli import main
    sys.exit(main())
from sepa_splitter.gui import run
sys.exit(run())
