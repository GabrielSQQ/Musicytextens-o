# Opera Music Downloader 1.1.0

Extensão para Opera GX com download de um clique no YouTube e no YouTube Music, processado no computador por aplicativo auxiliar, yt-dlp e FFmpeg. A pasta, o formato e a qualidade são configurados no ícone da extensão; o botão do YouTube usa essas preferências sem abrir formulário ou seletor de pasta.

## Downloads

- [Baixar instalador Windows 1.1.0 (EXE)](https://github.com/GabrielSQQ/Musicytextens-o/releases/download/v1.1.0/OperaMusicDownloader-Setup.exe).
- [Baixar extensão atualizada (ZIP)](https://github.com/GabrielSQQ/Musicytextens-o/raw/refs/heads/main/downloads/OperaMusicDownloader-Extensao.zip).
- [Baixar código-fonte completo (ZIP)](https://github.com/GabrielSQQ/Musicytextens-o/raw/refs/heads/main/downloads/OperaMusicDownloader-Fonte.zip).
- [Versões e instalador Windows](https://github.com/GabrielSQQ/Musicytextens-o/releases).
- [SHA256 dos ZIPs e instalador](downloads/SHA256SUMS.txt).

O auxiliar também precisa da versão 1.1.0 para o fluxo de um clique. A extensão reconhece um auxiliar antigo e solicita atualização, evitando que ele abra a antiga janela de seleção a cada download. O instalador foi compilado e instalado com sucesso pelo workflow Windows, incluindo conversão real MP3 e verificação de persistência/migração. As evidências e limites estão no [relatório de testes](docs/TESTES.md).

## Atualizar a instalação que já funciona

1. Aguarde ou cancele os downloads ativos e feche o Opera GX.
2. Execute o novo `OperaMusicDownloader-Setup.exe` sobre a instalação anterior, no mesmo diretório. Não desinstale a versão anterior antes da atualização. A instalação precisa de internet para preparar automaticamente as ferramentas oficiais verificadas por SHA256; você não precisa instalar Python, FFmpeg ou yt-dlp manualmente.
3. Extraia a nova extensão. Para manter o cadastro do Opera, substitua os arquivos da pasta `extension` já carregada no navegador, mantendo a chave pública e o nome da pasta.
4. Abra `opera://extensions`, clique em **Recarregar** na extensão e recarregue as abas do YouTube.
5. Abra o ícone da extensão. Sua pasta anterior é reaproveitada. Confira o formato/qualidade e marque uma única vez que baixará apenas conteúdo autorizado. As alterações são salvas automaticamente.
6. Clique em **Baixar MP3** ou **Baixar MP4** no YouTube. O download começa usando a configuração salva.

A atualização mantém `state.json`, histórico e arquivos já baixados. Os modos antigos de perguntar/reutilizar pasta são migrados para um destino fixo: primeiro a pasta padrão anterior e, na falta dela, a última escolhida. Uma pasta configurada indisponível deve ser corrigida em **Alterar pasta**; o download não abre um seletor por conta própria.

Se a extensão ainda não estiver carregada, ative o modo de desenvolvedor em `opera://extensions`, escolha **Carregar sem compactação** e selecione a pasta `extension` extraída. Uma extensão não publicada exige essa etapa manual.

## Configurar uma vez, baixar com um clique

No popup da barra do navegador, **Configurações de download** reúne:

- **Pasta de destino / Alterar pasta:** seleção nativa do Windows. A escolha é gravada pelo auxiliar mesmo se o popup fechar ao perder o foco. Na primeira utilização, sem pasta anterior, o aplicativo tenta localizar a pasta Músicas pela API de pastas conhecidas do Windows.
- **Formato dos downloads:** MP3 ou MP4. Padrão MP3.
- **Qualidade:** MP3 em 128/192/320 kbps, padrão 320; MP4 até 360/720/1080p, padrão 720. As qualidades de cada formato são lembradas separadamente. Converter para 320 kbps não melhora o áudio original.
- **Autorização:** escolha persistente de baixar apenas conteúdo que você tem autorização para salvar.
- **Abrir pasta ao concluir:** opção persistente.

Os botões do YouTube mudam de MP3 para MP4 sem reiniciar a página. O clique mostra preparação, fila, andamento e sucesso/erro, impede duplicação acidental e não abre o popup automaticamente. A fila continua com o popup fechado. As mudanças de preferência valem para próximos pedidos; arquivos já enfileirados mantêm seu destino e formato.

O popup mantém progresso, cancelamento, histórico, tentativa após erro e abertura da pasta. Quando o vídeo só oferece uma resolução menor que a solicitada, o resultado informa a resolução real; não representa um vídeo de 360p como 1080p.

## Funcionamento, segurança e limites

- Native Messaging preservado: sem servidor HTTP de produção ou servidor próprio de conversão. O auxiliar valida origem, URLs de vídeos individuais, preferências e caminhos. Processos usam argumentos separados e nenhuma interpolação em shell.
- O auxiliar é a fonte das preferências. O cache completo da extensão é restrito a contextos confiáveis; páginas do YouTube recebem preferências sanitizadas e progresso apenas de seus próprios pedidos, sem caminhos locais.
- Conteúdo público autorizado somente. O aplicativo não solicita login, cookies, credenciais, DRM, proxies de desbloqueio ou desvio de restrições. A disponibilidade do YouTube pode mudar e exigir atualização do extrator.
- MP3 recebe artista/faixa quando esses campos existem no extrator; caso contrário, usa o título. Acentos são preservados e nomes inválidos/longos são tratados. Arquivos existentes não são sobrescritos. Metadados não inventam artista a partir do canal nem lançamento a partir da data de upload.
- YouTube Music usa os elementos de lista/reprodução expostos pela página e não desbloqueia conteúdo de assinatura.
- Encerrar o navegador, desativar a extensão ou reiniciar o computador interrompe o processamento; pedidos interrompidos são apresentados para tentar novamente. Fechar apenas o popup não interrompe a fila.
- Uma instância do auxiliar por usuário protege a fila. Feche a sessão anterior antes de usar outro perfil/navegador com a mesma extensão.
- Windows 10/11 x64 é o alvo. UNC direto e pastas com mais de 170 unidades UTF-16 não são aceitos; use um caminho mais curto ou unidade mapeada.
- O instalador não tem assinatura Authenticode comercial. Testes automatizados não substituem a aceitação visual numa versão específica do Opera GX/Windows.

## Desenvolvimento e testes

Estrutura existente preservada: `extension/`, `native-app/`, `installer/`, `scripts/`, `tests/` e `docs/`.

- [Arquitetura](docs/ARQUITETURA.md) e [protocolo 2](docs/PROTOCOL.md).
- [Compilar o instalador Windows](docs/BUILD-WINDOWS.md).
- [Testes executados e limitações](docs/TESTES.md).

```sh
python scripts/run_tests.py
python tests/browser_test.py --executable /caminho/para/chrome
python tests/native_browser_test.py --browser /caminho/para/chrome
python tests/full_download_test.py --browser /caminho/para/chrome
python scripts/package_release.py
```

O teste completo usa a extensão real, Native Messaging real e yt-dlp/FFmpeg reais com fontes sintéticas autorizadas. O seletor de teste é injetado e contado; apenas a ação explícita de configurar o destino pode chamá-lo. A lista de URLs aceita em produção permanece restrita ao YouTube.

Para desinstalar, use Aplicativos instalados do Windows e remova a extensão no Opera. O desinstalador remove aplicativo/registro/configurações conhecidas e preserva as mídias salvas. As dependências são atualizadas com versões/hashes revisados no build e preparadas automaticamente pelo instalador; não há atualização remota silenciosa durante downloads.

Projeto sem afiliação ao Opera ou ao YouTube. Use apenas conteúdo cujo download seja permitido.
