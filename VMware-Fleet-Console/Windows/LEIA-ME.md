# VMware Fleet Console — versão para Windows

**Esta pasta é a aplicação completa para Windows.** As versões de Linux e macOS
vivem nas pastas ao lado e não são precisas aqui.

*This folder is the complete Windows application. The Linux and macOS versions
live in the folders alongside and are not needed here.*

<sub>Created by Redfox using Claude</sub>

---

## Arrancar

Duplo clique em **`EXECUTAR.bat`**.

Na primeira execução cria o ambiente virtual e instala as dependências. Nas
seguintes abre logo a janela, **sem consola atrás dela**. **Não pede elevação** —
esta ferramenta não lê nada da máquina local.

A janela pergunta primeiro **a que tipo de servidor se liga** — ESXi ou vCenter
— depois o servidor, o utilizador e a senha, e abre no separador das máquinas,
filtrado nas que estão ligadas.

## Exportar máquinas para OVF

No separador **Máquinas**, escolha uma ou várias (Ctrl ou Shift) e carregue em
**Exportar máquinas…**. O destino pode ser uma pasta local, um disco externo ou
uma partilha de rede (`\\servidor\partilha`). O que acontece a cada máquina —
pronta, vai ser encerrada, ou recusada e porquê — vê-se **antes** de confirmar.
O detalhe está no [README do projecto](../README.md#exportação-para-ovf--ovf-export).

## Modo de texto

```
CLI.bat --servidor vcenter.empresa.local --utilizador administrator@vsphere.local
CLI.bat --json --seccao estado
```

Códigos de saída: **0** nada a apontar, **1** avisos, **2** críticos, **3** não
foi possível ligar, **4** a assinatura da aplicação foi alterada. O modo de
texto só lê: as operações e a exportação vivem na janela, onde há um sítio para
confirmar.

## O que esta máquina precisa

```
EXECUTAR.bat --diagnostico
```

| Requisito | Porquê | Sem ele |
| :--- | :--- | :--- |
| Python 3.10+ | — | não arranca |
| Python que **não** seja o da Store | ver abaixo | não arranca |
| `pyvmomi` | a biblioteca da VMware | não há ligação nenhuma |
| Tkinter | a janela; vem com o Python do python.org (opção *tcl/tk and IDLE*) | resta o modo de texto |

Não há mais dependências: a janela usa o Tkinter que vem com o Python, e a
exportação usa só a biblioteca da VMware e a biblioteca-padrão — sem `ovftool`.

## O que é diferente nesta versão

O `src\vfc\platform_support.py` é o único ficheiro que difere entre as três
versões. Nesta, o que ele sabe e as outras não são quatro particularidades do
Windows:

### O `python.exe` da Microsoft Store

Uma instalação limpa do Windows traz um `python.exe` no PATH que **não é o
Python**: é um atalho que abre a loja. Quem o corre vê a Microsoft Store
abrir-se sozinha e conclui que o programa está avariado.

O `EXECUTAR.bat` decide pelo Python que **corre**, não pelo que aparece no PATH:
experimenta primeiro o lançador `py` (que vem com o python.org) e depois o
`python`. Se nenhum correr, diz o que fazer: instalar de
[python.org](https://www.python.org/downloads/) — com *Add python.exe to PATH* e
*tcl/tk and IDLE* marcados — e desligar os aliases em **Definições → Aplicações →
Definições avançadas de aplicações → Aliases de execução de aplicações**.

### A página de código

É a causa número um de "sai tudo aos quadradinhos". Uma consola portuguesa
arranca na página 850, onde os caracteres de desenho de caixas e os acentos saem
trocados. Só importa ao modo de texto e às mensagens dos lançadores, que fazem
`chcp 65001` (UTF-8) antes de arrancar.

### A nitidez da janela

Num portátil com a escala do ecrã a 125% ou 150%, o Windows estica as janelas
das aplicações que não se declaram preparadas para alta densidade, e o texto
fica desfocado. A aplicação declara-se antes de abrir a primeira janela.

### O Tkinter

Vem com o instalador do python.org, mas é uma opção — *tcl/tk and IDLE* — que se
pode desmarcar. O `EXECUTAR.bat` confirma que existe antes de abrir a janela, e
diz como o instalar se faltar.

### Onde ficam as definições

`%APPDATA%\VMwareFleetConsole` — a pasta **itinerante**, e não a local, de
propósito: as definições e as impressões digitais dos certificados aceites devem
seguir o utilizador para outra máquina do domínio.

**Não há nenhuma ramificação por sistema operativo dentro desta versão**, e há
um teste que falha se alguém acrescentar uma.

## Correr os testes

```
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest        # os testes da janela saltam-se se não houver ecrã
python -m ruff check .
```

---

Toda a documentação — o que a aplicação faz, como decide, e o que não faz — está
no [README do projecto](../README.md).
