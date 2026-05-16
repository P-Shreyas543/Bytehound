; ============================================================================
; Bytehound  –  Inno Setup Script
; Generates: installer_output\Bytehound_Setup_<version>.exe
;
; Requirements:
;   Inno Setup 6.x  https://jrsoftware.org/isinfo.php
;   Run AFTER:  python build.py --no-zip
;
; Compile from command line:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; ============================================================================

#define MyAppName      "Bytehound"
#define MyAppSlug      "Bytehound"
; MyAppVersion and MyDeveloper come from version.json via the auto-generated
; installer_version.iss. Run `python build.py` (any flags) to refresh it.
; The file is .gitignored — single source of truth lives in version.json.
#include "installer_version.iss"
#define MyAppExe       "Bytehound.exe"
#define MyAppIcon      "branding\logo_sq.ico"
#define MyDistDir      "dist\Bytehound"

[Setup]
; ── Identity ────────────────────────────────────────────────────────────────
AppId                     = {{FD5F3D1F-A6B1-4A59-99E7-2485AC78B5F6}
AppName                   = {#MyAppName}
AppVersion                = {#MyAppVersion}
AppVerName                = {#MyAppName} v{#MyAppVersion}
AppPublisher              = {#MyDeveloper}
AppCopyright              = Copyright (C) 2026 {#MyDeveloper}

; ── Install location ────────────────────────────────────────────────────────
; Installs to C:\Program Files\Bytehound  (admin)
; Falls back to %LocalAppData%\Programs\...  (no admin)
DefaultDirName            = {autopf}\{#MyAppSlug}
DefaultGroupName          = {#MyAppName}
AllowNoIcons              = no
DisableProgramGroupPage   = yes

; ── Installer output ────────────────────────────────────────────────────────
OutputDir                 = installer_output
OutputBaseFilename        = Bytehound_Setup_{#MyAppVersion}
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
VersionInfoCompany        = {#MyDeveloper}
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
; Excludes trim known Qt bloat that ships unused: opengl32sw.dll is the ~20 MB
; software-rasterizer fallback, Qt translations add up fast, and we never use
; QtWebEngine. Adjust if any of those become needed.
Source: "{#MyDistDir}\*";        DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
                                 Excludes: "opengl32sw.dll,translations\*,*WebEngine*"

; ── Branding assets at exe root ──────────────────────────────────────────────
Source: "branding\logo_sq.ico";  DestDir: "{app}"; Flags: ignoreversion
Source: "branding\logo_sq.png";  DestDir: "{app}"; Flags: ignoreversion
Source: "branding\logo_rec.png"; DestDir: "{app}"; Flags: ignoreversion

; ── version.json – update checker reads this from install dir ────────────────
Source: "version.json";          DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Desktop shortcut – name is static (no version) so Windows Taskbar/Start pins
; survive auto-updates. Renaming the shortcut on every release breaks pins.
Name: "{autodesktop}\{#MyAppName}"; \
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
// Auto-uninstall the previous version before laying down new files. The
// auto-updater invokes us with /SILENT, and the new exe needs a clean {app}
// to avoid stale files mixing with the new bundle.
//
// Inno Setup's uninstaller normally copies itself to %TEMP% and forks — the
// original process exits immediately and our Exec() call returns long before
// the uninstall finishes, racing the [Files] copy. The undocumented `/_?=`
// parameter forces the uninstaller to run in place (no temp copy, no fork),
// so ewWaitUntilTerminated actually waits.
// ---------------------------------------------------------------------------
function GetUninstallString(): String;
var
  RegPath: String;
  Value: String;
begin
  RegPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';
  Value := '';
  if not RegQueryStringValue(HKLM, RegPath, 'UninstallString', Value) then
    RegQueryStringValue(HKCU, RegPath, 'UninstallString', Value);
  Result := Value;
end;

procedure UninstallPreviousVersion();
var
  CmdLine: String;
  Params: String;
  ResultCode: Integer;
begin
  CmdLine := GetUninstallString();
  if CmdLine = '' then
    Exit;
  CmdLine := RemoveQuotes(CmdLine);
  // /_?= must be last and must point at the uninstaller's directory so the
  // uninstaller runs in-place and Exec() blocks until it truly finishes.
  Params := '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /_?=' + ExtractFilePath(CmdLine);
  Exec(CmdLine, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Removing previous version...';
    UninstallPreviousVersion();
  end;
end;
