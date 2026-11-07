; Compile through scripts/build_windows.py; Windows x64 / Inno Setup 6.
#ifndef ExtensionId
  #error ExtensionId must be supplied by the verified build script
#endif
#ifndef StageDir
  #error StageDir must be supplied by the build script
#endif

[Setup]
AppId={{28D3FF14-D823-451C-985A-3E4F6BD013C8}
AppName=Opera Music Downloader
AppVersion=1.0.0
AppPublisher=Opera Music Downloader contributors
DefaultDirName={localappdata}\Programs\OperaMusicDownloader
DefaultGroupName=Opera Music Downloader
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=OperaMusicDownloader-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Opera Music Downloader
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
InfoBeforeFile=installer-information.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
; Opera documents the Chromium / Google Chrome host namespace.
Root: HKCU32; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.opera_music_downloader"; ValueType: string; ValueData: "{app}\com.opera_music_downloader.json"; Flags: uninsdeletekey
Root: HKCU64; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.opera_music_downloader"; ValueType: string; ValueData: "{app}\com.opera_music_downloader.json"; Flags: uninsdeletekey

[Icons]
Name: "{group}\Como ativar a extensão"; Filename: "{app}\LEIA-ME.html"
Name: "{group}\Pasta da extensão para o Opera GX"; Filename: "{app}\extension"
Name: "{group}\Desinstalar Opera Music Downloader"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\LEIA-ME.html"; Description: "Abrir instruções para ativar a extensão no Opera GX"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallDelete]
Type: files; Name: "{app}\com.opera_music_downloader.json"
; Delete only known app configuration files. Never recursively remove a user folder.
Type: files; Name: "{localappdata}\OperaMusicDownloader\state.json"
Type: files; Name: "{localappdata}\OperaMusicDownloader\settings.json"
Type: files; Name: "{localappdata}\OperaMusicDownloader\state.json.tmp"
Type: files; Name: "{localappdata}\OperaMusicDownloader\state-corrompido.json"
Type: files; Name: "{localappdata}\OperaMusicDownloader\host.lock"
Type: files; Name: "{localappdata}\OperaMusicDownloader\state-*.tmp"
Type: dirifempty; Name: "{localappdata}\OperaMusicDownloader"

[Code]
var
  SelfTestSucceeded: Boolean;

function JsonEscape(Value: String): String;
begin
  StringChangeEx(Value, '\', '\\', True);
  StringChangeEx(Value, '"', '\"', True);
  Result := Value;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  HostManifest: String;
  ResultCode: Integer;
  ManifestLines: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    HostManifest := '{' + #13#10 +
      '  "name": "com.opera_music_downloader",' + #13#10 +
      '  "description": "Opera Music Downloader - aplicativo auxiliar local",' + #13#10 +
      '  "path": "' + JsonEscape(ExpandConstant('{app}\OperaMusicDownloaderHost.exe')) + '",' + #13#10 +
      '  "type": "stdio",' + #13#10 +
      '  "allowed_origins": ["chrome-extension://{#ExtensionId}/"]' + #13#10 +
      '}' + #13#10;
    SetArrayLength(ManifestLines, 1);
    ManifestLines[0] := HostManifest;
    if not SaveStringsToUTF8FileWithoutBOM(ExpandConstant('{app}\com.opera_music_downloader.json'), ManifestLines, False) then
      RaiseException('Não foi possível gravar a configuração do aplicativo auxiliar.');
    SelfTestSucceeded := Exec(ExpandConstant('{app}\OperaMusicDownloaderHost.exe'), '--self-test', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    SelfTestSucceeded := SelfTestSucceeded and (ResultCode = 0);
    if not SelfTestSucceeded then
      MsgBox('O aplicativo foi copiado, mas o teste das dependências falhou. Não considere a instalação validada. Consulte LEIA-ME.html e reinstale o pacote completo.', mbError, MB_OK);
  end;
end;

procedure InitializeWizard;
begin
  SelfTestSucceeded := False;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
  begin
    if SelfTestSucceeded then
      WizardForm.FinishedLabel.Caption := 'Aplicativo auxiliar instalado e dependências verificadas.' + #13#10 + #13#10 +
        'Falta ativar a extensão: abra opera://extensions, ative o Modo do desenvolvedor, clique em Carregar extensão descompactada e selecione:' + #13#10 + ExpandConstant('{app}\extension') + #13#10 + #13#10 +
        'Feche e abra o Opera GX. O popup deve informar Aplicativo conectado. O teste do instalador não substitui esse teste no navegador.'
    else
      WizardForm.FinishedLabel.Caption := 'O teste do aplicativo auxiliar falhou. Consulte as instruções e reinstale o pacote completo antes de utilizar.';
  end;
end;
