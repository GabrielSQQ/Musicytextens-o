# Native Messaging — protocolo 2 (aplicativo 1.1.0)

Host: `com.opera_music_downloader`. Stdio, JSON UTF-8 com comprimento uint32 little endian e limite de 1 MiB. Não existe servidor HTTP de produção.

Requisição: `{ "id": "uuid", "type": "get_state", "payload": {} }`.
Resposta: `{ "id": "uuid", "ok": true, "result": ... }` ou `{ "id": "uuid", "ok": false, "error": "mensagem em português" }`.
Evento: `{ "event": "state", "data": SNAPSHOT }`.

## Preferências e estado

O arquivo `state.json` do aplicativo auxiliar é a fonte confiável das preferências. O armazenamento da extensão guarda uma cópia para exibição; downloads validam o estado atual do host.

`ping` e `SNAPSHOT` contêm `protocolVersion:2`, `capabilities:{oneClickDownloads:true}` e `version:"1.1.0"`. O worker exige essa capacidade antes de enviar downloads. Um aplicativo 1.0 recebe instrução de atualização, sem receber o comando que antes poderia abrir o seletor de pasta.

```json
{
  "folderMode": "default",
  "defaultFolder": "C:\\Users\\Usuario\\Music",
  "lastFolder": "C:\\Users\\Usuario\\Music",
  "openFolder": false,
  "defaultFormat": "mp3",
  "mp3Quality": 320,
  "mp4Quality": 720,
  "authorizedDownloads": false
}
```

`folderMode` permanece para migração, com valor `default`. `lastFolder` é somente leitura. Formatos do fluxo normal: MP3/MP4. Valores: MP3 128/192/320 kbps, MP4 360/720/1080p. `authorizedDownloads` registra a escolha única no popup de baixar apenas conteúdo autorizado. Não há confirmação na página do YouTube.

Na migração, uma pasta padrão anterior é preservada; se não havia padrão, a última pasta é reutilizada. Somente quando nenhuma foi escolhida é consultada a pasta de Músicas conhecida pelo Windows. Pastas configuradas que se tornam inválidas produzem erro, sem abrir diálogo nem mudar o destino silenciosamente. Campos inválidos voltam individualmente a padrões seguros, preservando os demais dados.

`SNAPSHOT` também possui `jobs` e `tools`. Jobs contêm `id,url,title,channel,thumbnail,format,quality,status,progress,speed,eta,error,path,createdAt`, além de `actualHeight` e `resultNote` quando disponíveis. Status: queued/preparing/downloading/converting/completed/cancelled/error. Progresso mede download; conversão é uma etapa separada. `quality` é a preferência solicitada; `actualHeight` informa a resolução final verificada.

## Comandos

- `ping`: versão, protocolo e capacidades.
- `get_state`: estado atual completo para as páginas da extensão.
- `settings`: alteração parcial validada; persiste antes de informar sucesso. Alterar MP4 não apaga a qualidade MP3.
- `pick_folder`: somente ação explícita de configuração. Abre o diálogo nativo, salva `defaultFolder` e `lastFolder` no próprio host e retorna `{path}` ou `{cancelled:true}`. A gravação ocorre mesmo se o popup fechar ao perder o foco.
- `download`: recebe `{url,title?,channel?,thumbnail?}`. O host valida a URL, autorização salva e pasta e captura formato, qualidade, pasta e abertura ao concluir sob lock. Valores equivalentes enviados pelo chamador não sobrepõem as preferências. Retorna `{jobId}`. Nunca abre seletor de pasta.
- `cancel`: `{jobId}`; cancela pedido ativo ou na fila.
- `open_folder`: `{jobId}` concluído ou pasta configurada; não aceita caminho vindo da página.
- `clear_history`: remove registros terminais, preservando arquivos de mídia.

Pedidos enfileirados mantêm suas preferências. Alterações posteriores valem para próximos pedidos. Falhas de persistência revertem a mudança em memória e não são apresentadas como sucesso.

## Fronteira com content scripts

`chrome.runtime.sendMessage` usa `{type,payload}` e resposta `{ok,result,error}`. Somente páginas da extensão recebem estado completo e comandos de configuração, cancelamento e pasta. Content scripts podem pedir estado sanitizado, ping e download com URL normalizada, mediante clique real.

Eventos para content scripts: `{event:"content_state",data:{preferences,connection,jobs}}`. Preferências expostas: `defaultFormat,mp3Quality,mp4Quality,authorizedDownloads,destinationConfigured`. Não são enviados caminhos locais. Jobs são limitados aos pedidos iniciados pelo documento de destino. Preferências e progresso são retransmitidos às abas inscritas, sem recarregar o YouTube.

O cache local da extensão fica restrito a contextos confiáveis. Content scripts não podem alterar o destino ou afirmar autorização por mensagem. A origem nativa mantém a identidade fixa da extensão; o framing usa escrita completa mesmo quando o sistema aceita apenas parte dos bytes.
