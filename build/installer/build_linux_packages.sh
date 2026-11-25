#!/usr/bin/env bash
# Baut .deb- und .rpm-Paket aus dem portablen Build (vorher build/build_unix.sh auf Linux ausführen).
# Benötigt: dpkg-deb (Debian/Ubuntu: vorhanden) und rpmbuild (Debian/Ubuntu: Paket "rpm"; Fedora: "rpm-build").
# Fehlt eines der Werkzeuge, wird das jeweilige Paket übersprungen (mit Hinweis).
# Pakete werden nicht signiert (Signieren wäre mit dpkg-sig bzw. rpmsign und einem eigenen GPG-Schlüssel kostenlos
# möglich; ohne eigenes Paket-Repository bringt es aber kaum etwas).
#
# Inhalt beider Pakete:
#   /opt/sepa-splitter/                    Programmordner (mit Markierung "installiert", ohne INI)
#   /usr/bin/sepa-splitter                 Startbefehl (auch: sepa-splitter --cli DATEI)
#   /usr/share/applications/sepa-splitter.desktop, /usr/share/icons/hicolor/256x256/apps/sepa-splitter.png
#   /usr/share/doc/sepa-splitter/          LICENSE/copyright, SBOM
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' sepa_splitter/__init__.py)"
ARCH="$(uname -m)"
SRC="dist/SEPA-Splitter-Linux-$ARCH"
[ -d "$SRC" ] || { echo "$SRC fehlt – zuerst build/build_unix.sh ausführen." >&2; exit 1; }
case "$ARCH" in
  x86_64)  DEB_ARCH=amd64 ;;
  aarch64) DEB_ARCH=arm64 ;;
  *) echo "Nicht unterstützte Architektur: $ARCH" >&2; exit 1 ;;
esac
MAINTAINER="${PACKAGE_MAINTAINER:-Christian Zander <ZanderCh@users.noreply.github.com>}"
HOMEPAGE="https://github.com/ZanderCh/SEPA-Splitter"
SUMMARY="Originalgetreues Aufteilen von SEPA-Lastschriftdateien"
DESCRIPTION="Teilt SEPA-Lastschriftdateien (pain.008.001.02, pain.008.001.08) mit mehr
als 999 Transaktionen originalgetreu in möglichst gleich große Teildateien auf.
Vollständig offline."
# Mindest-glibc = Version des Build-Systems (PyInstaller-Pakete laufen nicht auf älteren Systemen).
GLIBC="$(getconf GNU_LIBC_VERSION | awk '{print $2}')"

WORK="build/work/linux-pkg"
ROOT="$WORK/root"
rm -rf "$WORK"
mkdir -p "$ROOT/opt/sepa-splitter" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/icons/hicolor/256x256/apps" "$ROOT/usr/share/doc/sepa-splitter"

# ---- gemeinsamer Dateibaum
cp -a "$SRC/." "$ROOT/opt/sepa-splitter/"
rm -f "$ROOT/opt/sepa-splitter/SEPA-Splitter.ini" "$ROOT/opt/sepa-splitter/LICENSE"
cp build/installer/SEPA-Splitter.installed "$ROOT/opt/sepa-splitter/"
cat > "$ROOT/usr/bin/sepa-splitter" <<'EOF'
#!/bin/sh
exec /opt/sepa-splitter/SEPA-Splitter "$@"
EOF
cat > "$ROOT/usr/share/applications/sepa-splitter.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=SEPA-Splitter
GenericName=SEPA-Lastschriften aufteilen
Comment=$SUMMARY
Exec=sepa-splitter
Icon=sepa-splitter
Terminal=false
Categories=Office;Finance;
Keywords=SEPA;Lastschrift;pain.008;XML;
EOF
cp sepa_splitter/assets/icon.png "$ROOT/usr/share/icons/hicolor/256x256/apps/sepa-splitter.png"
cp sbom.cdx.json "$ROOT/usr/share/doc/sepa-splitter/"
find "$ROOT" -type d -exec chmod 755 {} +
chmod -R u+rw,go+r,go-w "$ROOT"
chmod 755 "$ROOT/usr/bin/sepa-splitter" "$ROOT/opt/sepa-splitter/SEPA-Splitter"
INSTALLED_KB="$(du -sk "$ROOT" | cut -f1)"

