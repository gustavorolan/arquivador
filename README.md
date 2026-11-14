# Arquivador

Libera espaço em disco no Windows guardando pastas pouco usadas em ZIP. Quando você precisa de uma pasta, o Arquivador a abre como pasta normal, deixa você trabalhar nela e depois a zipa de novo.

Feito para quem tem SSD pequeno ou PC antigo e não quer apagar projetos velhos.

## Como funciona

1. **Compactar:** a pasta vira um ZIP em `~/Arquivo`. O programa verifica o ZIP (CRC, lista e tamanho dos arquivos) e confere se a quantidade de arquivos bate com a pasta. Só então apaga o original. Se algo falhar, nada é apagado.
2. **Abrir:** o ZIP é extraído no caminho original, como pasta comum. O ZIP fica como backup.
3. **Guardar de volta:** a pasta é compactada de novo com as suas alterações, verificada, e troca o ZIP antigo.
4. **Rotina:** uma tarefa agendada do Windows guarda de volta, de hora em hora, as pastas abertas sem alteração há 2 horas. Pasta em uso por algum programa é pulada.

Um `indice.json` em `~/Arquivo` registra cada item.

## Requisitos

- Windows 10 ou 11.
- Python 3.11 ou mais novo (somente biblioteca padrão, sem `pip install`).
- Microsoft Edge ou Chrome (para a janela do aplicativo).

## Uso

| Forma | Comando |
|---|---|
| Janela de aplicativo | `pythonw arquivador_app.pyw` |
| Interface no navegador | `arquivador.bat` |
| Janela tkinter (reserva) | `pythonw arquivador_gui.pyw` |
| Linha de comando | `python arquivador.py <comando>` |

Comandos: `listar`, `abrir <nome|id>`, `fechar <nome|id>`, `compactar <caminho> [--manter]`, `restaurar <nome|id>`, `rotina [--horas N]`, `instalar-rotina [--horas N]`, `remover-rotina`.

A interface web escuta só em `127.0.0.1` e exige um token gerado a cada execução.

## Pastas protegidas

Por padrão o programa nunca compacta `AppData`, `.claude` e a própria pasta `Arquivo`. Para proteger mais pastas, crie `~/Arquivo/protegidos.txt` com um caminho por linha (linhas com `#` são comentários).

Ele também só aceita caminhos dentro da sua pasta de usuário e ignora atalhos e junctions.

## Executável (`Arquivador.exe`)

A página de [Releases](../../releases) traz um `Arquivador.exe` gerado com PyInstaller. Ele abre a interface no navegador padrão.

Assinatura e confiança:

- O executável é assinado com um certificado **autoassinado** (`CN=Arquivador (autoassinado)`, arquivo `Arquivador.cer` na release). Isso garante que o arquivo não foi alterado depois de assinado, mas **o Windows não confia nele por padrão**, porque não vem de uma autoridade certificadora reconhecida.
- Por isso o Smart App Control e o SmartScreen podem bloqueá-lo. Nesse caso, use a versão em Python acima. Não desative as proteções do Windows por causa disto.
- Confira o SHA-256 e o thumbprint do certificado informados na release antes de executar.

Para gerar você mesmo: `pip install pyinstaller` e rode `build.bat`.

## O que esperar de ganho

Código e texto encolhem de 60% a 80%. Vídeos, fotos e arquivos já compactados quase não mudam; para esses, o ganho vem de tirar da frente, não de compactar.

## Arquivos

| Arquivo | Função |
|---|---|
| `arquivador.py` | Núcleo: compactar, verificar, abrir, guardar, rotina, CLI e servidor local |
| `index.html` | Interface |
| `arquivador_app.pyw` | Abre a interface em janela própria (Edge ou Chrome em modo aplicativo) |
| `arquivador_gui.pyw` | Janela tkinter alternativa |
| `arquivador.bat` | Abre a interface no navegador |
| `icone.py`, `arquivador.ico` | Gerador e arquivo do ícone |
| `build.bat` | Gera o `.exe` |
