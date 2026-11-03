# VMware Fleet Console — versão para Linux

**Esta pasta é a aplicação completa para Linux.** As versões de Windows e macOS
vivem nas pastas ao lado e não são precisas aqui.

*This folder is the complete Linux application. The Windows and macOS versions
live in the folders alongside and are not needed here.*

<sub>Created by Redfox using Claude</sub>

---

## Arrancar

```bash
./executar.sh
```

Na primeira execução cria o ambiente virtual e instala as dependências. Nas
seguintes abre logo a janela, que pergunta primeiro **a que tipo de servidor se
liga** — ESXi ou vCenter — e depois o servidor, o utilizador e a senha.

Se o repositório foi clonado por uma máquina Windows, o bit de execução
perde-se:

```bash
chmod +x executar.sh cli.sh
```

## Exportar máquinas para OVF

No separador **Máquinas**, escolha uma ou várias (Ctrl ou Shift) e carregue em
**Exportar máquinas…**. O que acontece a cada máquina — pronta, vai ser
encerrada, ou recusada e porquê — vê-se **antes** de confirmar. O detalhe está no
[README do projecto](../README.md#exportação-para-ovf--ovf-export).

## Modo de texto

```bash
./cli.sh --servidor vcenter.empresa.local --utilizador administrator@vsphere.local
./cli.sh --json --seccao estado
```

Códigos de saída: **0** nada a apontar, **1** avisos, **2** críticos, **3** não
foi possível ligar, **4** a assinatura da aplicação foi alterada. O modo de
texto só lê: as operações e a exportação vivem na janela.

## O que esta máquina precisa

```bash
./executar.sh --diagnostico
```

| Requisito | Porquê | Sem ele |
| :--- | :--- | :--- |
| Python 3.10+ | — | não arranca |
| `pyvmomi` | a biblioteca da VMware | não há ligação nenhuma |
| Tkinter (`python3-tk`, `python3-tkinter`, `tk`…) | a janela | resta o modo de texto |
| Ambiente gráfico (`DISPLAY` ou `WAYLAND_DISPLAY`) | a janela | resta o modo de texto |

O `python3-venv` e o Tkinter são pacotes à parte na maior parte das
distribuições. O `executar.sh` e o `--diagnostico` dizem o comando certo para a
sua se faltarem.

## O que é diferente nesta versão

O `src/vfc/platform_support.py` é o único ficheiro que difere entre as três
versões. Nesta, o que ele sabe e as outras não é **qual é a distribuição** — lê
o `/etc/os-release` para escolher entre `apt`, `dnf`, `pacman`, `zypper` e `apk`,
e usa o `ID_LIKE` para cobrir derivadas que não estão na lista.

Também é aqui que se verifica se a janela pode abrir: se há Tkinter e um
ambiente gráfico. Num servidor ou numa sessão SSH sem `-X` não há, e a
aplicação abre em modo de texto em vez de rebentar.

A pasta de dados segue o XDG: `$XDG_CONFIG_HOME/VMwareFleetConsole`, ou
`~/.config/VMwareFleetConsole`.

**Não há nenhuma ramificação por sistema operativo dentro desta versão**, e há
um teste que falha se alguém acrescentar uma.

## Correr os testes

```bash
pip install -r requirements-dev.txt
python -m pytest        # os testes da janela saltam-se se não houver ecrã
python -m ruff check .
```

---

Toda a documentação — o que a aplicação faz, como decide, e o que não faz — está
no [README do projecto](../README.md).