# ---- .deb
if command -v dpkg-deb >/dev/null; then
  DEB_ROOT="$WORK/deb"
  cp -a "$ROOT" "$DEB_ROOT"
  { echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
    echo "Upstream-Name: SEPA-Splitter"; echo "Source: $HOMEPAGE"; echo
    echo "Files: *"; echo "Copyright: 2026 Christian Zander"; echo "License: GPL-3"
    echo " This program is free software: you can redistribute it and/or modify it under the terms"
    echo " of the GNU General Public License as published by the Free Software Foundation, version 3."
    echo " ."
    echo " On Debian systems, the complete text of the GNU General Public License version 3 can be"
    echo " found in /usr/share/common-licenses/GPL-3."
    echo " ."
    echo " Die Lizenzen der mitgelieferten Bibliotheken (Python, Qt/PySide6, lxml, ...) stehen in"
    echo " /usr/share/doc/sepa-splitter/sbom.cdx.json."; } > "$DEB_ROOT/usr/share/doc/sepa-splitter/copyright"
  printf 'sepa-splitter (%s-1) unstable; urgency=medium\n\n  * Paket aus dem portablen Build, siehe %s/releases\n\n -- %s  %s\n' \
    "$VERSION" "$HOMEPAGE" "$MAINTAINER" "$(LC_ALL=C date -R)" | gzip -9n > "$DEB_ROOT/usr/share/doc/sepa-splitter/changelog.Debian.gz"
  chmod 644 "$DEB_ROOT/usr/share/doc/sepa-splitter/changelog.Debian.gz"
  chmod 644 "$DEB_ROOT/usr/share/doc/sepa-splitter/copyright"
  mkdir -p "$DEB_ROOT/DEBIAN"
  cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: sepa-splitter
Version: $VERSION-1
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Maintainer: $MAINTAINER
Installed-Size: $INSTALLED_KB
Depends: libc6 (>= $GLIBC), libegl1, libgl1, libfontconfig1, libdbus-1-3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xfixes0
Recommends: xdg-utils
Homepage: $HOMEPAGE
Description: $SUMMARY
$(echo "$DESCRIPTION" | sed 's/^/ /')
EOF
  DEB="dist/sepa-splitter_${VERSION}-1_${DEB_ARCH}.deb"
  dpkg-deb --root-owner-group -Zxz --build "$DEB_ROOT" "$DEB" >/dev/null
  echo "Fertig: $DEB"
else
  echo "Hinweis: dpkg-deb fehlt, .deb wird übersprungen." >&2
fi

# ---- .rpm (vorgefertigte Dateien; keine automatische Abhängigkeitssuche, kein Strippen/debuginfo)
if command -v rpmbuild >/dev/null; then
  RPM_TOP="$(pwd)/$WORK/rpm"
  mkdir -p "$RPM_TOP"/{BUILD,RPMS,SPECS,SOURCES,SRPMS,BUILDROOT}
  install -m 644 LICENSE "$ROOT/usr/share/doc/sepa-splitter/LICENSE"
  S="()(64bit)"
  cat > "$RPM_TOP/SPECS/sepa-splitter.spec" <<EOF
%global debug_package %{nil}
%global __os_install_post %{nil}
%global _build_id_links none
%global __requires_exclude_from ^/opt/sepa-splitter/.*\$
%global __provides_exclude_from ^/opt/sepa-splitter/.*\$
Name:           sepa-splitter
Version:        $VERSION
Release:        1
Summary:        $SUMMARY
License:        GPL-3.0-only
URL:            $HOMEPAGE
Packager:       $MAINTAINER
AutoReqProv:    no
Requires:       libc.so.6(GLIBC_$GLIBC)$S, libEGL.so.1$S, libGL.so.1$S, libfontconfig.so.1$S, libdbus-1.so.3$S
Requires:       libxkbcommon.so.0$S, libxkbcommon-x11.so.0$S, libxcb-cursor.so.0$S, libxcb-icccm.so.4$S
Requires:       libxcb-image.so.0$S, libxcb-keysyms.so.1$S, libxcb-randr.so.0$S, libxcb-render-util.so.0$S
Requires:       libxcb-shape.so.0$S, libxcb-xinerama.so.0$S, libxcb-xfixes.so.0$S
Recommends:     xdg-utils

%description
$DESCRIPTION

%install
mkdir -p %{buildroot}
cp -a "$(pwd)/$ROOT/." %{buildroot}/

%files
%license /usr/share/doc/sepa-splitter/LICENSE
%doc /usr/share/doc/sepa-splitter/sbom.cdx.json
/opt/sepa-splitter
/usr/bin/sepa-splitter
/usr/share/applications/sepa-splitter.desktop
/usr/share/icons/hicolor/256x256/apps/sepa-splitter.png
%dir /usr/share/doc/sepa-splitter
EOF
  rpmbuild --quiet -bb --target "$ARCH" --define "_topdir $RPM_TOP" "$RPM_TOP/SPECS/sepa-splitter.spec"
  RPM="dist/sepa-splitter-${VERSION}-1.$ARCH.rpm"
  mv "$RPM_TOP/RPMS/$ARCH/"*.rpm "$RPM"
  echo "Fertig: $RPM"
else
  echo "Hinweis: rpmbuild fehlt, .rpm wird übersprungen (Debian/Ubuntu: sudo apt install rpm)." >&2
fi
rm -rf "$WORK"
