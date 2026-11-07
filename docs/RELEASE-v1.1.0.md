# Opera Music Downloader 1.1.0 — download com um clique

Atualização do projeto existente: configure o destino, formato e qualidade pelo ícone da extensão e clique em Baixar MP3/MP4 no YouTube. O download comum não abre modal, confirmação ou seletor de pasta.

- Pasta e preferências persistem no auxiliar, com migração da instalação anterior.
- MP3/320 kbps e MP4/720p são os padrões; cada formato mantém sua qualidade própria.
- Autorização de conteúdo é confirmada uma única vez no popup.
- Fila, progresso, cancelamento e histórico continuam funcionando com o popup fechado.
- Botões mudam de MP3/MP4 sem reiniciar a página e informam erros ou ajustes de resolução.

## Arquivos

- OperaMusicDownloader-Setup.exe: instalador Windows 10/11 x64. Instala o auxiliar e prepara automaticamente ferramentas oficiais, com verificação SHA256. É necessária conexão à Internet na instalação; não é necessário instalar Python/FFmpeg/yt-dlp manualmente.
- OperaMusicDownloader-Extensao.zip: extensão Manifest V3 versão 1.1.0 com identidade preservada.
- OperaMusicDownloader-Fonte.zip: código completo, testes e instruções de build.
- SHA256SUMS.txt: hashes dos três arquivos principais.
- windows-build-self-test.json e windows-install.json: evidências produzidas no runner Windows.

## Atualizar sem perder configurações

1. Termine/cancele os downloads e feche o Opera GX.
2. Execute o Setup 1.1.0 sobre a instalação existente, no mesmo diretório. Não desinstale antes de atualizar.
3. Substitua os arquivos da extensão na pasta já carregada. Em opera://extensions clique em Recarregar e recarregue as abas do YouTube.
4. Abra o ícone da extensão, confira a pasta e marque a autorização persistente uma única vez. Depois use os botões do YouTube diretamente.

A pasta e o histórico existentes são preservados. Arquivos de música/vídeo não são excluídos. Se o auxiliar ainda for 1.0, a extensão informa a necessidade de atualização sem acionar o antigo seletor de pasta.

## Verificação

Fluxo real verificado com extensão, Native Messaging e yt-dlp/FFmpeg usando mídia sintética autorizada: MP3/320, MP4 com fallback de resolução corretamente informado e MP3/192 em sequência; popup fechado; pasta com espaços/acentos; preferências e histórico preservados após reiniciar o navegador. Instalação e testes do host Windows constam nos relatórios anexos.

A integração visual numa versão específica do Opera GX, o YouTube real e as notificações visíveis do Windows não foram testados neste ambiente. O instalador não tem assinatura Authenticode comercial. Utilize apenas conteúdo autorizado e sem DRM/restrições de acesso.
