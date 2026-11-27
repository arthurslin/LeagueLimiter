; Inno Setup script for League Limiter.
; Build the app first:  pyinstaller --noconfirm --windowed --name LeagueLimiter --icon assets/icon.ico --add-data "assets/icon.ico;assets" limiter.pyw
; Then:                 ISCC.exe /DAppVersion=1.0.0 installer\LeagueLimiter.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C2B7E-4A0D-4E8B-9C51-3D7A2F9E8B14}
AppName=League Limiter
AppVersion={#AppVersion}
AppVerName=League Limiter {#AppVersion}
AppPublisher=League Limiter
AppPublisherURL=https://github.com/arthurslin/LeagueLimiter
DefaultDirName={localappdata}\Programs\LeagueLimiter
DisableProgramGroupPage=yes
DisableDirPage=auto
; Per-user install: no admin prompt
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=LeagueLimiter-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\LeagueLimiter.exe
UninstallDisplayName=League Limiter
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "startup"; Description: "Start League Limiter automatically when I sign in (recommended)"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\LeagueLimiter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Keep the user's edited settings on upgrade
Source: "..\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{userprograms}\League Limiter"; Filename: "{app}\LeagueLimiter.exe"
Name: "{userprograms}\League Limiter settings"; Filename: "{app}\config.json"
Name: "{userdesktop}\League Limiter"; Filename: "{app}\LeagueLimiter.exe"; Tasks: desktopicon
; Same name as the script version's shortcut, so it replaces it
Name: "{userstartup}\League Limiter"; Filename: "{app}\LeagueLimiter.exe"; Tasks: startup

[Run]
Filename: "{app}\LeagueLimiter.exe"; Description: "Start League Limiter now"; Flags: nowait postinstall

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM LeagueLimiter.exe"; Flags: runhidden; RunOnceId: "StopApp"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Stop a running copy so its files can be replaced on upgrade }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM LeagueLimiter.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
