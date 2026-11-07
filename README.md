# Opera Music Downloader

## Baixar os arquivos

- [Baixar projeto completo (ZIP)](https://github.com/GabrielSQQ/Musicytextens-o/raw/refs/heads/main/downloads/OperaMusicDownloader-Fonte.zip)
- [Baixar somente a extensão (ZIP)](https://github.com/GabrielSQQ/Musicytextens-o/raw/refs/heads/main/downloads/OperaMusicDownloader-Extensao.zip)
- [Baixar este repositório como ZIP](https://github.com/GabrielSQQ/Musicytextens-o/archive/refs/heads/main.zip)
- [Hashes SHA256 dos dois arquivos originais](downloads/SHA256SUMS.txt)

Os ZIPs são os arquivos originais da entrega. A extensão depende do auxiliar local. O instalador Windows ainda precisa ser compilado: veja [BUILD-WINDOWS.md](docs/BUILD-WINDOWS.md).

Extensão Manifest V3 para Opera GX com botões no YouTube, fila real de downloads e aplicativo auxiliar local. Interface em português, tema escuro e seleção nativa de pasta no Windows. O áudio é processado por yt-dlp e FFmpeg no computador.

**Estado desta entrega:** código-fonte e extensão carregável. Este ambiente é Linux: o instalador `.exe` precisa ser gerado no Windows pelo processo incluído. Não há um instalador Windows compilado nesta entrega. Consulte [o relatório de testes](docs/TESTES.md) para distinguir o que foi executado do que ainda depende de Windows/Opera GX.

## Instalação para uso no Windows

Depois que uma pessoa responsável gerar `OperaMusicDownloader-Setup.exe` seguindo [BUILD-WINDOWS.md](docs/BUILD-WINDOWS.md):

1. Execute o instalador e siga as telas. Ele inclui o auxiliar, yt-dlp, FFmpeg, FFprobe e o runtime necessário, sem exigir Python da usuária.
2. No Opera GX, abra `opera://extensions` e ative **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta `extension` indicada ao final da instalação. Não selecione o ZIP.
4. Fixe a extensão na barra do navegador. Abra seu popup e verifique a conexão com o auxiliar.
5. Abra ou recarregue o YouTube. Clique em **Baixar MP3**, escolha formato e qualidade, confirme que tem autorização e clique em **Escolher pasta e baixar**.
6. Escolha a pasta na janela do Windows. Acompanhe o andamento no popup; pode fechá-lo durante o processamento.

A extensão não publicada é carregada manualmente: o instalador não força sua instalação no navegador. Não mova a pasta da extensão após carregá-la. Se o Opera bloquear extensões locais ou hosts por política administrativa, será necessário resolver essa política no próprio computador.

## Preferências e formatos

Nas configurações, escolha entre perguntar a pasta a cada download, repetir a última pasta ou usar uma pasta padrão. A pasta padrão é escolhida pelo diálogo nativo. É possível abrir a pasta ao terminar.

- Áudio: MP3 em 128, 192 ou 320 kbps; M4A e OPUS.
- Vídeo: MP4 com limite de 360p, 720p ou 1080p, conforme a fonte disponível.
- A conversão para um bitrate maior não recupera qualidade ausente no original.
- O nome usa artista e faixa quando a fonte fornece esses campos; do contrário usa o título disponível. Acentos são preservados e nomes inválidos do Windows são tratados.
- Arquivos existentes são preservados; colisões recebem outro nome. Um mesmo pedido ativo não é colocado duas vezes na fila.
- Falhas e cancelamentos aparecem no histórico; pedidos com erro podem ser enviados novamente.

## Limites conhecidos

- Downloads exigem internet e conteúdo público que você esteja autorizado a baixar. Não há fornecimento de cookies, credenciais, login, desbloqueio de acesso, DRM ou georrestrições. Vídeos protegidos ou indisponíveis podem falhar.
- Mudanças do YouTube podem exigir atualização do yt-dlp e dos seletores da extensão. Nenhum extrator garante compatibilidade permanente.
- Suporte a YouTube Music usa os elementos de lista e de reprodução acessíveis no DOM; não desbloqueia conteúdo restrito a contas ou assinaturas.
- Fechar o popup mantém a fila. Encerrar o navegador, desativar a extensão, reiniciar o computador ou perder o host interrompe o processamento; o aplicativo sinaliza os pedidos interrompidos e permite tentar novamente.
- Uma instância do auxiliar por usuário protege o estado da fila. Para usar a extensão em outro perfil ou navegador simultaneamente, encerre primeiro a sessão que iniciou o auxiliar.
- Progresso de download é medido pelo yt-dlp. A conversão é uma etapa separada, sem porcentagem fictícia. Qualidade e velocidade podem ficar indisponíveis durante preparação e conversão.
- Capa e metadados dependem de dados disponíveis e dos formatos suportados. O aplicativo não adivinha artista, álbum ou lançamento.
- Windows 10/11 x64 é o alvo do empacotamento. A execução no Opera GX, o diálogo nativo e a ausência de janelas de console exigem validação final nesse sistema.
- Destinos são pastas locais ou unidades mapeadas. Caminhos UNC (`\\servidor\pasta`) e diretórios com mais de 170 unidades UTF-16 não são aceitos nesta versão; nesse caso, escolha uma pasta mais curta ou mapeie a unidade de rede no Windows.
- O instalador gerado não tem assinatura comercial de código. O Windows pode exibir o nome de editor desconhecido.

## Estrutura e desenvolvimento

```text
extension/       Manifest V3, content script, popup e configurações
native-app/      host stdio, fila, validação e processamento real
installer/       instalador Windows e arquivos de apoio
scripts/         preparação e compilação
tests/           testes de protocolo, segurança, mídia e navegador
docs/            protocolo, arquitetura, testes e compilação
```

O [contrato de comunicação](docs/PROTOCOL.md) descreve os comandos. As [decisões de arquitetura](docs/ARQUITETURA.md) registram as fontes consultadas e o modelo de segurança. Instruções para compilar estão em [BUILD-WINDOWS.md](docs/BUILD-WINDOWS.md).

## Atualização e desinstalação

Para atualizar, gere e execute o novo instalador, encerre os downloads ativos e recarregue a extensão em `opera://extensions`. Mantenha a chave pública do manifesto para preservar a identidade da extensão. As dependências são atualizadas no processo de build com revisão de versões e hashes; a aplicação não executa atualizações remotas silenciosas.

Para remover, use **Aplicativos instalados** do Windows e desinstale Opera Music Downloader. Remova também a extensão em `opera://extensions`. O desinstalador remove o auxiliar e seu registro Native Messaging; não remove as músicas e os vídeos salvos nas pastas escolhidas. Veja detalhes de preferências e dados locais no guia de compilação.

Este projeto não é afiliado ao Opera ou ao YouTube. Use apenas conteúdo cujo download seja permitido.
