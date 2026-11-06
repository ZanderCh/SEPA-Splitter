"""Erzeugt die Programm-Icons aus build/sepa-logo.png (einmalig, Ergebnis ist eingecheckt).

Benötigt Pillow:  pip install pillow ;  python build/make_icons.py
Das Logo (Querformat) wird zentriert auf eine transparente quadratische Fläche gesetzt.
  sepa_splitter/assets/icon.png   Fenster-Icon (alle Plattformen, 256 px)
  build/icon.ico                  Programmdatei Windows (16–256 px)
  build/icon.icns                 App-Bundle macOS (bis 512 px)
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
src = Image.open(ROOT / "build" / "sepa-logo.png").convert("RGBA")
side = max(src.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(src, ((side - src.width) // 2, (side - src.height) // 2), src)

square.resize((256, 256), Image.LANCZOS).save(ROOT / "sepa_splitter" / "assets" / "icon.png")
square.resize((256, 256), Image.LANCZOS).save(
    ROOT / "build" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
square.resize((512, 512), Image.LANCZOS).save(ROOT / "build" / "icon.icns")
print("Icons erzeugt.")
