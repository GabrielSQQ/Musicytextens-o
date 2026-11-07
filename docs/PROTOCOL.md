# Contrato Native Messaging v1

Host: `com.opera_music_downloader`. Apenas stdio, sem HTTP local. Frames JSON UTF-8 com comprimento uint32 little endian; máximo 1 MiB.

Requisição: `{ "id": "uuid", "type": "ping", "payload": {} }`.
Resposta: `{ "id": "uuid", "ok": true, "result": ... }` ou `{ "id": "uuid", "ok": false, "error": "mensagem em português" }`.
Evento assíncrono: `{ "event": "state", "data": SNAPSHOT }`.

SNAPSHOT: `{ "settings": {"folderMode":"ask", "defaultFolder":"", "lastFolder":"", "openFolder":false}, "jobs":[], "tools":{} }`.
Jobs: `{id,url,title,channel,thumbnail,format,quality,status,progress,speed,eta,error,path,createdAt}`. Progress 0–100, speed bytes/s e eta segundos (null quando indisponíveis). Status: queued, preparing, downloading, converting, completed, cancelled, error.

Comandos:
- `ping`: retorna `{version:"1.0.0"}`.
- `get_state`: retorna SNAPSHOT.
- `download`: payload `{url,title,channel,thumbnail,format:"mp3"|"m4a"|"opus"|"mp4",quality:128|192|320|360|720|1080,authorized:true}`; valida URL exclusivamente YouTube e autorização explícita; escolhe pasta nativa conforme preferências; retorna `{jobId}` ou `{cancelled:true}`. Sem caminho arbitrário recebido da página.
- `cancel`: payload `{jobId}`.
- `pick_folder`: abre janela nativa e retorna `{path}` ou `{cancelled:true}`; pode persistir lastFolder. Usado por configurações para escolher defaultFolder.
- `settings`: payload parcial com folderMode/defaultFolder/openFolder; retorna settings persistidas. lastFolder é somente leitura e é atualizado pelo picker nativo. Caminho padrão apenas diretório existente e absoluto.
- `open_folder`: payload `{jobId}` ou vazio para última/padrão; nunca aceita caminho da página.
- `clear_history`: remove somente jobs terminais; nunca remove arquivos de mídia.

O service worker permite a content scripts somente download/get_state/ping. Comandos de configuração, pasta e cancelamento ficam disponíveis somente às páginas da extensão. `chrome.runtime.sendMessage` usa o mesmo `{type,payload}` e resposta `{ok,result,error}`. O worker acrescenta id, mantém connectNative e retransmite eventos às páginas/popup com `{event:"state",data}`; guarda último estado em chrome.storage.local. Popup fechado não interrompe host.
