#define MyAppName "SHUNCHi by RUHUL"
#define MyAppVersion "4.4.0"
#define MyAppPublisher "Ruhul Amin"
#define MyAppExeName "SHUNCHi.exe"

[Setup]
AppId={{E9C3C2A1-64C5-4B2B-A3E2-8E7C9D3B1F40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://shunchiai.com
AppSupportURL=https://shunchiai.com
AppUpdatesURL=https://shunchiai.com
DefaultDirName={autopf}\SHUNCHi
DefaultGroupName=SHUNCHi by RUHUL
UninstallDisplayName=SHUNCHi by RUHUL
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer_output
OutputBaseFilename=SHUNCHi_by_RUHUL_Setup_4.4.0
SetupIconFile=assets\shunchi.ico
WizardImageFile=assets\wizard.bmp,assets\wizard@2x.bmp
WizardSmallImageFile=assets\wizard-small.bmp,assets\wizard-small@2x.bmp
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
DisableProgramGroupPage=yes
Uninstallable=yes
CloseApplications=no
RestartApplications=no
DisableDirPage=yes
DisableReadyPage=yes
SetupLogging=yes
VersionInfoCompany=Ruhul Amin
VersionInfoDescription=SHUNCHi AI Voice Typing for Windows
VersionInfoProductName=SHUNCHi by RUHUL
VersionInfoProductVersion=4.4.0

[Messages]
WelcomeLabel1=Welcome to SHUNCHi
WelcomeLabel2=Free AI voice typing for Windows.%n%nSpeak in Bangla or English and SHUNCHi types it wherever your cursor is: browser, WhatsApp, Word, anywhere.%n%nAll you need is a free Gemini API key. Click Next to continue.%n%nshunchiai.com
FinishedHeadingLabel=You're all set
FinishedLabel=SHUNCHi is installed and open on your screen.%n%nPaste your free Gemini API key in Settings, then press Win + Left Ctrl (Bangla) or Win + Left Shift (English) and start speaking.%n%nWebsite: shunchiai.com%nSupport: voice.shunchi@gmail.com
WizardSelectTasks=Choose your options
SelectTasksDesc=The recommended options are already selected.
SelectTasksLabel2=Untick anything you do not want, then click Install.
ButtonInstall=&Install

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Add a SHUNCHi shortcut to my desktop"; GroupDescription: "Recommended:"
Name: "startup"; Description: "Start SHUNCHi with Windows (runs quietly in the system tray)"; GroupDescription: "Recommended:"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\SHUNCHi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\shunchi.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\SHUNCHi by RUHUL"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\shunchi.ico"
Name: "{autodesktop}\SHUNCHi"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\shunchi.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SHUNCHi"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Tasks: startup; Flags: uninsdeletevalue
; Also removes the start-up entry if it was switched on later from SHUNCHi Settings.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "SHUNCHi"; Flags: uninsdeletevalue dontcreatekey

[Run]
; No tick-box: the dashboard opens by itself as soon as installation finishes.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden skipifdoesntexist; RunOnceId: "StopShunchi"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\assets"

[Code]
// SHUNCHi lives in the system tray and ignores a normal "close" request, so stop it before files are replaced.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(700);
  Result := '';
end;
