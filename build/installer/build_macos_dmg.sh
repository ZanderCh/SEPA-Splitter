#!/usr/bin/env bash
# Baut das macOS-Disk-Image (DMG) aus dem portablen Build (vorher build/build_unix.sh auf dem Mac ausführen).
# Das DMG enthält SEPA-Splitter.app (mit Markierung "installiert"), eine Verknüpfung auf /Applications
# zum Hineinziehen sowie LICENSE und die SBOM. Nur Bordmittel (hdiutil, codesign).
#
# Signieren ist OPTIONAL. Ohne Apple-Developer-Zertifikat wird ad hoc signiert (kostenlos, nötig für Apple
# Silicon); Gatekeeper fragt dann beim ersten Start nach (siehe INSTALL.md).
# Mit Zertifikat vor dem Aufruf setzen:
#   MACOS_SIGN_IDENTITY   z. B. "Developer ID Application: NAME (TEAMID)" (im Schlüsselbund vorhanden)
# Zusätzlich notarisieren (nur zusammen mit MACOS_SIGN_IDENTITY):
#   MACOS_NOTARY_APPLE_ID, MACOS_NOTARY_TEAM_ID, MACOS_NOTARY_PASSWORD (app-spezifisches Kennwort)
set -euo pipefail
cd "$(dirname "$0")/../.."
[ "$(uname -s)" = "Darwin" ] || { echo "Nur unter macOS ausführbar." >&2; exit 1; }

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' sepa_splitter/__init__.py)"
ARCH="$(uname -m)"
SRC="dist/SEPA-Splitter-macOS-$ARCH/SEPA-Splitter.app"
[ -d "$SRC" ] || { echo "$SRC fehlt – zuerst build/build_unix.sh ausführen." >&2; exit 1; }
DMG="dist/SEPA-Splitter-$VERSION-macOS-$ARCH.dmg"
STAGE="build/work/dmg"

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
ditto "$SRC" "$STAGE/SEPA-Splitter.app"          # ditto erhält Symlinks und Attribute im Bundle
cp build/installer/SEPA-Splitter.installed "$STAGE/SEPA-Splitter.app/Contents/Resources/"
cp LICENSE "$STAGE/LICENSE.txt"
cp sbom.cdx.json "$STAGE/"
ln -s /Applications "$STAGE/Programme"

# Die hinzugefügte Markierung ändert das Bundle: neu signieren (sonst startet es auf Apple Silicon nicht).
if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
  echo "Signiere mit: $MACOS_SIGN_IDENTITY"
  codesign --deep --force --options runtime --timestamp --sign "$MACOS_SIGN_IDENTITY" "$STAGE/SEPA-Splitter.app"
else
  echo "Kein Zertifikat angegeben: Ad-hoc-Signatur (nicht notarisiert)."
  codesign --deep --force --sign - "$STAGE/SEPA-Splitter.app"
fi
codesign --verify --deep --strict "$STAGE/SEPA-Splitter.app"

hdiutil create -volname "SEPA-Splitter $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG"

if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
  codesign --force --timestamp --sign "$MACOS_SIGN_IDENTITY" "$DMG"
  if [ -n "${MACOS_NOTARY_APPLE_ID:-}" ] && [ -n "${MACOS_NOTARY_TEAM_ID:-}" ] && [ -n "${MACOS_NOTARY_PASSWORD:-}" ]; then
    echo "Notarisiere ..."
    xcrun notarytool submit "$DMG" --apple-id "$MACOS_NOTARY_APPLE_ID" --team-id "$MACOS_NOTARY_TEAM_ID" \
      --password "$MACOS_NOTARY_PASSWORD" --wait
    xcrun stapler staple "$DMG"
  fi
fi
rm -rf "$STAGE"
echo "Fertig: $DMG"
