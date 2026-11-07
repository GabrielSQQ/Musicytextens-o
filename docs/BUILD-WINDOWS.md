# Instalador Windows 1.1.0

`OperaMusicDownloader-Setup.exe` instala o aplicativo auxiliar e obtém as
ferramentas automaticamente. A usuária não instala Python, yt-dlp, FFmpeg ou
Deno manualmente e não precisa abrir terminal. **É necessária uma conexão à
Internet para instalar e atualizar.**

## Como atualizar sem perder configurações

1. Aguarde os downloads concluírem e feche todas as janelas do Opera GX. Isso
   permite ao aplicativo antigo gravar seu estado e encerrar com segurança.
2. Execute o novo Setup na mesma pasta. O instalador mantém a mesma identidade,
   chave da extensão, registro Native Messaging e diretório de preferências.
   Ele recusa substituir o aplicativo enquanto o host antigo estiver ativo.
3. O assistente baixa as versões fixadas de yt-dlp, FFmpeg e Deno diretamente
   dos projetos oficiais, mostra progresso real e verifica SHA256. Em caso de
   falha, informa o motivo e permite tentar novamente.
4. Abra `opera://extensions`, atualize a extensão existente mantendo a pasta
   instalada e reinicie o Opera GX. Se necessário, carregue manualmente a
   pasta `extension` instalada. Não remova `manifest.key`.
5. No popup, configure destino, formato e qualidade e autorize o uso de conteúdo
   que você pode baixar. Depois basta um clique no YouTube.

A migração conserva uma pasta padrão anterior ou, se houver apenas essa
preferência, a última pasta selecionada. Somente em uma instalação sem pasta
anterior o host tenta identificar a pasta Músicas pela API Known Folder do
Windows. Uma pasta configurada que desapareceu não é substituída silenciosamente.
O histórico, as músicas e as preferências válidas são preservados na atualização.

## Compilar (apenas para desenvolvedores)

Pré-requisitos do computador de build:

- Windows 10 22H2 ou Windows 11 x64.
- [CPython 3.12 x64](https://www.python.org/downloads/windows/) com pip, Tcl/Tk e
  Python Launcher.
- [Inno Setup 6.3+](https://jrsoftware.org/isdl.php).
- Acesso HTTPS a PyPI e às releases oficiais do GitHub.

Dê dois cliques em `installer/Construir.cmd`, ou execute:

```powershell
py -3.12 scripts/build_windows.py
```

O build cria um venv com wheels fixados por hash, obtém ferramentas com SHA256
fixo para executar o teste real do host Windows e da conversão MP3, e então
**remove as ferramentas externas do payload do Setup**. O instalador publicado
contém nosso host, Python/Tcl/Tk, licenças e um utilitário de manutenção. As
ferramentas de mídia são adquiridas pela própria usuária diretamente dos
fornecedores durante a instalação, com progresso nativo e sem terminal.

Saídas:

- `dist/OperaMusicDownloader-Setup.exe`.
- `dist/SHA256SUMS.txt`.
- `work/windows-build/dist/OperaMusicDownloaderHost/build-self-test.json`.

O instalador inicia o utilitário de manutenção oculto para verificar os bytes
novamente e extrair somente arquivos conhecidos. Depois testa as ferramentas e
uma conversão MP3 real. Falhas impedem uma conclusão silenciosa. O log de
extração fica em `%LOCALAPPDATA%\OperaMusicDownloader\install-dependencies.log`.

## GitHub Actions e testes Windows

O workflow `.github/workflows/windows-build.yml` é executável manualmente no
repositório e gera o artifact `OperaMusicDownloader-Windows-x64`. Ele preserva a
compilação Windows e testa o Setup real em modo silencioso no runner, incluindo
as dependências obtidas pela instalação, conversão de mídia, framing Native
Messaging, versão/capacidades, persistência, migração de preferências 1.0 e pasta
Músicas pela API Windows. Os relatórios são anexados ao artifact.

Os testes do runner não comprovam a interface do Opera GX, o seletor de pasta
interativo nem o YouTube real. Esses testes continuam sendo de aceitação no
computador da usuária. O workflow não cria uma release pública automaticamente.
A imagem Windows e o Inno Setup do runner não são fixados por hash; o arquivo
final não tem assinatura Authenticode configurada.

## Native Messaging e encerramento seguro

O [manual oficial do Opera](https://help.opera.com/en/extensions/message-passing/)
documenta `chrome.runtime.connectNative` e o namespace
`Software\Google\Chrome\NativeMessagingHosts`. O instalador mantém o host
`com.opera_music_downloader` em HKCU nas visões 32/64 bits, com a origem exata
`chrome-extension://kinpjcjipphcbboncbjmodfiiblgfaoo/` e sem elevação.
Não há porta HTTP aberta. O host usa stdin/stdout; por isso o PyInstaller usa
`--console`. Alterar para `--noconsole` remove os streams necessários.

Fechar o Opera desconecta o host existente, que salva o estado e encerra os
processos de mídia. O instalador e o desinstalador verificam a exclusividade de
`host.lock` e solicitam fechar o navegador antes de prosseguir, sem encerrar
processos à força nem sobrescrever estado ativo.

## Remover e atualizar ferramentas

A remoção elimina os binários e licenças exatos registrados pelo utilitário,
assim como as configurações conhecidas do aplicativo e o registro Native
Messaging. Ela nunca varre pastas escolhidas para downloads e recusa apagar
arquivos de mídia mesmo que tenham sido colocados na pasta interna `tools`.
Remova a extensão manualmente em `opera://extensions`.

Para atualizar dependências, selecione releases oficiais exatas, confira os
hashes, revise `installer/dependencies.lock.json` e repita os testes. O código
nunca aceita `latest`, TLS desabilitado ou hash divergente. O build mensal BtbN
fixado tem retenção de dois anos pelo fornecedor; uma versão futura deve renovar
os links antes de sua expiração.

## Licenças e distribuição

Consulte `installer/THIRD-PARTY-NOTICES.txt`. O Setup não redistribui FFmpeg,
yt-dlp nem Deno: ele obtém os arquivos diretamente dos projetos oficiais. Isso
preserva suas funcionalidades, incluindo H.264 com libx264, sem alegar que links
genéricos equivalem a um pacote completo de fontes correspondentes GPL. Quem
alterar o build para agregar esses binários precisará cumprir as obrigações de
redistribuição dos componentes, incluindo fornecer fontes correspondentes quando
exigido. As licenças Python/Tcl/Tk/PyInstaller do payload são incluídas no Setup.

## Build publicado da versão 1.1.0

A [execução 42320573847](https://github.com/GabrielSQQ/Musicytextens-o/actions/runs/42320573847) concluiu compilação, instalação real e testes do host Windows com sucesso no commit `24faeea6bbe92521f5d6a54edabcf0c258569f70`. [Instalador para download](https://github.com/GabrielSQQ/Musicytextens-o/releases/download/v1.1.0/OperaMusicDownloader-Setup.exe). Consulte [TESTES.md](TESTES.md) para evidências e limitações de aceitação visual.

## Preparar uma release com os artefatos validados

O workflow manual `Prepare verified release assets` recebe a tag e o ID da execução Windows bem-sucedida. Ele confere o commit e os relatórios, verifica os hashes do Setup e dos ZIPs e envia os seis arquivos para uma release em rascunho. O token de escrita é temporário do próprio GitHub Actions; não se copia credencial para o projeto. O workflow não publica automaticamente: confira os arquivos e publique o rascunho após a validação. A execução Windows original permanece preservada.
