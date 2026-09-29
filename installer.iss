; Inno Setup script for SingleCellCycler.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppName=SingleCellCycler
AppVersion={#MyAppVersion}
AppPublisher=Bytehound
DefaultDirName={autopf}\SingleCellCycler
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\installer
OutputBaseFilename=SingleCellCycler
SetupIconFile=branding\logo.ico
UninstallDisplayIcon={app}\SingleCellCycler.exe
Compression=lzma
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\SingleCellCycler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SingleCellCycler"; Filename: "{app}\SingleCellCycler.exe"
Name: "{group}\Uninstall SingleCellCycler"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SingleCellCycler"; Filename: "{app}\SingleCellCycler.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SingleCellCycler.exe"; Description: "Launch SingleCellCycler"; Flags: postinstall nowait skipifsilent
