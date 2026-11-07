; Compile through scripts/build_windows.py; Windows x64 / Inno Setup 6.
#ifndef ExtensionId
  #error ExtensionId must be supplied by the verified build script
#endif
#ifndef StageDir
  #error StageDir must be supplied by the build script
#endif
#ifndef DependencyScript
  #error DependencyScript must be supplied by the build script
#endif

[Setup]
AppId={{28D3FF14-D823-451C-985A-3E4F6BD013C8}
AppName=Opera Music Downloader
AppVersion=1.1.0
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
CloseApplications=no
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
Type: files; Name: "{localappdata}\OperaMusicDownloader\install-dependencies.log"
Type: dirifempty; Name: "{localappdata}\OperaMusicDownloader"

[UninstallRun]
Filename: "{app}\maintenance\OperaMusicDownloaderTools.exe"; Parameters: "--remove --destination ""{app}\tools"" --log ""{tmp}\omd-uninstall-tools.log"""; Flags: runhidden waituntilterminated skipifdoesntexist

[Code]
var
  SelfTestSucceeded: Boolean;
  DownloadPage: TDownloadWizardPage;
  DependenciesDownloaded: Boolean;

function CreateFileForIdleCheck(FileName: String; DesiredAccess, ShareMode: Cardinal;
  SecurityAttributes: Integer; CreationDisposition, Flags: Cardinal; TemplateFile: Integer): Integer;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseIdleCheckHandle(Handle: Integer): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function HostIsBusy: Boolean;
var
  LockPath: String;
  LockHandle: Integer;
begin
  Result := False;
  LockPath := ExpandConstant('{localappdata}\OperaMusicDownloader\host.lock');
  if FileExists(LockPath) then
  begin
    { Exclusive sharing fails while the existing host owns its open state lock.
      Do not terminate it or overwrite an active installation. Closing Opera
      disconnects stdio and lets the old host save state and cancel safely. }
    LockHandle := CreateFileForIdleCheck(LockPath, $80000000, 0, 0, 3, 0, 0);
    if LockHandle = -1 then
      Result := True
    else
      CloseIdleCheckHandle(LockHandle);
  end;
end;

procedure QueuePinnedDependencies;
begin
  DownloadPage.Clear;
  #include DependencyScript
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    if HostIsBusy then
    begin
      SuppressibleMsgBox('Feche todas as janelas do Opera GX e aguarde o aplicativo auxiliar encerrar antes de atualizar. Os downloads em andamento serão interrompidos com segurança. Depois clique em Instalar novamente.', mbInformation, MB_OK, IDOK);
      Result := False;
      Exit;
    end;
    QueuePinnedDependencies;
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        DependenciesDownloaded := True;
      except
        DependenciesDownloaded := False;
        if not DownloadPage.AbortedByUser then
          SuppressibleMsgBox('Não foi possível obter as dependências oficiais: ' + GetExceptionMessage + #13#10 + #13#10 + 'Verifique a conexão com a Internet e clique em Instalar para tentar novamente. Nenhum terminal é necessário.', mbError, MB_OK, IDOK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if HostIsBusy then
    Result := 'Feche todas as janelas do Opera GX e aguarde o aplicativo auxiliar encerrar. Depois tente instalar novamente.'
  else if not DependenciesDownloaded then
    Result := 'As dependências oficiais ainda não foram baixadas. Volte e clique em Instalar com uma conexão à Internet.';
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
  while HostIsBusy do
    if SuppressibleMsgBox('Feche todas as janelas do Opera GX e aguarde o aplicativo auxiliar encerrar antes de desinstalar. Clique em Repetir para continuar.', mbInformation, MB_RETRYCANCEL, IDCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
end;

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
    WizardForm.StatusLabel.Caption := 'Verificando e preparando as ferramentas baixadas...';
    if not Exec(ExpandConstant('{app}\maintenance\OperaMusicDownloaderTools.exe'),
      '--destination "' + ExpandConstant('{app}\tools') + '" --cache "' + ExpandConstant('{tmp}') + '" --log "' + ExpandConstant('{localappdata}\OperaMusicDownloader\install-dependencies.log') + '"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('Não foi possível preparar as ferramentas. Reinstale o pacote completo.');
    if ResultCode <> 0 then
      RaiseException('Falha ao verificar ou extrair as ferramentas. Consulte ' + ExpandConstant('{localappdata}\OperaMusicDownloader\install-dependencies.log') + ' e execute o instalador novamente.');
    WizardForm.StatusLabel.Caption := 'Testando o aplicativo e a conversão real de áudio...';
    SelfTestSucceeded := Exec(ExpandConstant('{app}\maintenance\OperaMusicDownloaderTools.exe'),
      '--destination "' + ExpandConstant('{app}\tools') + '" --self-test-host "' + ExpandConstant('{app}\OperaMusicDownloaderHost.exe') + '" --log "' + ExpandConstant('{localappdata}\OperaMusicDownloader\install-dependencies.log') + '"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    SelfTestSucceeded := SelfTestSucceeded and (ResultCode = 0);
    if not SelfTestSucceeded then
      RaiseException('O teste das dependências ou da conversão falhou. A instalação não foi validada. Consulte ' + ExpandConstant('{localappdata}\OperaMusicDownloader\install-dependencies.log') + ' e execute o instalador novamente.');
  end;
end;

procedure InitializeWizard;
begin
  SelfTestSucceeded := False;
  DependenciesDownloaded := False;
  DownloadPage := CreateDownloadPage('Obtendo ferramentas oficiais', 'Baixando yt-dlp, FFmpeg e Deno com verificação SHA256. É necessária uma conexão à Internet.', nil);
end;

function GetCustomSetupExitCode: Integer;
begin
  if SelfTestSucceeded then
    Result := 0
  else
    Result := 1;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
  begin
    if SelfTestSucceeded then
      WizardForm.FinishedLabel.Caption := 'Opera Music Downloader 1.1.0 instalado e dependências verificadas.' + #13#10 + #13#10 +
        'Falta ativar a extensão: abra opera://extensions, ative o Modo do desenvolvedor, clique em Carregar extensão descompactada e selecione:' + #13#10 + ExpandConstant('{app}\extension') + #13#10 + #13#10 +
        'Se já utilizava a extensão, atualize-a em opera://extensions mantendo a mesma pasta. Feche e abra o Opera GX. No popup, configure a pasta, formato e qualidade uma vez; os botões do YouTube passam a baixar com um clique. Preferências e músicas existentes foram preservadas.'
    else
      WizardForm.FinishedLabel.Caption := 'O teste do aplicativo auxiliar falhou. Consulte as instruções e reinstale o pacote completo antes de utilizar.';
  end;
end;
