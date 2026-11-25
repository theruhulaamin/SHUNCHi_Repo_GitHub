; SHUNCHi web installer (stub). ~3 MB. Always installs the LATEST release:
; it reads https://shunchiai.com/update.json, downloads the full installer from the GitHub release,
; checks its SHA-256, then starts it. Needs Inno Setup 6.4 or newer.
#ifndef StubVersion
  #define StubVersion "1.0.0"
#endif
#define ManifestUrl "https://shunchiai.com/update.json"
#define AllowedPrefix "https://github.com/theruhulaamin/"

[Setup]
AppId={{B7A2F1D4-3C58-4E0B-9A61-5D2E8C4F7A10}
AppName=SHUNCHi
AppVersion={#StubVersion}
AppPublisher=Ruhul Amin
AppPublisherURL=https://shunchiai.com
CreateAppDir=no
Uninstallable=no
CreateUninstallRegKey=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
OutputDir=installer_output
OutputBaseFilename=SHUNCHi_Setup
SetupIconFile=assets\shunchi.ico
WizardImageFile=assets\wizard.bmp,assets\wizard@2x.bmp
WizardSmallImageFile=assets\wizard-small.bmp,assets\wizard-small@2x.bmp
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
MinVersion=10.0
SetupLogging=yes
VersionInfoCompany=Ruhul Amin
VersionInfoDescription=SHUNCHi web installer
VersionInfoProductName=SHUNCHi
VersionInfoVersion={#StubVersion}.0
VersionInfoProductVersion={#StubVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=SHUNCHi
WelcomeLabel2=Free AI voice typing for Windows.%n%nThis small installer downloads the latest version of SHUNCHi from shunchiai.com and starts the setup. You need an internet connection.%n%nClick Next to download.
ButtonNext=&Download

[Code]
var
  DownloadPage: TDownloadWizardPage;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Downloading SHUNCHi', 'Getting the latest version. Please wait...', @OnDownloadProgress);
end;

// Tiny reader for flat JSON written by our own release script: "key": "value"
function JsonValue(const Json, Key: String): String;
var
  P, Q: Integer;
  Pat: String;
begin
  Result := '';
  Pat := '"' + Key + '"';
  P := Pos(Pat, Json);
  if P = 0 then Exit;
  P := P + Length(Pat);
  while (P <= Length(Json)) and ((Json[P] = ' ') or (Json[P] = ':') or (Json[P] = #9) or (Json[P] = #13) or (Json[P] = #10)) do
    P := P + 1;
  if (P > Length(Json)) or (Json[P] <> '"') then Exit;
  P := P + 1;
  Q := P;
  while (Q <= Length(Json)) and (Json[Q] <> '"') do
    Q := Q + 1;
  Result := Copy(Json, P, Q - P);
end;

function IsHex64(const S: String): Boolean;
var
  I: Integer;
begin
  Result := Length(S) = 64;
  if not Result then Exit;
  for I := 1 to 64 do
    if Pos(S[I], '0123456789abcdef') = 0 then
    begin
      Result := False;
      Exit;
    end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Raw: AnsiString;
  Manifest, Url, Sha, Ver, TmpCopy: String;
  ResultCode: Integer;
begin
  Result := True;
  if CurPageID <> wpWelcome then Exit;
  Result := False;
  DownloadPage.Clear;
  DownloadPage.Add('{#ManifestUrl}?t=' + GetDateTimeString('yyyymmddhhnnss', #0, #0), 'update.json', '');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
      if not LoadStringFromFile(ExpandConstant('{tmp}\update.json'), Raw) then
        RaiseException('Could not read the version information.');
      Manifest := String(Raw);
      Url := JsonValue(Manifest, 'installer_url');
      Sha := Lowercase(JsonValue(Manifest, 'installer_sha256'));
      Ver := JsonValue(Manifest, 'latest_version');
      // Safety: only our own GitHub releases, over https, and always with a checksum.
      if (Pos('{#AllowedPrefix}', Url) <> 1) or (Pos('/releases/download/', Url) = 0) then
        RaiseException('No installer is published yet. Please try again later.');
      if not IsHex64(Sha) then
        RaiseException('The release has no checksum, so the download was stopped for safety.');
      DownloadPage.Clear;
      DownloadPage.Add(Url, 'SHUNCHi_Setup_Full.exe', Sha);
      DownloadPage.SetText('Downloading SHUNCHi ' + Ver, 'The file is checked before it runs.');
      DownloadPage.Download;
      TmpCopy := ExpandConstant('{%TEMP}\SHUNCHi_Setup_' + Ver + '.exe');
      if not FileCopy(ExpandConstant('{tmp}\SHUNCHi_Setup_Full.exe'), TmpCopy, False) then
        RaiseException('Could not prepare the installer in the temporary folder.');
      if not Exec(TmpCopy, '', '', SW_SHOWNORMAL, ewNoWait, ResultCode) then
        RaiseException('Could not start the installer.');
      Result := True;  // nothing left for this small setup to do, it closes by itself
    except
      if DownloadPage.AbortedByUser then
        Log('Download cancelled by the user.')
      else
        SuppressibleMsgBox(AddPeriod(GetExceptionMessage) + #13#10#13#10 +
          'You can also download SHUNCHi manually from https://shunchiai.com/download', mbCriticalError, MB_OK, IDOK);
      Result := False;
    end;
  finally
    DownloadPage.Hide;
  end;
end;
