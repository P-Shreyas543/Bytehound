; ============================================================================
; Serial-MonitorApp  –  Inno Setup Script
; Generates: installer_output\SerialMonitor_Setup_<version>.exe
;
; Requirements:
;   Inno Setup 6.x  https://jrsoftware.org/isinfo.php
;   Run AFTER:  python build.py --no-zip
;
; Compile from command line:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; ============================================================================

#define MyAppName      "Serial Monitor"
#define MyAppSlug      "Serial-MonitorApp"
#define MyAppVersion   "0.1.0"
#define MyPublisher    "Serial Monitor"
#define MyAppExe       "Serial-MonitorApp.exe"
#define MyAppIcon      "branding\logo_sq.ico"
#define MyDistDir      "dist\Serial-MonitorApp"

[Setup]
; ── Identity ────────────────────────────────────────────────────────────────
AppId                     = {{FD5F3D1F-A6B1-4A59-99E7-2485AC78B5F6}
AppName                   = {#MyAppName}
AppVersion                = {#MyAppVersion}
AppVerName                = {#MyAppName} v{#MyAppVersion}
AppPublisher              = {#MyPublisher}
AppCopyright              = Copyright (C) 2026 {#MyPublisher}

; ── Install location ────────────────────────────────────────────────────────
; Installs to C:\Program Files\Serial-MonitorApp  (admin)
; Falls back to %LocalAppData%\Programs\...  (no admin)
DefaultDirName            = {autopf}\{#MyAppSlug}
DefaultGroupName          = {#MyAppName}
AllowNoIcons              = no
DisableProgramGroupPage   = yes

; ── Installer output ────────────────────────────────────────────────────────
OutputDir                 = installer_output
OutputBaseFilename        = SerialMonitor_Setup_{#MyAppVersion}
SetupIconFile             = {#MyAppIcon}
UninstallDisplayIcon      = {app}\{#MyAppExe}
UninstallDisplayName      = {#MyAppName} v{#MyAppVersion}

; ── Compression – everything bundled, zero internet needed ──────────────────
Compression               = lzma2/ultra64
SolidCompression          = yes
LZMAUseSeparateProcess    = yes

; ── Privileges ──────────────────────────────────────────────────────────────
PrivilegesRequired                    = lowest
PrivilegesRequiredOverridesAllowed    = dialog

; ── Visuals ─────────────────────────────────────────────────────────────────
WizardStyle               = modern
ShowLanguageDialog        = auto

; ── Version info stamped into the installer PE ──────────────────────────────
VersionInfoVersion        = {#MyAppVersion}.0
VersionInfoCompany        = {#MyPublisher}
VersionInfoDescription    = {#MyAppName} Installer
VersionInfoProductName    = {#MyAppName}
VersionInfoProductVersion = {#MyAppVersion}

; ── Misc ────────────────────────────────────────────────────────────────────
ArchitecturesInstallIn64BitMode = x64compatible
CloseApplications         = yes
RestartApplications       = no
ChangesAssociations       = no

; ── Code signing (opt-in) ───────────────────────────────────────────────────
; Build signed: invoke ISCC with /dSIGN and /Ssigntool="<full signtool cmd> $f"
; build.py passes both automatically when SIGN_PFX + SIGN_PASSWORD env vars are set.
#ifdef SIGN
SignTool                  = signtool
SignedUninstaller         = yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Note: Inno Setup tasks are checked by default; there is no `checked` flag.
; Use `unchecked` to flip the default off.
Name: "desktopicon";   Description: "Create a &desktop shortcut";  GroupDescription: "Shortcuts:"
Name: "startmenu";     Description: "Create a &Start Menu entry";   GroupDescription: "Shortcuts:"

[Dirs]
; Pre-create the default logs directory so the app finds it on first launch
Name: "{userdocs}\{#MyAppSlug}"; Flags: uninsneveruninstall

[Files]
; ── Entire PyInstaller output (fully offline, all deps bundled) ──────────────
Source: "{#MyDistDir}\*";        DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── Branding assets at exe root ──────────────────────────────────────────────
Source: "branding\logo_sq.ico";  DestDir: "{app}"; Flags: ignoreversion
Source: "branding\logo_sq.png";  DestDir: "{app}"; Flags: ignoreversion
Source: "branding\logo_rec.png"; DestDir: "{app}"; Flags: ignoreversion

; ── version.json – update checker reads this from install dir ────────────────
Source: "version.json";          DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Desktop shortcut – name includes version number
Name: "{autodesktop}\{#MyAppName} v{#MyAppVersion}"; \
      Filename: "{app}\{#MyAppExe}"; \
      IconFilename: "{app}\logo_sq.ico"; \
      Tasks: desktopicon

; Start Menu
Name: "{group}\{#MyAppName}"; \
      Filename: "{app}\{#MyAppExe}"; \
      IconFilename: "{app}\logo_sq.ico"; \
      Tasks: startmenu

Name: "{group}\Uninstall {#MyAppName}"; \
      Filename: "{uninstallexe}"; \
      Tasks: startmenu

[Run]
; Offer to launch after install (unchecked by default for silent installs)
Filename: "{app}\{#MyAppExe}"; \
          Description: "Launch {#MyAppName} now"; \
          Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Remove entire install directory on uninstall
Type: filesandordirs; Name: "{app}"

[Code]
// ---------------------------------------------------------------------------
// Pre-install: detect if app is already running and warn user
// ---------------------------------------------------------------------------
function IsAppRunning(const ExeName: String): Boolean;
var
  WbemLocator, WbemService, WbemObjectSet: Variant;
begin
  Result := False;
  try
    WbemLocator   := CreateOleObject('WbemScripting.SWbemLocator');
    WbemService   := WbemLocator.ConnectServer('.', 'root\cimv2', '', '');
    WbemObjectSet := WbemService.ExecQuery(
      'SELECT Name FROM Win32_Process WHERE Name="' + ExeName + '"');
    Result := not VarIsNull(WbemObjectSet) and (WbemObjectSet.Count > 0);
  except
    Result := False;
  end;
end;

function InitializeSetup(): Boolean;
begin
  if IsAppRunning('{#MyAppExe}') then
  begin
    MsgBox(
      '{#MyAppName} is currently running.' + #13#10 +
      'Please close it before continuing installation.',
      mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;

// ---------------------------------------------------------------------------
// Uninstall: remove desktop shortcuts created by previous versions
// ---------------------------------------------------------------------------
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  OldShortcut: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Clean up any versioned desktop shortcuts from older installs
    OldShortcut := ExpandConstant('{autodesktop}\{#MyAppName}*.lnk');
    DelTree(OldShortcut, False, True, False);
  end;
end;
