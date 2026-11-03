# Changelog

Todas as alterações notáveis a este projecto.
*All notable changes to this project.*

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
a numeração segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

<sub>Created by Redfox using Claude</sub>

---

## [2.0.0] — 2026-11-03

Interface gráfica em vez da interface de texto, exportação de máquinas para OVF,
e quatro correcções que a 1.0 escondia. Três aplicações independentes, como
antes, com **857 testes** a passar (276 + 294 + 287).

### Interface gráfica

- **A TUI (Textual) foi substituída por uma janela (Tkinter).** O Tkinter vem
  com o Python do python.org em Windows e macOS, e por isso a aplicação passou a
  ter **uma única dependência do `pip`** (`pyvmomi`). Tema escuro e claro.
- O ecrã de ligação pergunta primeiro **o tipo de servidor — ESXi ou vCenter** —
  sugere o utilizador habitual e, depois de ligar, compara a escolha com o que o
  servidor diz que é, perguntando antes de continuar se não coincidir.
- O separador **Máquinas** abre filtrado nas **ligadas**, com procura e selecção
  múltipla. As operações vivem num menu **Acções** por separador (o mesmo do botão
  direito), com as recusadas pela guarda **desactivadas, não escondidas**.
- As tabelas ordenam por qualquer coluna (números como números, IPs como IPs) e
  **mantêm a selecção** quando o inventário se actualiza.
- O certificado fixado aparece no cabeçalho do painel; a impressão digital no
  diálogo de confiança vem em duas linhas, com botão para copiar.
- Em Windows, o `EXECUTAR.bat` abre a janela **sem consola atrás**, e a janela
  declara-se preparada para ecrãs de alta densidade.

### Exportação para OVF

- Novo separador **Exportação** e diálogo **Exportar máquinas…**: cada máquina
  vai para uma pasta com o `.ovf`, os discos *stream-optimized*, um manifesto
  **SHA-256** e um `LEIA-ME.txt`; na raiz do destino fica o relatório do lote em
  texto e JSON.
- **Sem `ovftool`**: `ExportVm` → `HttpNfcLease` → descarga → `CreateDescriptor`,
  com a concessão mantida viva e o SHA-256 calculado durante a descarga.
- Máquinas ligadas: **só com autorização explícita e ENCERRAR escrito**, são
  encerradas pelo convidado, exportadas uma a uma e voltam a ser ligadas — ou
  ficam desligadas, para a manutenção do anfitrião. **Nunca se desliga à força.**
- Recusadas antes de confirmar, com a razão: sem Tools a correr, suspensas,
  anfitrião sem resposta, e **o próprio vCenter da sessão**.
- Uma exportação falhada ou cancelada **não deixa ficheiros a meio**, aborta a
  concessão e volta a ligar a máquina que tinha sido encerrada.
- A transferência dos discos vai directa ao anfitrião, **sem o proxy** da
  máquina, e só envia o cookie da sessão a um certificado confirmado — o da
  sessão, ou o que o vCenter anunciou na concessão.

### A assinatura

- O crédito e o autor vivem em `branding.py` e estão **selados**: alterá-los
  impede o arranque (código de saída **4**), e a janela confirma que o rodapé o
  mostra. Aparece no título, no rodapé, no *Sobre*, nos relatórios, no
  `LEIA-ME.txt` de cada exportação e no registo.

### Correcções

- **ESXi geridos por vCenter não ligavam directamente.** O certificado deles é
  emitido pela VMCA; fixado sem `VERIFY_X509_PARTIAL_CHAIN`, o aperto de mão
  falhava sempre, mesmo depois de a impressão digital ser aceite.
- **O separador dos anfitriões vinha vazio em servidores com sensores** (um HPE
  com a imagem do fabricante, por exemplo): a leitura dos sensores percorria
  `systemHealthInfo` como se fosse a lista, e a falha levava todos os anfitriões
  com ela. Agora lê `numericSensorInfo`, compara a `key` do estado, e um objecto
  ilegível já não esvazia a lista.
- **O diálogo do certificado mostrava o sujeito, o emissor e a validade em
  branco**, porque o `getpeercert()` só os dá para certificados validados. Agora
  lêem-se do próprio DER.
- A tabela de privilégios do README dizia `GuestControl` para encerrar e
  reiniciar pelo convidado; o vSphere pede `PowerOff` e `Reset`.

