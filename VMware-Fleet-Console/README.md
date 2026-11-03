# VMware Fleet Console

**O estado do parque VMware, a manutenção do dia-a-dia e a cópia das máquinas — numa janela**
*The state of the VMware estate, day-to-day maintenance and whole-machine copies — in one window*

<sub>Created by Redfox using Claude</sub>

---

## Índice · Contents

- [O que faz · What it does](#o-que-faz--what-it-does)
- [O que se vê · What you see](#o-que-se-vê--what-you-see)
- [O certificado · The certificate](#o-certificado--the-certificate)
- [Credenciais · Credentials](#credenciais--credentials)
- [As operações, e o que as trava](#as-operações-e-o-que-as-trava)
- [Exportação para OVF · OVF export](#exportação-para-ovf--ovf-export)
- [O que a aplicação vos diz que ninguém configurou](#o-que-a-aplicação-vos-diz-que-ninguém-configurou)
- [Instalação · Installation](#instalação--installation)
- [Preparar o vSphere · Preparing vSphere](#preparar-o-vsphere--preparing-vsphere)
- [Linha de comandos · Command line](#linha-de-comandos--command-line)
- [Limites conhecidos · Known limits](#limites-conhecidos--known-limits)
- [A assinatura · The signature](#a-assinatura--the-signature)
- [Estrutura · Structure](#estrutura--structure)
- [Resolução de problemas · Troubleshooting](#resolução-de-problemas--troubleshooting)

---

## O que faz · What it does

**PT** · Liga-se a um **vCenter** ou directamente a um **anfitrião ESXi**, lê o
inventário todo e responde, num ecrã, à pergunta que leva alguém a abrir o
cliente web às onze da noite:

> **Está tudo bem? E se não está, o que é, onde, e o que faço?**

A partir daí trata do que se faz a seguir: ligar e encerrar máquinas, tirar e
apagar snapshots, pôr um anfitrião em manutenção — e **exportar máquinas
inteiras para OVF**, a cópia que se quer ter na mão antes de mexer no
armazenamento de um anfitrião. Tudo sem abrir o browser, sem `ovftool` e sem
voltar a autenticar-se de cada vez.

**EN** · Connects to a **vCenter** or straight to an **ESXi host**, reads the
whole inventory and answers, on one screen, the question that makes somebody
open the web client at eleven at night: *is everything all right, and if not,
what, where, and what do I do?* From there it handles what comes next — power
operations, snapshots, maintenance mode, and **exporting whole machines to OVF**
before touching a host's storage — with no browser, no `ovftool` and no
re-authenticating every time.

---

## O que se vê · What you see

**A ligação** pergunta primeiro **a que tipo de servidor se vai ligar** — ESXi,
directamente, ou vCenter — e depois o servidor, a porta, o utilizador e a senha.
A escolha sugere o utilizador habitual (`root` ou `administrator@vsphere.local`)
e, depois de ligar, é comparada com o que o servidor diz que é: ligar ao ESXi a
pensar que é o vCenter é a maneira mais fácil de ver metade do inventário sem
perceber porquê, e por isso pergunta-se antes de continuar.

**O painel** tem um cabeçalho com o servidor, o produto, o certificado fixado e
o veredicto — *HÁ PROBLEMAS CRÍTICOS — 2 críticos, 5 avisos* — e seis
separadores:

| Separador | O que tem |
| :--- | :--- |
| **Estado** | os achados, por gravidade, com o que fazer em cada um |
| **Máquinas** | abre filtrado nas **ligadas**; procura por nome, IP, sistema ou anfitrião; detalhe da seleccionada |
| **Anfitriões** | estado, manutenção, CPU, memória, máquinas, versão, uptime, alertas de hardware |
| **Datastores** | capacidade, livre, e o estado contra os limiares |
| **Snapshots** | todos, com idade e tamanho — os velhos a vermelho |
| **Exportação** | o progresso da exportação: máquina a máquina, ritmo, tempo que falta, registo |

As operações vivem num botão **Acções** em cada separador, que é o mesmo menu do
botão direito. Uma acção que a guarda recusa aparece **desactivada, não
escondida**. A tabela mantém a selecção quando o inventário se actualiza — não
tira a máquina de baixo do cursor enquanto alguém lhe está a ler o nome.

Todo o achado traz três coisas: **o que se observou, onde, e o que fazer**. Um
aviso que diz "datastore quase cheio" sem dizer qual, nem quanto, nem o que se
ganha em limpar, obriga a ir procurar — e a essa hora ninguém vai procurar.

Tema escuro ou claro (menu **Ver**), e o rodapé diz sempre a hora da última
leitura.

### Por que razão a cor nunca é a única informação

O vermelho nunca é a única coisa que distingue um crítico de um aviso: há sempre
a palavra — *Crítico*, *Aviso* — escrita ao lado. Cerca de um em cada doze homens não
distingue vermelho de verde, e uma ferramenta de operações que comunique o
essencial só por cor é uma ferramenta que não serve a essa pessoa. Também resolve
a captura de ecrã impressa a preto e branco que vai no relatório.

---

## O certificado · The certificate

**Esta é a parte da aplicação que mais difere do que se costuma escrever para
vSphere, e a que mais vale a pena ler.**

Praticamente todos os ESXi e vCenter do mundo apresentam um certificado
auto-assinado, porque é o que vem de fábrica. O resultado é que quase toda a
gente que escreve automação para vSphere acaba, mais cedo ou mais tarde, a
escrever a linha que desliga a verificação:

```python
contexto.verify_mode = ssl.CERT_NONE     # <- o que esta aplicação NÃO faz
```

A partir dessa linha a ligação está **cifrada mas não autenticada**: qualquer
coisa entre a estação e o servidor pode apresentar-se como o servidor e receber
a senha de administrador do vSphere em texto limpo do outro lado do túnel. Numa
rede de gestão que passa pelos mesmos switches que o resto, não é um risco
teórico.

### O que se faz em vez disso

Confiança na primeira utilização — o modelo do SSH, e funciona pela mesma razão.

1. **Tenta-se validar normalmente.** Se o parque tiver uma autoridade interna
   instalada na máquina, isto passa e não há mais nada a discutir.
2. **Se não validar, não se liga.** Mostra-se a impressão digital SHA-256 e
   pede-se que a compare com a que o servidor mostra. Nenhuma credencial é
   enviada antes disso.
3. **Aceite uma vez, fica guardada.** Nas ligações seguintes é comparada.

```
┌─ Certificado de esx01.lab.local ───────────────────────────────────┐
│ Certificado que esta máquina não consegue validar — o que é o      │
│ normal num ESXi ou vCenter com o certificado de fábrica.           │
│                                                                     │
│  A4:C1:9F:22:E8:0B:7D:53:16:AA:90:FC:31:6E:D2:88:...               │
│                                                                     │
│ Onde confirmar esta impressão digital:                             │
│   ESXi    — na consola directa (DCUI), em View Support Information │
│   vCenter — Administration > Certificates > Machine SSL            │
│                                                                     │
│                              [ Recusar ]  [ Aceitar e guardar ]    │
└─────────────────────────────────────────────────────────────────────┘
```

O botão em foco é o de **recusar**: quem carregue em Enter por reflexo não
aceita um certificado que não olhou.

### E quando a impressão digital muda

**A ligação pára.** É o comportamento que justifica tudo o resto.

```
A IMPRESSÃO DIGITAL DO CERTIFICADO MUDOU.
  Aceite antes: A4:C1:9F:22:E8:0B:7D:53:...
  Agora:        7B:22:E1:04:9C:AF:38:D0:...

Isto acontece quando o certificado é regenerado — mas também acontece
quando não se está a falar com o servidor de sempre.
```

Acontece de verdade quando se muda o nome do anfitrião ou se regenera o
certificado. É chato uma vez por ano, e é o comportamento certo: **a diferença
entre isto e `CERT_NONE` é que uma substituição de certificado é notada em vez
de passar despercebida.**

---

### O que a 2.0 corrigiu aqui

- **ESXi geridos por um vCenter.** O certificado deles é emitido pela VMCA (a
  autoridade interna do vCenter) e não é a sua própria raiz. Na 1.0, fixar a
  impressão digital de um desses certificados não chegava: o OpenSSL insistia em
  subir a cadeia e o aperto de mão falhava sempre. Agora o certificado aceite
  basta por si (`VERIFY_X509_PARTIAL_CHAIN`), que é o que fixar quer dizer.
- **O diálogo do certificado vinha com o sujeito, o emissor e a validade em
  branco**, porque o Python só os devolve para certificados validados — e o que
  se mostra é precisamente o que não valida. Agora lêem-se do próprio
  certificado.

---

## Credenciais · Credentials

**Não há campo para guardar senhas. Não há opção. Não há "lembrar-me".**

A senha é pedida a cada sessão, segue na chamada que abre a ligação, e o campo
é limpo logo a seguir — corra a ligação bem ou mal. A partir daí a aplicação usa
a sessão do servidor, não a senha.

A razão é o que a senha abre. Uma senha de administrador do vCenter dá acesso a
**todas** as máquinas do parque — os controladores de domínio, as bases de
dados, as cópias de segurança. Guardá-la num ficheiro na pasta do utilizador
significa que qualquer coisa que consiga ler ficheiros nessa conta fica com o
parque inteiro. Uma cifra feita com uma chave que também está na máquina não
resolve isto: adia-o.

O que **é** guardado é o que não tem valor sozinho:

| Guardado | Porquê |
| :--- | :--- |
| Endereço do servidor | para não o escrever todos os dias |
| Nome de utilizador | idem |
| Porta | idem |
| Tipo de servidor (ESXi ou vCenter) | para o ecrã de ligação abrir com a escolha certa |
| Impressão digital do certificado | é ela que faz o trabalho de segurança |
| Destino e prazo de encerramento da última exportação | para não os escolher de novo |

Há um teste que falha se alguém acrescentar um campo de senha a qualquer uma das
estruturas que vão para disco, e outro que verifica que uma senha metida à mão no
ficheiro é ignorada e não sobrevive à gravação seguinte.

Para automação existe a variável de ambiente `VFC_PASSWORD`. **Não há opção
`--senha`**, e a ausência é deliberada: um argumento de linha de comandos fica
visível no `ps` para qualquer utilizador da máquina e escrito no histórico da
shell.

---

## As operações, e o que as trava

Ligar, encerrar, reiniciar, suspender, snapshots e modo de manutenção. Tudo
passa por uma **guarda** antes de chegar ao servidor.

### Encerrar não é a mesma coisa que desligar

É a distinção que mais estrago evita, e a aplicação nunca a esconde. Ao carregar
em `e` numa máquina, o que aparece é isto:

```
┌─ SRV-APP01 — o que fazer ──────────────────────────────────────────┐
│  > Encerrar pelo sistema convidado — limpo, pede às Tools          │
│    Desligar à força — equivale a cortar a corrente                 │
│    Reiniciar pelo sistema convidado                                │
│    Suspender — guarda a memória em disco                           │
└─────────────────────────────────────────────────────────────────────┘
```

E quando a máquina não tem VMware Tools a correr, a opção limpa aparece **como
recusa, com a razão**, em vez de desaparecer sem explicação:

```
    Encerrar limpo indisponível: VMware Tools não instaladas: não há
    forma de pedir ao sistema convidado que se encerre. Resta desligar
    à força, que é o equivalente a cortar a corrente.
```

### A confirmação é escrita, não é um botão

As operações destrutivas não têm "Sim" e "Não". Têm uma caixa onde é preciso
**escrever o nome do objecto**.

```
┌─ Desligar à força — SRV-DC01 ──────────────────────────────────────┐
│ Equivale a cortar a corrente: o sistema convidado não é avisado e  │
│ o que estiver por gravar perde-se. Esta máquina tem as VMware Tools│
│ a correr — o encerramento limpo está disponível e é o que devia    │
│ usar.                                                               │
│                                                                     │
│ Para continuar, escreva o nome exacto:  SRV-DC01                   │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ └─────────────────────────────────────────────────────────────────┘│
│                                   [ Cancelar ]  [ Confirmar ]      │
└─────────────────────────────────────────────────────────────────────┘
```

Um diálogo com um botão de confirmar ensina a carregar em confirmar. Uma caixa
onde é preciso escrever `SRV-DC01` **obriga a ler** que a máquina prestes a ser
desligada se chama `SRV-DC01`. É a única defesa real contra ter a lista ordenada
de outra maneira do que se pensava.

<details>
<summary><b>O que exige confirmação escrita, e o que não</b></summary>

| Operação | Confirmação | Porquê |
| :--- | :--- | :--- |
| Ligar | não | não perde nada |
| Encerrar pelo convidado | não | é a operação segura; obrigar a escrever empurraria as pessoas para a insegura, que é mais rápida |
| Reiniciar pelo convidado | não | idem |
| Suspender | não | reversível |
| Criar snapshot | não | criar não perde nada — e pedir confirmação aqui treinaria a confirmar sem ler, e a caixa seguinte é a de apagar |
| **Desligar à força** | **sim** | corta a corrente |
| **Reset** | **sim** | idem |
| **Reverter snapshot** | **sim** | deita fora tudo desde que foi tirado |
| **Apagar snapshot** | **sim** | perde o ponto de retorno |
| **Entrar em manutenção** | **sim** | pode parar serviço |
| **Reiniciar / desligar anfitrião** | **sim** | pára tudo o que lá está |

</details>

### Três recusas que valem o módulo inteiro

**Uma máquina cujo anfitrião não responde não recebe ordens.** O vCenter continua
a listá-la com o último estado conhecido, e mandar-lhe um `PowerOn` devolve um
erro que ninguém percebe. A aplicação diz antes que não sabe o estado dela.

**Entrar em manutenção com máquinas ligadas em cima.** Num cluster com DRS o
vCenter migra-as e a tarefa acaba. Sem DRS — que é o caso de um anfitrião só, e é
o caso da maioria dos sítios pequenos — a tarefa fica a 2% *para sempre*, **sem
erro nenhum**, à espera que alguém desligue as máquinas à mão. Já se perderam
horas nisso. Por isso as máquinas ligadas são contadas antes e o aviso diz-o.

**Reiniciar um anfitrião fora do modo de manutenção.** O ESXi recusa por si
próprio, mas com uma mensagem genérica. Recusar aqui diz o que falta fazer
primeiro.

### Reverter um snapshot é tratado como um apagar

Porque é um. É a operação que mais parece inofensiva e mais estrago faz, e o
aviso diz quantos dias se perdem — não "vai perder alterações", mas **"isso são
240 dias de alterações"**, que é o que faz alguém parar.

E a confirmação pede o nome **da máquina**, não o do snapshot: os snapshots
chamam-se todos "antes da actualização", e escrever isso não distingue reverter a
máquina de testes de reverter a de produção.

---

## Exportação para OVF · OVF export

**PT** · Um backup feito com agente dentro do Windows protege os dados e o
sistema, mas para recuperar a máquina é preciso um restauro a partir do zero:
perde-se o `.vmx`, o hardware virtual, as placas de rede e as VLANs. Antes de
mexer no armazenamento de um anfitrião — refazer um RAID, por exemplo — o que se
quer é **a máquina tal como o vSphere a vê, pronta a importar**.

No separador **Máquinas**, escolha uma ou várias e carregue em **Exportar
máquinas…**. Cada uma fica numa pasta própria com:

```
SRV-APP01_20261103-0830/
├── SRV-APP01.ovf              o descritor: hardware, redes, discos
├── SRV-APP01-disk-0.vmdk      os discos, comprimidos e só com os blocos usados
├── SRV-APP01.mf               o manifesto SHA-256, verificado na importação
└── LEIA-ME.txt                o que é, de onde veio, e como se restaura
```

e na raiz do destino fica o relatório do lote, em texto e em JSON. Para
restaurar: no vSphere Client, **Deploy OVF Template**, e escolher os ficheiros da
pasta.

**EN** · An agent backup inside Windows protects data and OS, but recovering the
machine is a bare-metal restore: the `.vmx`, virtual hardware and NICs are gone.
This exports the machine as vSphere sees it — `.ovf`, stream-optimised disks and
a SHA-256 manifest — ready to import with *Deploy OVF Template*.

### Sem ferramentas externas

Não usa o `ovftool`. É o mesmo mecanismo que ele e o cliente web usam por baixo,
feito com a biblioteca da VMware e a biblioteca-padrão do Python:

1. `VirtualMachine.ExportVm()` devolve uma concessão (`HttpNfcLease`) com um
   endereço HTTPS por disco.
2. Os discos descarregam-se por esses endereços, já no formato *stream-optimized*.
3. A concessão é mantida viva enquanto se descarrega (`HttpNfcLeaseProgress`).
4. `OvfManager.CreateDescriptor()` escreve o `.ovf`.
5. Escreve-se o manifesto com o SHA-256 de cada ficheiro, calculado enquanto
   descarrega — sem ler os discos duas vezes.

A transferência dos discos leva o cookie da sessão, que é uma credencial, e por
isso tem a mesma desconfiança que a ligação principal: para o servidor da sessão
usa o certificado que alguém aceitou; para outro anfitrião (exportar pelo
vCenter, que manda buscar os discos ao ESXi onde a máquina está) compara o
certificado com a impressão digital que o próprio vCenter anunciou na concessão,
e só depois envia o cookie. Vai sempre directa ao anfitrião, **sem passar pelo
proxy** que a máquina tenha configurado.

### A regra que não se negocia: o vSphere só exporta máquinas desligadas

Para uma máquina ligada, a aplicação pode — **só se lhe for pedido, e com
ENCERRAR escrito à mão** — encerrar o sistema convidado pelas VMware Tools,
exportar, e no fim **voltar a ligá-la ou deixá-la desligada** (para a manutenção
do anfitrião). Uma máquina de cada vez, para que o tempo parado de cada uma seja
só o da sua própria cópia.

| Caso | O que acontece |
| :--- | :--- |
| Desligada (ou modelo) | exporta-se |
| Ligada, com as Tools a correr, opção activa | encerra-se, exporta-se, volta a ligar-se (ou fica desligada, se escolhido) |
| Ligada, **sem Tools a correr** | **recusada** — sem encerramento limpo, não se desliga à força |
| Ligada, mas é **o próprio vCenter** desta sessão | **recusada** — encerrá-la cortava a sessão a meio |
| Suspensa | recusada — ligue e encerre, ou desligue |
| No anfitrião que não responde | recusada — os discos não têm de onde vir |

Cada recusa aparece no diálogo **antes** de confirmar, com a razão por inteiro.

### O que acontece quando corre mal

- **Não encerrou a tempo** (o prazo é configurável): não é desligada à força.
  Fica como está e a exportação dela é dada como falhada.
- **A cópia falhou ou foi cancelada:** a concessão é abortada, **a pasta a meio
  é apagada** — uma pasta com meio disco parece um backup, o que é pior do que
  não haver pasta — e, se a máquina foi encerrada por nós e era para voltar a
  ligar, **volta a ser ligada**.
- **Acabou o espaço:** essa falha, e o lote pára antes de encerrar mais
  máquinas para nada.
- **Fechar a janela a meio** pede confirmação, cancela, e espera que a máquina
  encerrada volte a ser ligada antes de sair.

### Para onde

Uma pasta local, um disco externo, ou uma partilha de rede
(`\\servidor\partilha`). O diálogo mostra o espaço livre contra o espaço que as
máquinas ocupam no datastore — um tecto, porque o OVF sai comprimido e sem os
blocos vazios. **Não guarde a cópia no próprio servidor em que vai mexer**: se o
armazenamento morrer, a cópia morre com ele. E uma exportação de um controlador
de domínio contém o `NTDS.dit` — a partilha de destino deve ser só de IT.

---

## O que a aplicação vos diz que ninguém configurou

O vCenter já tem alarmes, e esta aplicação lê-os todos. O que acrescenta são as
leituras que ninguém configura como alarme porque não têm limiar óbvio.

| Regra | Limiar | Porquê este valor |
| :--- | :--- | :--- |
| Espaço em datastore | **10%** crítico, **20%** aviso | 10% é onde um VMFS deixa de conseguir crescer um snapshot ou um disco fino sem parar as máquinas |
| Idade de snapshot | **3 d** aviso, **30 d** crítico | três dias é onde deixa de ser "um antes da actualização" e passa a ser um ficheiro esquecido |
| Cadeia de snapshots | **3 níveis** | cada nível é mais um ficheiro de diferenças lido em cada acesso ao disco |
| Uptime do anfitrião | **90 d** | um ciclo de patches completo por aplicar |
| CPU do anfitrião | **85%** | — |
| Memória do anfitrião | **90%** | acima dos 95% o ESXi faz ballooning e swap, e o que se nota é lentidão *dentro* das máquinas |
| VMware Tools | paradas / em falta | sem elas não há encerramento limpo |
| Falha de um anfitrião | — | ver abaixo |

Todos os limiares são editáveis nas definições, e cada um tem um teste de cada
lado — um valor que dispara e um que não.

### A pergunta que só se responde olhando para o parque todo

> Se o maior anfitrião cair, o que resta chega para o que lá estava a correr?

```
[AVISO ] Parque: Se esx01 cair, a memória em uso (180,0 GB) não cabe
         no que resta (128,0 GB).
         Nem todas as máquinas voltariam a arrancar.
```

Um anfitrião em modo de manutenção **não conta como folga** — não recebe
máquinas, e contá-lo seria contar com uma folga que não existe. Com um anfitrião
só, a regra cala-se: a resposta é obviamente não, e dizê-la seria ruído em todos
os sítios pequenos.

### Três coisas que a aplicação recusa fazer

<details open>
<summary><b>Não aponta nada quando não há nada a apontar</b></summary>

Um parque saudável dá um relatório vazio, e há um teste que o garante. Uma
ferramenta que aponta sempre alguma coisa ensina quem a lê a ignorá-la — e a
partir daí não serve para nada.

</details>

<details>
<summary><b>Não avisa sobre modelos, nem sobre Tools em máquinas desligadas</b></summary>

Um template está desligado por definição e não tem Tools a correr por definição.
Numa máquina desligada, "Tools paradas" é a descrição de uma máquina desligada.
Avisar sobre qualquer um dos dois encheria o relatório de linhas que nunca vão ser
resolvidas.

</details>

<details>
<summary><b>Não trata "sem dados" como "saudável"</b></summary>

O `gray` do vSphere significa "o vCenter não está a receber dados deste objecto".
Não é saudável nem doente — é uma terceira coisa, e costuma ser a mais urgente.
Um anfitrião sem resposta é **crítico**, e os números que dele se mostram vêm com
a nota de que são os últimos conhecidos e podem ter horas.

E quando um anfitrião não responde, os outros avisos sobre ele calam-se: dois
avisos sobre a mesma avaria parecem duas avarias.

</details>

---

## Instalação · Installation

### Três versões independentes · Three independent versions

Esta pasta não contém a aplicação: contém **três versões independentes** dela,
uma por sistema. Cada uma é completa e autónoma — tem o seu `src/`, os seus
`tests/`, o seu `requirements.txt` e o seu lançador. Escolha a sua e ignore as
outras duas.

| Pasta | Sistema | Abrir com |
| :--- | :--- | :--- |
| **[`Windows/`](Windows/)** | Windows 10 / 11 | duplo clique em `EXECUTAR.bat` |
| **[`Linux/`](Linux/)** | Qualquer distribuição | `./executar.sh` |
| **[`macOS/`](macOS/)** | Apple Silicon e Intel | duplo clique em `executar.command` |

Não são três cópias iguais. O `src/vfc/platform_support.py` é diferente em cada
uma, e **nenhuma tem uma ramificação por sistema operativo lá dentro** — há um
teste em cada versão que falha se alguém acrescentar um `sys.platform`.

- A de **Windows** deteta o `python.exe` falso da Microsoft Store, declara a
  janela preparada para ecrãs de alta densidade (para o texto não ficar
  desfocado a 125% ou 150%), e trata da página de código do modo de texto.
- A de **Linux** lê o `/etc/os-release` para escolher entre `apt`, `dnf`,
  `pacman`, `zypper` e `apk` — incluindo o pacote do Tkinter, que nas
  distribuições vem à parte — e verifica se há um ambiente gráfico.
- A de **macOS** trata do Python do sistema, dos dois prefixos do Homebrew e do
  `python-tk` que o Python do Homebrew não traz.

Para saber o que falta nesta máquina, em qualquer das três:

```
python -m vfc --diagnostico
```

**O custo, dito à cabeça:** uma correcção ao código partilhado tem de ser
aplicada três vezes. É o preço de três versões independentes em vez de uma com
ramificações — cada versão fica mais simples de ler e o utilizador leva só o que
precisa. O `CONTRIBUTING.md` tem o comando que confirma que as três não se
afastaram.

### Requisitos · Requirements

- **Python 3.10 ou superior** · [python.org](https://www.python.org/downloads/)
- Acesso à porta **443** do vCenter ou do anfitrião ESXi
- Uma conta do vSphere — ver [Preparar o vSphere](#preparar-o-vsphere--preparing-vsphere)

### As dependências, e o que acontece sem elas

| Pacote | Para quê | Sem ele |
| :--- | :--- | :--- |
| `pyvmomi` | a biblioteca oficial da VMware | **não há ligação nenhuma** |
| Tkinter | a janela — vem com o Python do python.org; em Linux é o `python3-tk` e afins | o modo de texto funciona na mesma |

Do `pip` vem **uma**. A janela usa o Tkinter que vem com o Python — num posto de
trabalho com a internet filtrada, a diferença entre a aplicação abrir ou não — e
a exportação usa só a biblioteca da VMware e a biblioteca-padrão.

### Linha de comandos

```bash
cd VMware-Fleet-Console/Linux        # ou Windows, ou macOS
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m vfc
```

---

## Preparar o vSphere · Preparing vSphere

### Uma conta que não seja a de administrador

Para monitorizar chega o papel **Read-only** do vSphere, aplicado na raiz do
inventário com propagação. Com essa conta a aplicação lê tudo e não escreve
nada — e é a conta certa para pôr num `cron` ou numa tarefa agendada.

Para as operações, os privilégios mínimos são:

| Operação | Privilégio |
| :--- | :--- |
| Ligar, desligar, suspender, reset | `VirtualMachine.Interact.PowerOn` / `PowerOff` / `Suspend` / `Reset` |
| Encerrar pelo convidado | `VirtualMachine.Interact.PowerOff` |
| Reiniciar pelo convidado | `VirtualMachine.Interact.Reset` |
| Exportar para OVF | `VApp.Export` (e, para encerrar e voltar a ligar, `PowerOff` e `PowerOn`) |
| Snapshots | `VirtualMachine.State.CreateSnapshot` / `RemoveSnapshot` / `RevertToSnapshot` |
| Modo de manutenção | `Host.Config.Maintenance` |
| Reiniciar e desligar anfitrião | `Host.Config.Maintenance` |

**Uma conta sem um privilégio não parte a aplicação**: a operação é recusada pelo
servidor e a mensagem é traduzida para "a conta não tem permissões para esta
operação neste objecto". A monitorização continua a funcionar.

### Ligar directamente a um ESXi

Funciona, e é o modo certo para quem não tem vCenter. Utilizador `root`, ou uma
conta local do anfitrião.

> **A limitação que interessa saber antes:** um ESXi com a **licença gratuita**
> tem a API do vSphere em **modo de leitura**. Ligar, desligar, snapshots e
> manutenção vão ser recusados pelo servidor, **mesmo com credenciais de
> administrador** — e o erro que o servidor devolve (`RestrictedVersion`) não diz
> nada sobre licenças a quem o vê pela primeira vez.
>
> A aplicação detecta isto na ligação e di-lo no cabeçalho, uma vez, em vez de
> deixar todos os botões falharem sem explicação. **Toda a monitorização
> funciona** — é a escrita que não.

---

## Linha de comandos · Command line

O mesmo diagnóstico, sem janela. Para sessões SSH, servidores sem ambiente
gráfico, e automação. Sem argumentos, a aplicação abre a janela; se a janela não
puder abrir (sem Tkinter, sem ambiente gráfico), cai aqui sozinha em vez de
rebentar.

```bash
./cli.sh --servidor vcenter.empresa.local --utilizador administrator@vsphere.local
./cli.sh --json --seccao estado
./cli.sh --seccao snapshots
```

| Código de saída | Significado |
| :---: | :--- |
| **0** | nada a apontar |
| **1** | há avisos |
| **2** | há problemas críticos |
| **3** | não foi possível ligar |
| **4** | a assinatura da aplicação foi alterada — ver [A assinatura](#a-assinatura--the-signature) |

O **3** é distinto de propósito: não conseguir ligar não é a mesma coisa que
estar tudo mal, e é a distinção que evita acordar alguém por causa de um cabo de
rede.

```bash
# PT: num cron às sete da manhã
VFC_PASSWORD="$(pass vsphere/leitura)" ./cli.sh \
    --servidor vcenter.empresa.local \
    --utilizador monitorizacao@vsphere.local \
    --json > /var/log/parque.json || echo "parque com problemas: $?"
```

### O modo de texto não escreve no vSphere

Não há `--desligar`, e não é esquecimento. Uma operação destrutiva sem
confirmação escrita fica a um `Ctrl-R` no histórico de distância da próxima vez
que alguém a repetir sem pensar. As operações — e a exportação, que pode
encerrar máquinas — vivem na janela, onde há um sítio para confirmar. Há um teste que falha se alguém acrescentar uma opção
dessas.

### E não aceita um certificado novo sozinho

Um script que corra sem ninguém a olhar não é sítio para decidir em quem se
confia. Aceite o certificado uma vez na janela; a partir daí a impressão
digital está guardada e o modo de texto liga sozinho.

---

## Limites conhecidos · Known limits

<details open>
<summary><b>ESXi com licença gratuita: a API é só de leitura</b></summary>

Nenhuma operação de escrita funciona, por muito que o utilizador seja
administrador. É uma restrição da licença da VMware, não da aplicação. A
monitorização toda funciona. A aplicação detecta-o e di-lo no cabeçalho.

</details>

<details>
<summary><b>Sem DRS, o modo de manutenção não migra nada</b></summary>

Num anfitrião sozinho, entrar em manutenção com máquinas ligadas fica pendente
indefinidamente. A aplicação avisa antes com o número de máquinas ligadas, mas
não as migra nem as encerra por si — isso é uma decisão de quem está a fazer a
intervenção.

</details>

<details>
<summary><b>Não migra máquinas, não cria máquinas, não mexe em redes</b></summary>

Isto é uma ferramenta de manutenção, não uma consola de administração. Criar
máquinas, mexer em vSwitches, configurar HA e DRS — tudo isso vive no cliente
web, e é lá que deve viver: são operações de projecto, não de plantão.

</details>

<details>
<summary><b>O tamanho dos snapshots nem sempre vem</b></summary>

O vCenter reporta-o de forma inconsistente conforme a versão e o tipo de
datastore. Quando não vem, o aviso sai sem o tamanho em vez de inventar um
número — e a idade, que é o que decide, vem sempre.

</details>

<details>
<summary><b>Uma sessão aberta é uma sessão aberta</b></summary>

A aplicação mantém a sessão do vSphere enquanto estiver aberta, e actualiza o
inventário no intervalo configurado. Num parque grande isso é carga no vCenter.
O intervalo é editável, e a zero desliga a actualização automática. Durante
uma exportação a actualização pára: a ligação ao servidor está ocupada com ela.

</details>

<details>
<summary><b>A exportação só copia máquinas desligadas</b></summary>

É uma regra do vSphere, não da aplicação: o `ExportVm` recusa uma máquina ligada.
Para copiar sem parar a máquina é preciso uma ferramenta de backup ao nível do
hipervisor (Veeam e afins). O que esta aplicação faz é encerrar pelo convidado,
copiar e voltar a ligar — com a máquina parada só durante a sua própria cópia.

</details>

<details>
<summary><b>O que foi testado, e contra quê</b></summary>

A ligação, a recolha do inventário, as operações e a janela foram testadas
contra o simulador oficial da VMware (`vcsim`, do govmomi), em modo vCenter e em
modo ESXi. O `vcsim` **não implementa `ExportVm`**, e por isso a exportação foi
testada contra um servidor HTTPS verdadeiro com certificado fixado e uma
concessão simulada — incluindo cancelar a meio, falhar a transferência, não
encerrar a tempo e ficar sem espaço. Os nomes de cada chamada e de cada campo
foram confirmados contra as definições de tipos do próprio `pyVmomi`. Faça a
primeira exportação a sério numa máquina que não seja crítica.

</details>

---

## A assinatura · The signature

O crédito — *Created by Redfox using Claude* — e o autor vivem num só sítio,
`branding.py`, e aparecem na barra de título, no rodapé permanente da janela, no
*Sobre*, no relatório de texto, no relatório de cada exportação, no `LEIA-ME.txt`
ao lado de cada cópia e na primeira linha de cada sessão no registo.

Os três valores estão **selados**: o arranque calcula o SHA-256 deles e
compara-o com o selo guardado. Se o crédito for alterado ou apagado, a aplicação
**recusa arrancar** (código de saída 4) e diz porquê; a janela confirma ainda,
depois de desenhada, que o rodapé mostra o crédito tal como está selado.

**Dito com honestidade:** nenhuma assinatura em código que corre na máquina de
outra pessoa é impossível de remover — o Python é texto, e quem apagar o crédito
pode apagar também a verificação. O selo garante que a remoção não acontece por
acaso nem às escondidas. A protecção que vale fora do código é a
[licença MIT](LICENSE), que obriga a manter o aviso de autoria em todas as cópias.

---

## Estrutura · Structure

```
VMware-Fleet-Console/
├── README.md              este ficheiro
├── CHANGELOG.md
├── CONTRIBUTING.md        inclui o comando que confirma que as três não divergiram
├── Windows/  Linux/  macOS/
    ├── src/vfc/
    │   ├── models.py            os objectos, e a fronteira com o pyVmomi
    │   ├── collect.py           do inventário do vSphere para os modelos
    │   ├── health.py            as regras — não tocam na rede
    │   ├── actions.py           as guardas, e a execução que as verifica outra vez
    │   ├── connection.py        a ligação e a decisão sobre o certificado
    │   ├── export.py            a exportação para OVF — a guarda e a execução
    │   ├── branding.py          a assinatura e o selo
    │   ├── config.py            definições; sem campo para senhas
    │   ├── cli.py               o modo de texto
    │   ├── platform_support.py  o único ficheiro diferente entre as três versões
    │   └── gui/                 a janela (o único sítio que importa o tkinter)
    └── tests/                   incl. um servidor HTTPS de bolso para a exportação
```

**A separação que faz a suite de testes valer alguma coisa:** `health.py`, as
guardas de `actions.py` e a guarda de `export.py` recebem modelos já lidos e
devolvem decisões. Não abrem
ligações, não precisam de vCenter, e por isso podem ser testadas exaustivamente
contra um parque inventado em `conftest.py` — com um anfitrião sem resposta, um
datastore quase cheio, um snapshot esquecido há oito meses e uma máquina sem
Tools.

Um teste que dependesse de um servidor VMware ligado seria um teste que ninguém
correria.

---

## Resolução de problemas · Troubleshooting

<details>
<summary><b>"A impressão digital do certificado mudou"</b></summary>

Ou o certificado foi regenerado, ou não se está a falar com o servidor de
sempre. Confirme a impressão digital na consola do servidor:

- **ESXi** — consola directa (DCUI), *View Support Information*
- **vCenter** — *Administration › Certificates › Machine SSL Certificate*

Se coincidir, aceite. Se não coincidir, **não aceite** e vá perceber porquê.

</details>

<details>
<summary><b>"Credenciais recusadas"</b></summary>

No vCenter o utilizador costuma incluir o domínio: `administrator@vsphere.local`.
Num ESXi é normalmente `root`.

Atenção: algumas tentativas falhadas seguidas **bloqueiam a conta** no vCenter.

</details>

<details>
<summary><b>"O servidor recusou a operação por causa do licenciamento"</b></summary>

É um ESXi com licença gratuita. Ver [Limites conhecidos](#limites-conhecidos--known-limits).

</details>

<details>
<summary><b>A janela não abre</b></summary>

```
python -m vfc --diagnostico
```

- **Windows** — o Tkinter é uma opção do instalador do python.org (*tcl/tk and
  IDLE*); o `EXECUTAR.bat` diz se falta. E confirme que o `python.exe` não é o
  atalho da Microsoft Store.
- **Linux** — o Tkinter é um pacote à parte (`python3-tk`, `python3-tkinter`,
  `tk`…), e é preciso um ambiente gráfico. Numa sessão SSH sem `-X` não há.
- **macOS** — o Python do Homebrew precisa de `brew install python-tk@3.x`.
- **Qualquer um** — sem janela, `--texto` dá o mesmo diagnóstico.

</details>

<details>
<summary><b>Sai vazio, ou faltam máquinas</b></summary>

Permissões. A conta vê apenas o ramo do inventário onde tem privilégios, e a
aplicação mostra o que conseguiu ler em vez de um ecrã em branco — meio
inventário é útil, nenhum não é. O que falhou fica no registo:

- Windows: `%APPDATA%\VMwareFleetConsole\registos\consola.log`
- Linux: `~/.config/VMwareFleetConsole/registos/consola.log`
- macOS: `~/Library/Application Support/VMwareFleetConsole/registos/consola.log`

</details>

<details>
<summary><b>A exportação falha ao descarregar os discos, através do vCenter</b></summary>

Pelo vCenter, os discos vêm directamente do ESXi onde a máquina está — não do
vCenter. Este computador tem de resolver o nome desse anfitrião e chegar-lhe pela
porta 443. Se o vCenter não anunciar a impressão digital do anfitrião e o
certificado dele não validar aqui, a transferência pára antes de enviar a sessão:
instale a autoridade do vCenter (`https://<vcenter>/certs/download.zip`) ou ligue
directamente ao ESXi e exporte daí.

</details>

<details>
<summary><b>Uma operação ficou pendente e não acaba</b></summary>

Se for uma entrada em modo de manutenção: são as máquinas ligadas. A aplicação
avisou antes, e o vCenter não vai dar erro — vai esperar. Encerre-as ou mova-as, ou
cancele a tarefa no cliente web.

</details>

---

<div align="center">

Parte de **[Personal AI Projects](https://github.com/RafaDevpt/Personal-AI-Projects)** ·
Licença [MIT](LICENSE)

<sub>Created by Redfox using Claude</sub>

</div>
