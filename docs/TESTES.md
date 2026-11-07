# Relatório de validação

Executado em 6 de novembro de 2026, em Linux, Python 3.12, Node.js, Chrome for Testing 151.0.7922.34, yt-dlp 2026.10.26 e FFmpeg/FFprobe 7.1.5. Os binários Windows fixados no build têm suas próprias versões e ainda precisam ser executados no Windows.

**Resultado: 32 testes Python, 6 testes JavaScript e 8 testes de navegador passaram.** Dois testes de integração adicionais passaram: comunicação Native Messaging com reinício do navegador e download completo da interface até um MP3 real. A extensão foi carregada de verdade no Chrome for Testing. Nenhum teste aqui foi executado no Opera GX, no Windows ou no YouTube real.

O Chromium do sistema aplica uma política que bloqueia extensões locais. Essa política foi preservada; os testes usaram uma instalação separada do Chrome for Testing em perfil temporário. As páginas com aparência de YouTube são fixtures sintéticas, sem consulta à plataforma real.

## Cobertura dos requisitos

| Verificação solicitada | Resultado e limite |
| --- | --- |
| 1. Carregamento da extensão | Passou no Chrome for Testing: manifesto MV3, identidade fixa, worker, popup e configurações. Opera GX pendente. |
| 2. Compatibilidade das APIs | Messaging, storage e service worker executados em Chromium. Native Messaging documentado pelo Opera. Notificações visíveis do Windows pendentes. |
| 3. Inserção de botões | Passou em fixtures de pesquisa, reprodução e listas do YouTube Music com a extensão carregada. |
| 4. Navegação dinâmica | Passou: novos resultados, 20 itens carregados, renderizadores reutilizados, mudança de vídeo e prevenção de botões duplicados. |
| 5. Comunicação local | Passou: extensão real → stdio → aplicativo real, origem fixa, comandos, preferências e reinício do navegador. |
| 6. Janela nativa de pasta | Implementada com `tkinter.filedialog.askdirectory`, que usa o seletor nativo no Windows. Janela Windows não executada neste ambiente. Testes com picker injetado validaram cancelamento, escolhas e manutenção da resposta durante o diálogo. |
| 7. Processamento autorizado | Passou com áudio senoidal e vídeo sintéticos gerados localmente. Download HTTP local, extração, conversão, validação e publicação reais. |
| 8. MP3 | Passou em 128, 192 e 320 kbps. FFprobe confirmou codec, bitrate, duração e título. M4A/AAC e OPUS também passaram. |
| 9. Cancelamento | Passou: fila, pedido ativo e processo real no Linux. O cancelamento continuou respondendo durante um picker de teste bloqueado. A implementação `taskkill /T` exige teste Windows. |
| 10. Erros | Passou: URL/origem/formato inválidos, autorização ausente, frames truncados/grandes, caminhos relativos, colisão de nome, fechamento de pipes e retomada após interrupção. |
| 11. Sem terminal visível | Processos Windows configurados com `CREATE_NO_WINDOW`, instalador com `SW_HIDE`, host preservando stdio. Verificação visual no Opera GX/Windows pendente. |
| 12. Preferências persistidas | Passou nos testes do aplicativo e através de um reinício real do navegador/host. |

Também passaram: proteção contra cliques sintéticos da página, título malicioso tratado como texto, comandos de configuração restritos às páginas da extensão, caminhos/histórico omitidos das respostas a content scripts, extração ZIP segura e checagem de hashes do build.

## Arquivos reais gerados

Os testes de mídia geraram e inspecionaram oito saídas:

- MP3 a 128, 192 e 320 kbps.
- M4A com áudio AAC e OPUS com áudio Opus.
- MP4 com vídeo H.264 e áudio AAC em 360p, 720p e 1080p, escolhidos a partir de três rendições locais realmente disponíveis.

Os testes preservam arquivos existentes, tratam nomes acentuados e verificam limpeza de arquivos parciais na alternativa de cópia.

A [amostra MP3 de 192 kbps](evidencias/Tom-autorizado-192kbps.mp3) contém um tom sintético de 440 Hz com cerca de dois segundos. Ela foi gerada pelo mesmo `Runner`, passando por yt-dlp, FFmpeg e FFprobe. O [resultado da inspeção](evidencias/amostra-media.json) registra o arquivo de 49.848 bytes, bitrate do fluxo de 192.000 bits/s e as etapas reais de download e conversão. Não é uma música de terceiros.

## Teste completo da interface ao arquivo

O [relatório de ponta a ponta](evidencias/full-download-report.json) registra um clique real no botão da fixture, seleção real da autorização, envio pelo service worker, Native Messaging e produção de `Fonte autorizada.mp3`. A pasta padrão é configurada antes do teste; o popup e a página são fechados enquanto o auxiliar termina o processamento. O popup é reaberto após a publicação e mostra o download concluído.

Nesse teste, somente o construtor do `Runner` recebe um resolvedor para a fonte HTTP de loopback. O host de teste é criado num diretório temporário; os arquivos do produto, a validação de URLs de produção e o protocolo não são modificados. O teste não alega acesso ao YouTube nem abertura do seletor Windows.

Outras evidências:

- [Resultados do navegador](evidencias/browser-report.json).
- [Native Messaging e persistência após reinício](evidencias/native-browser-report.json).
- [Log da suíte Python/JavaScript](evidencias/unit-tests.txt).
- [Teste adicional isolado de payloads](evidencias/browser-injected-report.json): 7 passaram, 1 foi pulado por exigir extensão real. Esse modo usa um dublê de `chrome.runtime` e não entra na contagem de testes com a extensão real.

## Como repetir como desenvolvedor

Prepare Python 3.12, Node.js, FFmpeg/FFprobe e o yt-dlp oficial no PATH do ambiente de testes. Para os testes de mídia usados aqui, a versão foi `yt-dlp[default]==2026.10.26`. Essas dependências de desenvolvimento não são exigidas da usuária do instalador final.

Na raiz do projeto:

```sh
python scripts/run_tests.py
```

Para o navegador, instale Playwright no ambiente de desenvolvimento e use uma distribuição Chromium que permita carregar extensões locais:

```sh
python tests/browser_test.py --executable /caminho/para/chrome
```

Os dois testes de integração seguintes usam registro Linux em perfil temporário. Eles não alteram o perfil normal do navegador nem arquivos no diretório pessoal:

```sh
python tests/native_browser_test.py --browser /caminho/para/chrome
python tests/full_download_test.py --browser /caminho/para/chrome
```

Se yt-dlp/FFmpeg/FFprobe não estiverem disponíveis, a suíte de mídia será explicitamente pulada; esse resultado não equivale a validar a conversão. `scripts/run_tests.py --browser` também aceita o executável via variável `OMD_TEST_BROWSER`.

## Aceitação que falta no Windows

Siga o procedimento em [BUILD-WINDOWS.md](BUILD-WINDOWS.md) para compilar e instalar numa máquina Windows 10/11 x64. Verifique o seletor de diretório em outro disco, os três modos de pasta, abertura do Explorer, notificações, ausência de console, cancelamento durante download/conversão e remoção do aplicativo sem apagar mídias. Faça downloads apenas de vídeos seus ou cujo download esteja autorizado.

A publicação de uma versão binária ainda requer validar o instalador e as ferramentas Windows, conferir os termos de redistribuição dos componentes e decidir sobre assinatura de código. O projeto entrega o processo de build; não inclui um `.exe` previamente compilado.
