#!/usr/bin/env python3
"""
PT-PT: Particularidades do Windows.

       Esta é a versão para Windows da VMware Fleet Console. Não há aqui nenhuma
       ramificação por sistema operativo: o código sabe onde está e diz apenas o
       que é verdade nesta máquina. As outras duas versões vivem nas pastas ao
       lado, cada uma com o seu equivalente deste ficheiro.

       O que existe aqui e nas outras não existe são três coisas que só em
       Windows dão problemas:

       **O `python.exe` da Microsoft Store.** Uma instalação limpa do Windows
       traz um `python.exe` no PATH que não é o Python: é um atalho que abre a
       loja. Quem o corre vê a Store abrir-se e não percebe porquê. Detecta-se
       pelo caminho (`WindowsApps`) e diz-se o que é, em vez de deixar alguém
       concluir que o programa está avariado.

       **A nitidez da janela.** Num portátil com a escala do ecrã a 125% ou
       150%, o Windows estica as janelas das aplicações que não se declaram
       preparadas para alta densidade, e o texto fica desfocado. A aplicação
       declara-se, antes de abrir a primeira janela.

       **A página de código**, que só importa ao modo de texto. É a causa
       número um de "sai tudo aos quadradinhos" em Windows. A 65001 é a UTF-8, e é a única em que os caracteres de
       desenho e os acentos saem certos.

EN-UK: Windows specifics.

       This is the Windows version. There is no operating-system branching here:
       the code knows where it is and states only what is true on this machine.

       Three things go wrong only on Windows. The Microsoft Store `python.exe` is
       a shim that opens the Store rather than running Python, and whoever runs
       it sees the Store open and does not understand why — it is detected by its
       path and named. Windows stretches — and blurs — the windows of
       applications that do not declare high-DPI awareness; this one declares
       it before its first window. And, for text mode, the code page is the number-one cause of "it all comes out as boxes":
       65001 is UTF-8, and the only one where the drawing characters and the
       accents come out right.

Created by Redfox using Claude
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

SYSTEM_NAME = "Windows"


@dataclass(frozen=True)
class Requirement:
    """
    PT-PT: Um requisito de sistema e o seu estado.

           `essential` separa o que impede a aplicação de funcionar do que
           apenas desliga uma funcionalidade. Apresentar os dois com a mesma
           gravidade levaria alguém a instalar coisas de que não precisa — e,
           pior, a desistir por causa de um aviso que não importava.

    EN-UK: A system requirement and its state. `essential` separates what stops
           the application working from what merely switches a feature off.
    """

    name: str
    present: bool
    essential: bool
    detail: str
    command: str = ""

    def __str__(self) -> str:
        estado = "OK" if self.present else ("EM FALTA" if self.essential else "em falta (opcional)")
        linha = f"{self.name}: {estado}"
        if self.detail:
            linha += f"\n    {self.detail}"
        if not self.present and self.command:
            linha += f"\n    {self.command}"
        return linha


def is_store_python(executable: str | None = None) -> bool:
    """
    PT-PT: Se este Python é o atalho da Microsoft Store.

           Uma instalação limpa do Windows traz um `python.exe` no PATH que abre
           a loja em vez de correr Python. Quem o corre vê a Store abrir-se e não
           percebe o que aconteceu. Reconhece-se pelo caminho.

    EN-UK: Whether this Python is the Microsoft Store shim. A clean Windows
           carries a `python.exe` on the PATH that opens the Store instead of
           running Python. It is recognised by its path.

    >>> is_store_python(r"C:\\Users\\x\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe")
    True
    >>> is_store_python(r"C:\\Python312\\python.exe")
    False
    """
    caminho = (executable if executable is not None else sys.executable).replace("/", "\\").lower()
    return "\\microsoft\\windowsapps\\" in caminho


def code_page() -> int:
    """
    PT-PT: A página de código activa da consola.

           A 65001 é a UTF-8. A 850 e a 1252 são as de omissão em Portugal, e são
           a causa número um de "sai tudo aos quadradinhos". Devolve 0 quando não
           se conseguiu saber, que é diferente de estar errada.

    EN-UK: The console's active code page. 65001 is UTF-8; 850 and 1252 are the
           usual defaults here and the number-one cause of box characters.
           Returns 0 when it could not be determined, which is different from
           being wrong.
    """
    try:
        saida = subprocess.run(  # noqa: S603
            ["chcp.com"], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    digitos = "".join(c for c in saida if c.isdigit())
    try:
        return int(digitos)
    except ValueError:
        return 0


def app_data_dir(app_name: str) -> Path:
    """
    PT-PT: A pasta de dados, na convenção do Windows: `%APPDATA%`.

           Sem a variável, cai-se em `~/AppData/Roaming`, que é o que ela vale.
           A pasta itinerante e não a local de propósito: as definições e as
           impressões digitais dos certificados devem seguir o utilizador para
           outra máquina do domínio.

    EN-UK: The data folder, in the Windows convention: `%APPDATA%`. Roaming and
           not local on purpose — the settings and certificate fingerprints
           should follow the user to another machine on the domain.
    """
    base = os.environ.get("APPDATA", "")
    raiz = Path(base) if base else Path.home() / "AppData" / "Roaming"
    return raiz / app_name


# PT-PT: As letras da interface. A Segoe UI é a do próprio Windows desde o
#        Vista; a Cascadia Mono vem com o Windows Terminal e a Consolas com
#        qualquer Windows — o Tk escolhe a primeira que existir.
# EN-UK: The interface fonts. Segoe UI is Windows' own since Vista; Cascadia
#        Mono ships with Windows Terminal and Consolas with every Windows — Tk
#        picks the first that exists.
UI_FONT_FAMILIES = ("Segoe UI", "Tahoma")
MONO_FONT_FAMILIES = ("Cascadia Mono", "Consolas", "Courier New")
UI_FONT_SIZE = 10


def tkinter_available() -> bool:
    """
    PT-PT: Se o Tkinter está instalado. Vem com o instalador do python.org,
           mas é uma opção ("tcl/tk and IDLE") que se pode desmarcar.
    EN-UK: Whether Tkinter is installed. It ships with the python.org installer,
           but as an option ("tcl/tk and IDLE") that can be unticked.
    """
    try:
        import tkinter  # noqa: F401,PLC0415
    except ImportError:
        return False
    return True


def gui_available() -> bool:
    """
    PT-PT: Se dá para abrir a janela. Em Windows há sempre um ambiente gráfico;
           a única coisa que pode faltar é o Tkinter.
    EN-UK: Whether the window can open. Windows always has a desktop; the only
           thing that can be missing is Tkinter.
    """
    return tkinter_available()


def prepare_gui() -> None:
    """
    PT-PT: Avisa o Windows de que a aplicação sabe desenhar em ecrãs de alta
           densidade.

           Sem isto, num portátil com a escala a 125% ou 150% — que é quase
           todos — o Windows desenha a janela em pequeno e estica-a, e o texto
           fica desfocado. Tem de ser chamado antes de a primeira janela
           existir. Numa versão do Windows sem a função, segue-se sem ela: a
           janela fica desfocada, mas abre.

    EN-UK: Tells Windows the application can draw on high-density screens.
           Without it, on a laptop at 125% or 150% scaling — nearly all of them —
           Windows draws the window small and stretches it, blurring the text.
           Must be called before the first window exists. Without the function,
           it carries on: blurry, but open.
    """
    try:
        import ctypes  # noqa: PLC0415

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except (AttributeError, OSError) as erro:
        _log.debug("Sem consciência de DPI: %s", erro)


def open_path(path: Path) -> None:
    """
    PT-PT: Abre uma pasta ou um ficheiro no Explorador, como um duplo clique.
    EN-UK: Opens a folder or file in Explorer, like a double click.
    """
    os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606


def unicode_is_safe() -> bool:
    """
    PT-PT: Se dá para desenhar caixas sem sair uma sopa de caracteres.

           Verifica-se a codificação da saída, e não só a página de código: o
           Python moderno em Windows usa UTF-8 na saída mesmo com a consola numa
           página antiga, e nesse caso os caracteres saem bem.

    EN-UK: Whether box-drawing will render. The output encoding is checked rather
           than only the code page: modern Python on Windows uses UTF-8 on output
           even with the console on an old code page, and then the characters do
           come out right.
    """
    codificacao = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    return "utf8" in codificacao or code_page() == 65001


def python_is_recent() -> bool:
    """PT-PT: Se a versão do Python chega. / EN-UK: Whether the Python is recent enough."""
    return sys.version_info >= (3, 10)


def check_requirements() -> list[Requirement]:
    """
    PT-PT: O estado desta máquina para correr a aplicação.

           É o que sai em `--diagnostico`, e é a primeira coisa a pedir a alguém
           que diz que "não abre".

    EN-UK: This machine's state for running the application. It is what
           `--diagnostico` prints, and the first thing to ask for from somebody
           saying "it does not open".
    """
    requisitos: list[Requirement] = [
        Requirement(
            name="Python",
            present=python_is_recent(),
            essential=True,
            detail=f"encontrado {platform.python_version()}, é preciso 3.10 ou superior",
            command="instale de python.org e marque 'Add Python to PATH'",
        ),
        Requirement(
            name="Origem do Python",
            present=not is_store_python(),
            essential=True,
            detail=(
                "atalho da Microsoft Store — abre a loja em vez de correr Python"
                if is_store_python()
                else sys.executable
            ),
            command=(
                "instale de python.org, e em Definições > Aplicações > Aliases de execução "
                "desligue os do python.exe"
            ),
        ),
    ]

    try:
        import pyVmomi  # noqa: F401,PLC0415

        tem_pyvmomi = True
    except ImportError:
        tem_pyvmomi = False

    requisitos.append(
        Requirement(
            name="pyVmomi",
            present=tem_pyvmomi,
            essential=True,
            detail="a biblioteca da VMware: sem ela não há ligação nenhuma ao vSphere",
            command="pip install -r requirements.txt",
        )
    )

    requisitos.append(
        Requirement(
            name="Tkinter",
            present=tkinter_available(),
            essential=False,
            detail="a interface gráfica; sem ela resta o modo de texto (--texto)",
            command=(
                "volte a correr o instalador do python.org, escolha 'Modify' e marque "
                "'tcl/tk and IDLE'"
            ),
        )
    )

    pagina = code_page()
    requisitos.append(
        Requirement(
            name="Codificação",
            present=unicode_is_safe(),
            essential=False,
            detail=f"página de código {pagina or 'desconhecida'}, stdout em "
            f"{getattr(sys.stdout, 'encoding', '(desconhecida)')}",
            command="chcp 65001   (põe a consola em UTF-8 nesta sessão)",
        )
    )

    return requisitos


def diagnostic_report() -> str:
    """
    PT-PT: O relatório de diagnóstico em texto.
    EN-UK: The diagnostic report as text.
    """
    linhas = [
        "VMware Fleet Console — diagnóstico",
        f"Sistema: {SYSTEM_NAME} {platform.release()} ({platform.version()})",
        f"Python:  {platform.python_version()} em {sys.executable}",
        f"Dados:   {app_data_dir('VMwareFleetConsole')}",
        "",
    ]
    linhas.extend(str(r) for r in check_requirements())
    em_falta = [r for r in check_requirements() if not r.present and r.essential]
    linhas.append("")
    linhas.append(
        "Falta o essencial — a aplicação não arranca assim."
        if em_falta
        else "Está tudo o que é essencial."
    )
    return "\n".join(linhas)


def missing_essentials() -> list[Requirement]:
    """PT-PT: Só o que impede. / EN-UK: Only what blocks."""
    return [r for r in check_requirements() if not r.present and r.essential]
