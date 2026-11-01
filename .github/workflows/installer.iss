[Setup]
AppName=Red Square Headset Control
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\RedSquareControl
DefaultGroupName=Red Square Control
OutputDir=..\..\Output
OutputBaseFilename=RedSquare_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\..\dist\RedSquare_Control.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Red Square Control"; Filename: "{app}\RedSquare_Control.exe"
Name: "{autodesktop}\Red Square Control"; Filename: "{app}\RedSquare_Control.exe"

[Run]
Filename: "{app}\RedSquare_Control.exe"; Description: "Запустить программу"; Flags: nowait postinstall skipifsilent
