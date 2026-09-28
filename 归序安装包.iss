#define MyAppName "归序"
#define MyAppVersion "1.0.0"
#define MyAppExe "归序.exe"

[Setup]
AppId=GuiXu.FileOrganizer
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupArchitecture=x64
MinVersion=10.0
WizardStyle=modern
SetupIconFile=assets\guixu.ico
UninstallDisplayIcon={app}\{#MyAppExe}
OutputDir=release
OutputBaseFilename=归序-Setup-v1.0.0
Compression=lzma2
SolidCompression=yes
CloseApplications=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："; Flags: unchecked

[Files]
Source: "release\归序-便携版\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\归序"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\归序"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "启动归序"; Flags: nowait postinstall skipifsilent
