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
#ifndef MyAppVersion
  #error MyAppVersion not defined. Run `python build.py` to regenerate installer_version.iss before compiling installer.iss directly.
#endif
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
; Point UninstallDisplayIcon at the standalone .ico (copied to {app} below)
; rather than the exe. The exe also has the icon embedded via Bytehound.spec,
; but pointing at the .ico is a belt-and-braces safeguard: if a future spec
; change ever drops the embedded icon, the Programs & Features entry still
; shows the right logo instead of a generic floppy/blank-app glyph.
UninstallDisplayIcon      = {app}\logo_sq.ico
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
; Win10+ only. Win7/8/8.1 are out of Microsoft support and we don't test there.
MinVersion                = 10.0
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

[Files]
; ── Entire PyInstaller output (fully offline, all deps bundled) ──────────────
; Excludes trim known Qt bloat that ships unused: opengl32sw.dll is the ~20 MB
; software-rasterizer fallback, Qt translations add up fast, and we never use
; QtWebEngine. Adjust if any of those become needed.
Source: "{#MyDistDir}\*";        DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
                                 Excludes: "opengl32sw.dll,translations\*,*WebEngine*,*.pdb,*.pyi,*\__pycache__\*,*\tests\*"

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
// Downgrade guard. CompareStr does a lexicographic compare which is wrong for
// semver ("0.10.0" < "0.9.0" lexically), so we parse "major.minor.patch" into
// integers. Anything unparseable falls back to allowing the install — better
// to let an edge-case version pattern through than to brick the upgrade flow.
// Silent installs (auto-updater) always proceed without prompting, otherwise
// a downgrade triggered by the updater would deadlock waiting for a click.
// ---------------------------------------------------------------------------
function VersionTuple(const V: String; var Major, Minor, Patch: Integer): Boolean;
var
  Parts: TArrayOfString;
  Tmp: String;
  P: Integer;
begin
  Result := False;
  Major := 0; Minor := 0; Patch := 0;
  Tmp := V;
  // Split on '.'
  SetArrayLength(Parts, 0);
  while True do
  begin
    P := Pos('.', Tmp);
    SetArrayLength(Parts, GetArrayLength(Parts) + 1);
    if P = 0 then
    begin
      Parts[GetArrayLength(Parts) - 1] := Tmp;
      Break;
    end;
    Parts[GetArrayLength(Parts) - 1] := Copy(Tmp, 1, P - 1);
    Tmp := Copy(Tmp, P + 1, Length(Tmp));
  end;
  if GetArrayLength(Parts) < 1 then Exit;
  Major := StrToIntDef(Parts[0], -1);
  if GetArrayLength(Parts) >= 2 then Minor := StrToIntDef(Parts[1], -1);
  if GetArrayLength(Parts) >= 3 then Patch := StrToIntDef(Parts[2], -1);
  Result := (Major >= 0) and (Minor >= 0) and (Patch >= 0);
end;

function IsDowngrade(const Installed, Candidate: String): Boolean;
var
  IM, IN_, IP, CM, CN, CP: Integer;
begin
  Result := False;
  if not VersionTuple(Installed, IM, IN_, IP) then Exit;
  if not VersionTuple(Candidate, CM, CN, CP) then Exit;
  if IM <> CM then Result := IM > CM
  else if IN_ <> CN then Result := IN_ > CN
  else Result := IP > CP;
end;

function InitializeSetup(): Boolean;
var
  RegPath: String;
  Installed: String;
begin
  Result := True;
  RegPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';
  Installed := '';
  if not RegQueryStringValue(HKLM64, RegPath, 'DisplayVersion', Installed) then
    if not RegQueryStringValue(HKLM32, RegPath, 'DisplayVersion', Installed) then
      RegQueryStringValue(HKCU, RegPath, 'DisplayVersion', Installed);
  if Installed = '' then Exit;
  if not IsDowngrade(Installed, '{#MyAppVersion}') then Exit;
  if WizardSilent() then
  begin
    Log('Downgrade attempted during silent install. Aborting to prevent data corruption.');
    Result := False;
    Exit;
  end;
  Result := MsgBox(
    'A newer version of {#MyAppName} (' + Installed + ') is already installed.' + #13#10 +
    'You are about to install an older version ({#MyAppVersion}).' + #13#10 + #13#10 +
    'Continue anyway?',
    mbConfirmation, MB_YESNO) = IDYES;
    
  if Result = False then Exit;

  // Prevent splitting installations when a machine-wide install exists but we lack admin rights
  if not IsAdminInstallMode() then
  begin
    if RegKeyExists(HKLM64, RegPath) or RegKeyExists(HKLM32, RegPath) then
    begin
      if WizardSilent() then
      begin
        Log('Machine-wide installation exists but running in non-admin silent mode. Aborting to prevent split installations.');
        Result := False;
        Exit;
      end;
      MsgBox(
        'A system-wide installation of {#MyAppName} exists, but you are currently running this installer without administrator privileges.' + #13#10 + #13#10 +
        'Please restart the installer and choose "Install for all users" (which requires Administrator rights) to upgrade it.',
        mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

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
  // Explicit hive order: 64-bit HKLM (admin install on 64-bit OS) -> 32-bit
  // HKLM (legacy / non-x64 installs) -> HKCU (per-user install). Spelling out
  // HKLM64/HKLM32 instead of the implicit HKLM means the lookup keeps working
  // even if ArchitecturesInstallIn64BitMode is changed later.
  if not RegQueryStringValue(HKLM64, RegPath, 'UninstallString', Value) then
    if not RegQueryStringValue(HKLM32, RegPath, 'UninstallString', Value) then
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
  // The path MUST be quoted, otherwise spaces will break the uninstaller's
  // command-line parsing, causing it to fork to %TEMP% and break the blocking wait.
  Params := '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /_?="' + ExtractFilePath(CmdLine) + '"';
  // We never abort on failure here — a partial upgrade is better than a hard
  // stop in the middle of an auto-update. Log so the failure shows up in the
  // Inno Setup log (find it under %TEMP%\Setup Log*.txt).
  if not Exec(CmdLine, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Log('UninstallPreviousVersion: failed to launch old uninstaller at ' + CmdLine)
  else if ResultCode <> 0 then
    Log('UninstallPreviousVersion: old uninstaller exited with code ' + IntToStr(ResultCode));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Removing previous version...';
    UninstallPreviousVersion();
  end;
end;
