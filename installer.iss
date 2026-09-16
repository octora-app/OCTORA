; OCTORA Windows installer — build with Inno Setup 6 (jrsoftware.org/isinfo.php)
; Steps:
;   1. On your Windows PC, run:  python build_exe.py --onedir
;   2. Open this file in Inno Setup Compiler and press Compile.
;   3. Output: OCTORA-Setup.exe in the Output folder.
;      (The file name is intentionally version-less so the website's
;      "Download" button and the auto-updater keep working across releases.)

#define MyAppName "OCTORA"
#define MyAppVersion "1.4.5"
#define MyAppPublisher "Rouqil Tech"
#define MyAppExeName "OCTORA.exe"

[Setup]
AppId={{8F3B2A1C-OCTORA-4000-9E77-ROUQILTECH01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=Output
OutputBaseFilename=OCTORA-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\OCTORA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
