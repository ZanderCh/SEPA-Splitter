"""Erzeugt die SBOM (Software Bill of Materials) im Format CycloneDX 1.6 (JSON).

Aufruf mit dem Python der Build-Umgebung, damit die tatsächlich gebauten Versionen erfasst werden:
    .venv-build/bin/python build/make_sbom.py            (Linux/macOS)
    .venv-build\\Scripts\\python build\\make_sbom.py      (Windows)
Ergebnis: sbom.cdx.json im Projektordner. Keine zusätzlichen Pakete nötig.

Erfasst werden:
  * Laufzeit (scope "required"): Bestandteile, die im portablen Paket mitgeliefert werden
    (Python-Interpreter, PySide6/Qt, lxml mit libxml2/libxslt).
  * Build/Test (scope "excluded"): Werkzeuge, die nur zum Bauen und Testen dienen und nicht ausgeliefert werden.
Nicht einzeln aufgeführt: Systembibliotheken, die PyInstaller unter Linux aus dem Build-System mitkopiert
(z. B. ICU, GLib, FreeType); sie hängen vom Build-Rechner ab.
"""
from __future__ import annotations

import json
import platform
import re
import sys
import uuid
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sepa_splitter import __version__  # noqa: E402

RUNTIME = ["PySide6", "PySide6_Essentials", "PySide6_Addons", "PySide6_Pdf", "PySide6_WebEngine",
           "shiboken6", "lxml"]
BUILD = ["pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "packaging", "setuptools",
         "pytest", "pytest-qt", "pluggy", "iniconfig", "Pygments", "typing_extensions", "pillow"]
# Pakete, die PySide6 zwar installiert, die das Programm aber nicht nutzt und PyInstaller nicht bündelt.
NOT_BUNDLED = {"PySide6_WebEngine"}
# Lizenzangaben, wo die Paket-Metadaten keinen SPDX-Ausdruck liefern.
LICENSE_FALLBACK = {
    "pyinstaller": "GPL-2.0-or-later WITH Bootloader-exception",
    "pyinstaller-hooks-contrib": "Apache-2.0 OR GPL-2.0-or-later",
    "pillow": "MIT-CMU",
}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def license_of(meta, name: str) -> list[dict]:
    expr = meta.get("License-Expression") or LICENSE_FALLBACK.get(norm(name)) \
        or LICENSE_FALLBACK.get(name.lower())
    if expr:
        return [{"expression": expr}]
    text = (meta.get("License") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9.+\-]+(?: (?:OR|AND|WITH) [A-Za-z0-9.+\-]+)*", text):
        return [{"expression": text}]  # Feld "License" enthält bereits einen SPDX-Ausdruck
    return [{"license": {"name": text.splitlines()[0][:200]}}] if text else []


def requires_of(dist) -> list[str]:
    out = []
    for req in dist.requires or []:
        if "extra ==" in req:
            continue
        m = re.match(r"\s*([A-Za-z0-9_.\-]+)", req)
        if m:
            out.append(norm(m.group(1)))
    return out


def pypi_component(name: str, scope: str) -> dict | None:
    try:
        dist = distribution(name)
    except PackageNotFoundError:
        print(f"Hinweis: {name} ist nicht installiert und fehlt in der SBOM.", file=sys.stderr)
        return None
    meta, version = dist.metadata, dist.version
    ref = f"pkg:pypi/{norm(name)}@{version}"
    comp = {
        "type": "library", "bom-ref": ref, "name": meta["Name"], "version": version, "scope": scope,
        "description": (meta.get("Summary") or "").strip(),
        "licenses": license_of(meta, name), "purl": ref,
    }
    home = meta.get("Home-page") or next(
        (u.split(",", 1)[1].strip() for u in meta.get_all("Project-URL") or [] if "," in u), None)
    if home:
        comp["externalReferences"] = [{"type": "website", "url": home}]
    if name in NOT_BUNDLED:
        comp["scope"] = "excluded"
        comp["properties"] = [{"name": "sepa-splitter:bundled", "value": "false"}]
    comp["_requires"] = requires_of(dist)
    return comp


