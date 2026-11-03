#!/usr/bin/env python3
"""
PT-PT: A interface gráfica da VMware Fleet Console (Tkinter).

       Substitui, na 2.0, a interface de texto. A escolha do Tkinter é
       deliberada: vem com o Python do python.org em Windows e macOS, não pede
       nenhuma instalação a mais — o que, num posto de trabalho com o acesso à
       internet filtrado, é a diferença entre a aplicação abrir ou não — e o
       tema `clam` deixa-a igual nos três sistemas.

       É o único pacote da aplicação que importa o `tkinter`. O resto —
       ligação, recolha, regras, guardas, exportação — não sabe que há uma
       janela, e por isso testa-se sem ela.

EN-UK: The graphical interface (Tkinter), replacing the text interface in 2.0.
       Tkinter ships with python.org's Python on Windows and macOS and needs
       nothing extra installed — on a workstation with filtered internet, the
       difference between opening and not. This is the only package importing
       `tkinter`; everything else is window-agnostic and tested without one.

Created by Redfox using Claude
"""

from __future__ import annotations

from .app import FleetApp, run

__all__ = ["FleetApp", "run"]
