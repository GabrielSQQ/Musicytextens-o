# Arquitetura e compatibilidade

Investigação realizada em 6 de novembro de 2026.

## Escolha: Native Messaging

A [documentação oficial do Opera](https://help.opera.com/en/extensions/message-passing/) documenta `nativeMessaging`, `runtime.connectNative`, comunicação por stdin/stdout e o registro Windows sob `SOFTWARE\Google\Chrome\NativeMessagingHosts`. Portanto, a implementação prioriza Native Messaging. Não é necessário abrir porta localhost, criar servidor HTTP ou distribuir token de autenticação para páginas web.

O host se chama `com.opera_music_downloader`. Seu manifesto permite apenas a origem da extensão com identidade fixa `kinpjcjipphcbboncbjmodfiiblgfaoo`. A chave pública em `manifest.json` estabiliza o ID quando a extensão é carregada sem compactação. Essa chave não é um segredo nem uma assinatura comercial.

A [documentação Chromium atual](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging) explica registro por usuário, framing e limites. O [ciclo de vida do service worker](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle) documenta que `connectNative` mantém o worker ativo; em falhas, o estado persistido permite informar a interrupção. A implementação mantém uma conexão para a fila, independentemente da duração do popup.

Isso confirma compatibilidade de API documentada; não substitui teste executado numa versão específica do Opera GX para Windows. Veja [TESTES.md](TESTES.md).

## Fluxo

```mermaid
sequenceDiagram
    actor U as Usuária
    participant C as Content script no YouTube
    participant W as Service worker
    participant H as Aplicativo auxiliar
    participant P as yt-dlp / FFmpeg
    U->>W: Configurar pasta, formato, qualidade e autorização uma vez no popup
    W->>H: Salvar preferências (diálogo só em Alterar pasta)
    U->>C: Clicar uma vez em Baixar MP3/MP4
    C->>W: download (URL e metadados)
    W->>W: Validar origem e comando
    W->>H: JSON por Native Messaging
    W->>H: Conferir capacidade do protocolo 2 na conexão atual
    H->>H: Validar URL, autorização salva e pasta
    H->>H: Capturar preferências e persistir pedido na fila
    H->>P: Executar com lista de argumentos
    P-->>H: Progresso real e resultado
    H-->>W: Eventos de estado
    W-->>U: Popup e notificação final
```

## Fronteiras de confiança

- Sem `externally_connectable`, `eval`, script remoto ou execução de comandos recebidos como texto.
- URLs são normalizadas para vídeos individuais do YouTube. URLs de outros sites, credenciais na URL, playlists como unidade de download e entradas locais não são aceitas pelo protocolo de produção.
- A página não envia caminhos de arquivos, formato, qualidade ou autorização. A seleção de pasta ocorre somente em ação explícita de configuração no auxiliar; comandos de preferência ficam restritos às páginas da extensão.
- O aplicativo é a fonte de preferências. O cache local completo é bloqueado para content scripts; atualizações de formato e progresso enviadas à página omitem caminhos e pedidos de outros documentos.
- O host usa argumentos separados e `shell=False`. yt-dlp ignora configurações externas; não recebe cookies ou credenciais.
- As ferramentas vêm de fontes oficiais identificadas no lock. O instalador baixa e verifica hashes automaticamente, sem redistribuir esses binários no Setup. O build também verifica ferramentas temporárias antes de validar o host.
- stdout é reservado ao protocolo Native Messaging; diagnósticos usam stderr. No Windows, stdin e stdout operam em modo binário.
- As preferências e o histórico ficam apenas no computador. Consultas à plataforma e aos seus servidores de mídia são necessárias ao download; não há servidor próprio de coleta ou conversão.

## Dependências e geração do instalador

O [yt-dlp](https://github.com/yt-dlp/yt-dlp) faz extração e download. FFmpeg/FFprobe convertem, mesclam e inspecionam os arquivos. Distribuições oficiais de yt-dlp incluem os componentes EJS; o [runtime JavaScript recomendado](https://github.com/yt-dlp/yt-dlp/wiki/EJS) é preparado junto às demais ferramentas. O projeto não ativa obtenção dinâmica de componentes externos.

O host Python é empacotado no Windows. O [PyInstaller não é um compilador cruzado](https://pyinstaller.org/en/stable/): o ambiente Linux executa os testes locais e o workflow GitHub Actions executa a compilação Windows. O resultado efetivo da compilação e dos testes do instalador está em [TESTES.md](TESTES.md).