### Removido

- A interface de texto (Textual) e as verificações de terminal que só ela usava.
- A definição `confirm_destructive`, que nunca foi lida por nada.

---

## [1.0.0] — 2026-09-08

Primeira versão. Três aplicações independentes — `Windows/`, `Linux/` e
`macOS/` — com **691 testes** a passar (235 + 225 + 231).

### Monitorização

- Inventário completo de **vCenter** ou de um **anfitrião ESXi** ligado
  directamente: anfitriões, máquinas, datastores, snapshots e alarmes, lidos
  numa chamada por tipo através do `PropertyCollector` do vSphere.
- Painel com cinco separadores, o primeiro dos quais é o dos achados — porque a
  pergunta que traz alguém aqui é "está tudo bem", não "quantas máquinas há".
- **Regras de saúde** com limiares editáveis: espaço em datastore, idade e
  profundidade de cadeia de snapshots, VMware Tools, uptime e carga de
  anfitrião, sensores de hardware e alarmes do vCenter.
- Regra de **capacidade do parque**: se o maior anfitrião cair, a memória em uso
  cabe no que resta? Ignora anfitriões em manutenção, que não recebem máquinas.
- Alarmes reconhecidos são **despromovidos a informação** — sem isso, um parque
  com um alarme reconhecido em Março nunca mais estaria verde.

### Operações

- Máquinas: ligar, encerrar e reiniciar pelo sistema convidado, desligar à
  força, reset e suspender.
- Snapshots: criar (com `quiesce` quando há Tools), apagar e reverter.
- Anfitriões: entrar e sair do modo de manutenção, reiniciar e desligar.
- Todas as operações passam por uma **guarda** que decide sem tocar na rede, e a
  execução verifica-a **outra vez** — um botão novo esbarra na mesma
  verificação.
- As operações destrutivas exigem que se **escreva o nome do objecto**. Não há
  botão de confirmar: um botão ensina a carregar em confirmar.

### Certificados

- **Confiança na primeira utilização** em vez de `CERT_NONE`: valida a cadeia,
  e quando não valida mostra a impressão digital SHA-256 e espera por uma
  decisão antes de enviar qualquer credencial.
- Uma **impressão digital diferente pára a ligação** e mostra as duas lado a
  lado.
- O modo de texto nunca aceita um certificado por omissão.

### Credenciais

- **Nenhuma senha é escrita em disco**, e não há campo para o fazer. Há testes
  que falham se alguém acrescentar um, e que verificam que uma senha metida à
  mão no ficheiro é ignorada.
- Não há opção `--senha` na linha de comandos: um argumento fica visível no
  `ps`. Para automação existe a variável `VFC_PASSWORD`.

### Modo de texto

- `--texto` e `--json`, com secções (`estado`, `anfitrioes`, `maquinas`,
  `datastores`, `snapshots`).
- Códigos de saída **0 / 1 / 2 / 3** — o 3 distingue "não liguei" de "está tudo
  mal".
- **Não escreve no vSphere**, por decisão, e há um teste que o garante.

### Por sistema

- **Windows** — detecta o `python.exe` da Microsoft Store antes de ele abrir a
  loja, distingue o Windows Terminal da consola clássica, e põe a página de
  código a 65001. Definições em `%APPDATA%` (itinerante).
- **Linux** — lê o `/etc/os-release` com queda para `ID_LIKE`, escolhendo entre
  `apt`, `dnf`, `pacman`, `zypper` e `apk`; verifica `TERM`, largura e
  codificação. Definições em XDG.
- **macOS** — trata do Python do sistema e dos dois prefixos do Homebrew
  (`/opt/homebrew` em Apple Silicon, `/usr/local` em Intel). Definições em
  `~/Library/Application Support`.
- Cada versão tem um teste que **falha se alguém acrescentar uma ramificação por
  sistema operativo** lá dentro.

### Infra-estrutura

- CI com matriz de três runners nativos — `windows-latest`, `ubuntu-latest`,
  `macos-latest`. Lint com `ruff`, testes com `pytest`, e o `--diagnostico` a
  correr contra o sistema verdadeiro.
- Nenhum teste precisa de um vCenter: o parque de testes é inventado no
  `conftest.py`.

[1.0.0]: https://github.com/RafaDevpt/Personal-AI-Projects/tree/VMware-Fleet-Console
