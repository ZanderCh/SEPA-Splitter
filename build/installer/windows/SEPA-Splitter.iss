; Inno-Setup-Skript für den Windows-Installer (Inno Setup 6.3 oder neuer).
; Aufruf über build\installer\build_windows_installer.ps1, das Version und Quellordner übergibt:
;   ISCC.exe /DAppVersion=1.0.0 /DSourceDir=...\dist\SEPA-Splitter-Windows /DOutputDir=...\dist SEPA-Splitter.iss
; Optional signiert (nur wenn ein Zertifikat vorhanden ist): zusätzlich /DSign /Ssigntool="signtool.exe sign ... $f"

#ifndef AppVersion
  #error AppVersion fehlt (/DAppVersion=...)
#endif
#ifndef SourceDir
  #error SourceDir fehlt (/DSourceDir=...)
#endif
#ifndef OutputDir
  #define OutputDir "..\..\..\dist"
#endif

[Setup]
; Feste AppId: verbindet Aktualisierungen und Deinstallation mit früheren Versionen. Nie ändern.
AppId={{FF63415C-F9D2-4085-BA9E-871AAEABC48B}
AppName=SEPA-Splitter
AppVersion={#AppVersion}
AppVerName=SEPA-Splitter {#AppVersion}
AppPublisher=Christian Zander
AppPublisherURL=https://github.com/ZanderCh/SEPA-Splitter
AppSupportURL=https://github.com/ZanderCh/SEPA-Splitter/issues
AppUpdatesURL=https://github.com/ZanderCh/SEPA-Splitter/releases
AppCopyright=Copyright (C) 2026 Christian Zander
VersionInfoVersion={#AppVersion}
; Standard: Installation nur für den eigenen Benutzer, ohne Administratorrechte
; (%LOCALAPPDATA%\Programs). Im Dialog oder mit /ALLUSERS auch für alle Benutzer (Program Files).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
DefaultDirName={autopf}\SEPA-Splitter
DefaultGroupName=SEPA-Splitter
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\..\..\LICENSE
SetupIconFile=..\..\icon.ico
UninstallDisplayIcon={app}\SEPA-Splitter.exe
UninstallDisplayName=SEPA-Splitter
OutputDir={#OutputDir}
OutputBaseFilename=SEPA-Splitter-{#AppVersion}-Windows-x64-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
#ifdef Sign
SignTool=signtool
SignedUninstaller=yes
#endif

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Programmordner aus dem PyInstaller-Build, ohne die INI: die installierte Anwendung legt sie im Benutzerordner an.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "SEPA-Splitter.ini"; Flags: ignoreversion recursesubdirs createallsubdirs
; Markierung "installiert" (siehe sepa_splitter/paths.py)
Source: "..\SEPA-Splitter.installed"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\..\sbom.cdx.json"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Reste einer älteren Version entfernen, bevor die neue Fassung kopiert wird
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\SEPA-Splitter"; Filename: "{app}\SEPA-Splitter.exe"
Name: "{autodesktop}\SEPA-Splitter"; Filename: "{app}\SEPA-Splitter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SEPA-Splitter.exe"; Description: "{cm:LaunchProgram,SEPA-Splitter}"; Flags: nowait postinstall skipifsilent

; Die Einstellungen im Benutzerordner (%APPDATA%\SEPA-Splitter) bleiben bei der Deinstallation erhalten.
