; Inno Setup script for SingleCellBMSCycler.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#ifndef MyAppName
  #define MyAppName "SingleCellBMSCycler"
#endif

#ifndef MyAppExe
  #define MyAppExe "SingleCellBMSCycler.exe"
#endif

[Setup]
AppName=Bytehound Single-Cell BMS Cycler
AppVersion={#MyAppVersion}
AppPublisher=Bytehound
DefaultDirName={autopf}\{#MyAppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\installer
OutputBaseFilename=SingleCellBMSCycler_Setup
SetupIconFile=branding\logo.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent
