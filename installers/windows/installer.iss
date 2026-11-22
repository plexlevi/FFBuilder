; Inno Setup script for FFBuilder

#ifndef AppName
  #define AppName "FFBuilder"
#endif

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef AppSource
  #define AppSource "..\\..\\dist\\FFBuilder"
#endif

#ifndef OutputDir
  #define OutputDir "..\\..\\dist"
#endif

[Setup]
AppId={{4F9D77B5-9D8B-45FA-9E11-3E728C0E2A01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=FFBuilder
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-{#AppVersion}-setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: "{#AppSource}\\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