def main() -> None:
    components: list[dict] = []
    deps: dict[str, list[str]] = {}

    py_ver = platform.python_version()
    python = {
        "type": "application", "bom-ref": f"pkg:generic/cpython@{py_ver}", "name": "CPython",
        "version": py_ver, "scope": "required", "description": "Python-Interpreter (von PyInstaller eingebettet)",
        "licenses": [{"expression": "PSF-2.0"}], "purl": f"pkg:generic/cpython@{py_ver}",
        "externalReferences": [{"type": "website", "url": "https://www.python.org/"}],
    }
    components.append(python)

    by_name: dict[str, dict] = {}
    for scope, names in (("required", RUNTIME), ("excluded", BUILD)):
        for n in names:
            c = pypi_component(n, scope)
            if c:
                components.append(c)
                by_name[norm(n)] = c

    # In den Wheels enthaltene native Bibliotheken als Unterkomponenten.
    try:
        from PySide6 import QtCore
        qt_ver = QtCore.qVersion()
        qt = {"type": "framework", "bom-ref": f"pkg:generic/qt@{qt_ver}", "name": "Qt", "version": qt_ver,
              "scope": "required", "description": "Qt-Bibliotheken (im Wheel PySide6_Essentials/Addons enthalten)",
              "licenses": [{"expression": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only"}],
              "purl": f"pkg:generic/qt@{qt_ver}",
              "externalReferences": [{"type": "website", "url": "https://www.qt.io/"}]}
        if "pyside6-essentials" in by_name:
            by_name["pyside6-essentials"]["components"] = [qt]
    except ImportError:
        pass
    try:
        from lxml import etree
        v = lambda t: ".".join(map(str, t))  # noqa: E731
        lxml_subs = []
        for nm, ver, lic, url in (("libxml2", v(etree.LIBXML_VERSION), "MIT", "https://gitlab.gnome.org/GNOME/libxml2"),
                                  ("libxslt", v(etree.LIBXSLT_VERSION), "MIT", "https://gitlab.gnome.org/GNOME/libxslt")):
            lxml_subs.append({"type": "library", "bom-ref": f"pkg:generic/{nm}@{ver}", "name": nm, "version": ver,
                              "scope": "required", "description": "statisch in lxml eingebunden",
                              "licenses": [{"expression": lic}], "purl": f"pkg:generic/{nm}@{ver}",
                              "externalReferences": [{"type": "vcs", "url": url}]})
        if "lxml" in by_name:
            by_name["lxml"]["components"] = lxml_subs
    except ImportError:
        pass

    app_ref = f"pkg:generic/sepa-splitter@{__version__}"
    deps[app_ref] = [python["bom-ref"], *(by_name[n]["bom-ref"] for n in ("pyside6", "lxml") if n in by_name)]
    for c in by_name.values():
        deps[c["bom-ref"]] = [by_name[r]["bom-ref"] for r in c.pop("_requires") if r in by_name]
        for sub in c.get("components", []):
            deps[c["bom-ref"]].append(sub["bom-ref"])
            deps[sub["bom-ref"]] = []
    deps[python["bom-ref"]] = []

    bom = {
        "bomFormat": "CycloneDX", "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}", "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "lifecycles": [{"phase": "build"}],
            "tools": {"components": [{"type": "application", "name": "build/make_sbom.py"}]},
            "component": {
                "type": "application", "bom-ref": app_ref, "name": "SEPA-Splitter", "version": __version__,
                "description": "Originalgetreues Aufteilen von SEPA-Lastschriftdateien (pain.008.001.02/.08)",
                "authors": [{"name": "Christian Zander"}], "purl": app_ref,
            },
            "properties": [{"name": "sepa-splitter:build-platform",
                            "value": f"{platform.system()} {platform.machine()}"}],
        },
        "components": components,
        "dependencies": [{"ref": r, "dependsOn": d} for r, d in deps.items()],
    }
    out = ROOT / "sbom.cdx.json"
    out.write_text(json.dumps(bom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SBOM geschrieben: {out} ({len(components)} Komponenten)")


if __name__ == "__main__":
    main()
