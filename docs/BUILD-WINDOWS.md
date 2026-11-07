# Gerar o instalador no Windows

O instalador final terá o nome `OperaMusicDownloader-Setup.exe`. A pessoa que
utilizar esse instalador não precisará instalar Python, yt-dlp, FFmpeg ou Deno.

Este ambiente de desenvolvimento é Linux: o executável Windows e o instalador
não foram compilados nem testados aqui. Os scripts abaixo são a etapa de build
para um desenvolvedor, não a instalação destinada à usuária final.

## Pré-requisitos de compilação

1. Windows 10 22H2 ou Windows 11, x64.
2. [CPython 3.12 x64](https://www.python.org/downloads/windows/), com pip, Tcl/Tk
   e o Python Launcher. Essas ferramentas são necessárias apenas no computador
   de compilação.
3. [Inno Setup 6.3 ou superior](https://jrsoftware.org/isdl.php), instalado em seu caminho
   padrão, ou informe `--iscc` ao script.
4. Acesso HTTPS a PyPI e aos repositórios oficiais de releases do GitHub.

## Compilar

Dê dois cliques em `installer/Construir.cmd`. Ou execute, como desenvolvedor:

```powershell
py -3.12 scripts/build_windows.py
```

O script cria um ambiente virtual em `work/windows-build`, instala os wheels de
build com versões e hashes fixos, baixa ferramentas oficiais com SHA256 fixo,
empacota o host com PyInstaller, executa seu teste real de FFmpeg/FFprobe e
dependências, e compila o instalador com Inno Setup. Não baixa executáveis
durante a instalação da usuária final. Um hash incorreto interrompe o build.

Arquivos gerados:

- `dist/OperaMusicDownloader-Setup.exe`.
- `dist/SHA256SUMS.txt`.
- `work/windows-build/dist/OperaMusicDownloaderHost/build-self-test.json`.

Os binários intermediários não são distribuídos neste repositório. O instalador
usa o ID estável registrado em `extension/extension-id.txt`, derivado da chave
pública de `manifest.json`. Não remova essa chave em uma atualização.

## GitHub Actions

O workflow `.github/workflows/windows-build.yml` pode ser executado manualmente
em um repositório contendo o projeto. Ele compila no runner Windows 2022 e
disponibiliza o instalador como artifact privado do workflow conforme as
permissões do repositório. Não cria releases públicas nem publica o projeto.
O runner precisa incluir Inno Setup 6; o script para se a ferramenta estiver
ausente. A imagem Windows e o compilador Inno Setup não são reprodutíveis por
hash neste projeto; versões/assinaturas do compilador devem ser fixadas também
em um pipeline de lançamento auditado.

## Registro Native Messaging no Opera GX

O [manual oficial do Opera](https://help.opera.com/en/extensions/message-passing/)
documenta Native Messaging via `chrome.runtime.connectNative` e o namespace
Windows `Software\Google\Chrome\NativeMessagingHosts`. A implementação registra
o host `com.opera_music_downloader` em HKCU nas duas visões 32/64 bits, sem
elevação. O manifesto só permite a origem exata da extensão.

O ID é estável. O instalador escreve o caminho absoluto do executável e inclui
somente `chrome-extension://<id>/` em `allowed_origins`. Ele não abre portas HTTP
e não usa um servidor de download. O framing binário usa stdin/stdout; por isso
o host PyInstaller é compilado como `--console`. Não altere para `--noconsole`,
que remove os streams necessários. O navegador inicia o host em segundo plano;
a ausência de console visível ainda precisa ser confirmada no Opera GX real.

## Teste do pacote

Em uma máquina Windows de teste, com Opera GX fechado:

1. Instale o Setup.exe sem privilégios de administrador.
2. Verifique se o instalador informa sucesso no teste do aplicativo. Esse teste
   inclui conversão de uma amostra local autorizada para MP3; não contata o
   YouTube. Uma falha é exibida claramente no instalador.
3. Siga `LEIA-ME.html`: carregue manualmente a pasta instalada `extension` em
   `opera://extensions` e reinicie o Opera GX.
4. Abra o popup e confirme a conexão. Escolha uma pasta, faça um download de
   conteúdo seu/autorizado, feche o popup e confirme a conclusão depois.
5. Teste cancelamento, pasta em outro disco, erro de vídeo indisponível,
   preferências persistentes, atualização e desinstalação.
6. Confirme que a desinstalação remove somente o aplicativo/configuração e
   deixa as músicas intactas. Remova manualmente a extensão no Opera GX.

O teste de dependências não comprova a seleção de pasta Win32, carregamento no
Opera GX, integração com o YouTube real nem ausência de terminal nessa versão
do navegador. Essas verificações exigem o teste de aceitação no Windows.

## Atualizar dependências

Atualizações são deliberadas: selecione uma release oficial exata, confira seus
hashes e proveniência, altere `installer/dependencies.lock.json`, revise as
licenças e repita os testes. O script nunca substitui versões por `latest`,
nunca desliga TLS e nunca aceita um arquivo com hash divergente. O lock inclui
um build mensal do BtbN, retido por dois anos conforme a política do fornecedor;
mantenha cópia verificada do cache para builds posteriores a esse prazo.

Recompile e reinstale o pacote completo. O instalador preserva o diretório de
preferências durante a atualização. A remoção apaga somente nomes conhecidos
de configuração, sem varrer diretórios escolhidos para músicas.

## Redistribuição

Consulte `installer/THIRD-PARTY-NOTICES.txt`. O FFmpeg selecionado usa GPL com
libx264. Para publicar um pacote binário, o distribuidor deve fornecer os fontes
correspondentes completos, incluindo bibliotecas vinculadas e scripts, preservar
todas as licenças e cumprir os termos aplicáveis. O build aqui preserva avisos,
mas não gera um espelho completo dos fontes de terceiros. A entrega atual é de
código-fonte; não inclui um instalador binário redistribuído. Não há assinatura
Authenticode configurada; um lançamento deve usar o certificado do distribuidor.
