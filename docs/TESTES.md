# Validação da atualização 1.1.0

A atualização foi aplicada ao projeto existente. O fluxo principal foi testado com a extensão carregada de verdade no Chrome for Testing 151, Native Messaging, aplicativo Python, yt-dlp 2026.10.26 e FFmpeg/FFprobe 7.1.5 no Linux. As páginas do YouTube e as fontes de mídia são sintéticas e autorizadas.

**Resultado local:** 46 testes Python, 12 testes de segurança JavaScript e 8 cenários com a extensão real passaram. No modo isolado de interface, 11 cenários passaram com um dublê de comunicação explicitamente identificado. Os 3 cenários exclusivos desse modo aparecem como pulados na execução com extensão real e não são contados como testes de Native Messaging.

Duas integrações adicionais passaram: preferências/migração com reinício real do navegador e download completo com um clique. Nenhum resultado Linux é apresentado como execução no Opera GX ou no YouTube real. A validação Windows é registrada separadamente abaixo.

## Critérios da atualização

| Requisito | Evidência executada |
| --- | --- |
| Salvar pasta no popup | Ação explícita Alterar pasta enviada ao host; o picker de teste foi chamado exatamente uma vez. A pasta foi salva mesmo fechando o popup antes da resposta. |
| Reiniciar sem perder pasta | Navegador e host foram encerrados e reabertos; destino, formato, qualidades e autorização persistiram. |
| MP3/320 | Clique único produziu MP3 real com bitrate de fluxo de 320.000 bits/s, confirmado por FFprobe. |
| MP4/720 | Preferência salva no popup e botão atualizado sem recarregar. Fonte somente 360p gerou MP4 H.264/AAC em 360p, com mensagem de ajuste correta. Testes de mídia separados confirmaram 720p e 1080p quando essas rendições estavam disponíveis. |
| Nenhum modal ao clicar no YouTube | Clique real no botão enviou metadados diretamente; nenhum diálogo/formulário foi inserido. Não houve chamada de picker durante downloads. |
| Salvar no destino configurado | Os três arquivos reais ficaram na pasta de teste com espaços, acentos, `&` e colchetes. |
| Downloads sequenciais | MP3/320, MP4 solicitado720 e MP3/192 concluídos em sequência pela interface. |
| Popup fechado | Todos os downloads foram iniciados e concluídos com o popup fechado. |
| Alteração de preferências | Formato e qualidade alterados no popup afetaram os próximos downloads; botões refletiram MP3/MP4 sem reiniciar a página. Pedidos já enfileirados preservaram a configuração capturada. |
| Migração | Estado 1.0 com última pasta e histórico foi carregado pela versão1.1. Pasta, histórico e arquivos anteriores preservados; campos novos receberam padrões seguros. |
| Comunicação existente | Extensão real e host real trocaram frames e verificaram protocolo2, origem fixa e persistência. Host antigo/capacidade em cache não autoriza encaminhar um download. |
| Testes anteriores | A suíte existente foi executada e adaptada onde o modal deixou de ser um comportamento válido. URL/origem, cancelamento, nomes seguros, colisão, pipes e conversão continuam cobertos. |

## Evidências

- [Fluxo real de um clique e três arquivos gerados](evidencias/full-download-report.json).
- [Migração e persistência após reinício do navegador](evidencias/native-browser-report.json).
- [Navegador com extensão carregada](evidencias/browser-report.json).
- [Interface isolada com dublê de runtime](evidencias/browser-injected-report.json).
- [Log dos testes Python/JavaScript](evidencias/unit-tests.txt).

O fluxo completo injeta somente uma fonte HTTP de loopback no construtor do Runner e um picker de teste que registra chamadas. A lista de URLs de produção continua limitada ao YouTube. O teste percorre content script → service worker → stdio → fila → yt-dlp → FFmpeg → FFprobe → arquivo publicado, usando cliques de usuário reais do navegador.

O relatório registra MP3/320, MP4/H.264 com resolução real e MP3/192. A amostra `Tom-autorizado-192kbps.mp3` preservada em `evidencias/` pertence à validação inicial do pipeline; não é apresentada como nova configuração padrão nem como música de terceiros.

## Segurança e regressões

Passaram verificações de autorização persistente não substituível por parâmetros da página, captura atômica das preferências, pasta inválida sem picker, falha de persistência com reversão de estado, origem estrita, cliques sintéticos bloqueados, cache restrito, assinaturas de documento e progresso apenas dos próprios pedidos.

A interface foi verificada a 400px, com títulos longos e histórico rolável sem overflow horizontal. Desconexão após confirmação do pedido restaura o botão e informa erro, sem deixar a página presa em carregamento.

## Windows e instalador

O workflow [Build Windows installer](https://github.com/GabrielSQQ/Musicytextens-o/actions/workflows/windows-build.yml) compila o host e o Setup no Windows, converte uma amostra real para MP3, instala o Setup em diretório de teste e verifica o host instalado, migração e preferências. O resultado dessa execução será incluído na publicação da versão.

Permanecem dependentes de aceitação no computador da usuária: interação visual com o diálogo nativo no Opera GX, integração com o YouTube real, notificações visíveis do Windows e ausência visual de console na versão específica do Opera GX. O build usa execução oculta e não exige terminal da usuária.

## Repetir os testes

Prepare o ambiente de desenvolvimento com Python3.12, Node.js, yt-dlp e FFmpeg/FFprobe no PATH. O instalador final prepara as dependências automaticamente; esses pré-requisitos se aplicam somente ao desenvolvimento.

```sh
python scripts/run_tests.py
python tests/browser_test.py --executable /caminho/para/chrome
python tests/native_browser_test.py --browser /caminho/para/chrome
python tests/full_download_test.py --browser /caminho/para/chrome
```

Os dois últimos scripts registram o host em perfil Linux temporário. Não alteram o perfil de uso normal. Se as ferramentas de mídia estiverem ausentes, os testes correspondentes são explicitamente pulados; esse resultado não comprova processamento real. O procedimento Windows está em [BUILD-WINDOWS.md](BUILD-WINDOWS.md).
