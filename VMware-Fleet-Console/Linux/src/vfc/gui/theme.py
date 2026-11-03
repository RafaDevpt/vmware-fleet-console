#!/usr/bin/env python3
"""
PT-PT: O aspecto da interface: cores, letras e estilos.

       Construído sobre o tema `clam` do Tk, porque é o único dos temas que vêm
       com o Tk que deixa mudar a cor de tudo — e por isso o único em que a
       aplicação fica igual em Windows, Linux e macOS, em claro e em escuro.

       **Uma regra herdada da versão de texto e mantida aqui:** a cor nunca é a
       única informação. Um crítico diz "Crítico" escrito, um aviso diz "Aviso".
       Cerca de um em cada doze homens não distingue vermelho de verde, e uma
       ferramenta de operações que comunique o essencial só por cor não serve a
       essa pessoa.

       Os widgets clássicos do Tk (texto, menus) não obedecem aos estilos do
       `ttk`. Ficam registados aqui com `register`, para que mudar de tema os
       repinte também.

EN-UK: The interface's look: colours, fonts and styles. Built on Tk's `clam`
       theme, the only bundled theme that lets every colour change — so the
       application looks the same on Windows, Linux and macOS, light and dark.
       Colour is never the only information: a critical says "Critical" in
       words. Classic Tk widgets (text, menus) ignore `ttk` styles; they are
       registered here so a theme change repaints them too.

Created by Redfox using Claude
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk

from .. import platform_support


@dataclass(frozen=True)
class Palette:
    """PT-PT: Uma paleta. / EN-UK: A palette."""

    bg: str
    surface: str
    raised: str
    stripe: str
    border: str
    text: str
    muted: str
    accent: str
    accent_active: str
    accent_text: str
    select: str
    ok: str
    warn: str
    crit: str
    info: str
    header: str


PALETTES: dict[str, Palette] = {
    "escuro": Palette(
        bg="#14171b",
        surface="#1b1f25",
        raised="#252a32",
        stripe="#1f242b",
        border="#323944",
        text="#e6e9ed",
        muted="#97a1ad",
        accent="#3d8bfd",
        accent_active="#2f72d8",
        accent_text="#ffffff",
        select="#1d3a63",
        ok="#3fb950",
        warn="#e3b341",
        crit="#f2555a",
        info="#58a6ff",
        header="#0f1215",
    ),
    "claro": Palette(
        bg="#f2f4f7",
        surface="#ffffff",
        raised="#e9edf2",
        stripe="#f6f8fa",
        border="#d3d9e1",
        text="#1d232b",
        muted="#5b6573",
        accent="#1f6feb",
        accent_active="#1858c4",
        accent_text="#ffffff",
        select="#d6e6fd",
        ok="#1a7f37",
        warn="#9a6700",
        crit="#cf222e",
        info="#0969da",
        header="#ffffff",
    ),
}

DEFAULT_THEME = "escuro"


class Theme:
    """
    PT-PT: O tema activo e os widgets clássicos que têm de ser repintados.
    EN-UK: The active theme and the classic widgets that need repainting.
    """

    def __init__(self, root: tk.Tk, name: str) -> None:
        self.root = root
        self.name = name if name in PALETTES else DEFAULT_THEME
        self.style = ttk.Style(root)
        self._classicos: list[tuple[tk.Misc, str]] = []
        self.ui_font = _first_family(root, platform_support.UI_FONT_FAMILIES)
        self.mono_font = _first_family(root, platform_support.MONO_FONT_FAMILIES)
        self._configure_fonts()
        self.apply(self.name)

    @property
    def palette(self) -> Palette:
        return PALETTES[self.name]

    # -- PT-PT: Letras. / EN-UK: Fonts. --------------------------------------

    def _configure_fonts(self) -> None:
        tamanho = platform_support.UI_FONT_SIZE
        for nome in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                fonte = tkfont.nametofont(nome)
            except tk.TclError:
                continue
            if self.ui_font:
                fonte.configure(family=self.ui_font)
            fonte.configure(size=tamanho)
        try:
            fixa = tkfont.nametofont("TkFixedFont")
            if self.mono_font:
                fixa.configure(family=self.mono_font)
            fixa.configure(size=tamanho)
        except tk.TclError:
            pass
        # PT-PT: Sem nenhuma das preferidas, fica a família que o Tk já usa —
        #        lida pelo nome real, porque "TkDefaultFont" dentro de um tuplo
        #        não é a fonte com esse nome, é uma família que não existe.
        # EN-UK: With none of the preferred ones, keep Tk's own family — read by
        #        its real name, since "TkDefaultFont" inside a tuple is not the
        #        named font but a family that does not exist.
        familia = self.ui_font or str(tkfont.nametofont("TkDefaultFont").actual("family"))
        if not self.mono_font:
            self.mono_font = str(tkfont.nametofont("TkFixedFont").actual("family"))
        self.fonts = {
            "normal": (familia, tamanho),
            "bold": (familia, tamanho, "bold"),
            "small": (familia, max(tamanho - 1, 8)),
            "title": (familia, tamanho + 8, "bold"),
            "subtitle": (familia, tamanho + 3, "bold"),
            "mono": (self.mono_font or "TkFixedFont", tamanho),
        }
        linha = tkfont.Font(root=self.root, font=self.fonts["normal"]).metrics("linespace")
        self.row_height = int(linha * 1.9)

    # -- PT-PT: Estilos. / EN-UK: Styles. ------------------------------------

    def apply(self, name: str) -> None:
        """
        PT-PT: Aplica uma paleta a tudo — estilos `ttk` e widgets registados.
        EN-UK: Applies a palette to everything — `ttk` styles and registered
               widgets.
        """
        self.name = name if name in PALETTES else DEFAULT_THEME
        p = self.palette
        s = self.style
        s.theme_use("clam")
        f = self.fonts

        s.configure(
            ".",
            background=p.bg,
            foreground=p.text,
            font=f["normal"],
            bordercolor=p.border,
            lightcolor=p.border,
            darkcolor=p.border,
            troughcolor=p.raised,
            focuscolor=p.accent,
            selectbackground=p.select,
            selectforeground=p.text,
            fieldbackground=p.surface,
            insertcolor=p.text,
            arrowcolor=p.muted,
        )
        s.map(".", foreground=[("disabled", p.muted)])

        for nome, fundo in (("TFrame", p.bg), ("Surface.TFrame", p.surface), ("Header.TFrame", p.header)):
            s.configure(nome, background=fundo)
        s.configure("Card.TFrame", background=p.surface, bordercolor=p.border, relief="solid", borderwidth=1)

        s.configure("TLabel", background=p.bg, foreground=p.text)
        s.configure("Muted.TLabel", foreground=p.muted)
        s.configure("Small.TLabel", foreground=p.muted, font=f["small"])
        s.configure("Title.TLabel", font=f["title"])
        s.configure("Subtitle.TLabel", font=f["subtitle"])
        s.configure("Strong.TLabel", font=f["bold"])
        for fundo_nome, fundo in (("Surface", p.surface), ("Header", p.header)):
            s.configure(f"{fundo_nome}.TLabel", background=fundo)
            s.configure(f"{fundo_nome}.Muted.TLabel", background=fundo, foreground=p.muted)
            s.configure(f"{fundo_nome}.Small.TLabel", background=fundo, foreground=p.muted, font=f["small"])
            s.configure(f"{fundo_nome}.Title.TLabel", background=fundo, font=f["title"])
            s.configure(f"{fundo_nome}.Subtitle.TLabel", background=fundo, font=f["subtitle"])
            s.configure(f"{fundo_nome}.Strong.TLabel", background=fundo, font=f["bold"])
            for estado, cor in (("Ok", p.ok), ("Warn", p.warn), ("Crit", p.crit), ("Info", p.info)):
                s.configure(f"{fundo_nome}.{estado}.TLabel", background=fundo, foreground=cor, font=f["bold"])
        for estado, cor in (("Ok", p.ok), ("Warn", p.warn), ("Crit", p.crit), ("Info", p.info)):
            s.configure(f"{estado}.TLabel", foreground=cor, font=f["bold"])
        s.configure("Credit.TLabel", background=p.raised, foreground=p.muted, font=f["small"])
        s.configure("Status.TLabel", background=p.raised, foreground=p.text, font=f["small"])
        s.configure("Status.TFrame", background=p.raised)

        s.configure("TButton", background=p.raised, foreground=p.text, padding=(14, 6), relief="flat",
                    bordercolor=p.border, focusthickness=1, focuscolor=p.accent)
        s.map(
            "TButton",
            background=[("disabled", p.bg), ("pressed", p.border), ("active", p.border)],
            foreground=[("disabled", p.muted)],
        )
        s.configure("Accent.TButton", background=p.accent, foreground=p.accent_text, bordercolor=p.accent,
                    font=f["bold"])
        s.map(
            "Accent.TButton",
            background=[("disabled", p.raised), ("pressed", p.accent_active), ("active", p.accent_active)],
            foreground=[("disabled", p.muted)],
            bordercolor=[("disabled", p.border)],
        )
        s.configure("Danger.TButton", background=p.crit, foreground="#ffffff", bordercolor=p.crit, font=f["bold"])
        s.map(
            "Danger.TButton",
            background=[("disabled", p.raised), ("active", p.crit)],
            foreground=[("disabled", p.muted)],
        )
        s.configure("TMenubutton", background=p.raised, foreground=p.text, padding=(12, 6), relief="flat",
                    arrowcolor=p.muted)
        s.map("TMenubutton", background=[("active", p.border), ("disabled", p.bg)],
              foreground=[("disabled", p.muted)])

        s.configure("TEntry", fieldbackground=p.surface, foreground=p.text, padding=6, insertcolor=p.text)
        s.map("TEntry", bordercolor=[("focus", p.accent)], fieldbackground=[("readonly", p.raised)])
        s.configure("TSpinbox", fieldbackground=p.surface, foreground=p.text, padding=4, arrowcolor=p.muted,
                    background=p.raised)
        s.map("TSpinbox", bordercolor=[("focus", p.accent)])
        s.configure("TCombobox", fieldbackground=p.surface, foreground=p.text, padding=5, arrowcolor=p.muted,
                    background=p.raised)
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", p.surface)],
            foreground=[("readonly", p.text)],
            bordercolor=[("focus", p.accent)],
            background=[("active", p.border)],
        )
        self.root.option_add("*TCombobox*Listbox.background", p.surface)
        self.root.option_add("*TCombobox*Listbox.foreground", p.text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", p.select)
        self.root.option_add("*TCombobox*Listbox.selectForeground", p.text)
        self.root.option_add("*TCombobox*Listbox.font", f["normal"])

        for nome in ("TCheckbutton", "TRadiobutton"):
            s.configure(nome, background=p.bg, foreground=p.text, indicatorbackground=p.surface,
                        indicatorforeground=p.accent, indicatorcolor=p.surface, focuscolor=p.bg)
            s.map(nome, indicatorcolor=[("selected", p.accent), ("disabled", p.raised)],
                  background=[("active", p.bg)], foreground=[("disabled", p.muted)])
        s.configure("Surface.TCheckbutton", background=p.surface)
        s.map("Surface.TCheckbutton", background=[("active", p.surface)])
        s.configure("Surface.TRadiobutton", background=p.surface)
        s.map("Surface.TRadiobutton", background=[("active", p.surface)])

        # PT-PT: O seleccionador ESXi / vCenter: botões que ficam carregados.
        # EN-UK: The ESXi / vCenter picker: buttons that stay pressed.
        s.configure("Segment.Toolbutton", background=p.raised, foreground=p.muted, padding=(18, 8),
                    font=f["bold"], relief="flat", anchor="center")
        s.map(
            "Segment.Toolbutton",
            background=[("selected", p.accent), ("active", p.border)],
            foreground=[("selected", p.accent_text), ("active", p.text)],
        )

        s.configure("TNotebook", background=p.bg, borderwidth=0, tabmargins=(12, 8, 12, 0))
        s.configure("TNotebook.Tab", background=p.bg, foreground=p.muted, padding=(18, 8), borderwidth=0,
                    font=f["bold"])
        s.map(
            "TNotebook.Tab",
            background=[("selected", p.surface), ("active", p.raised)],
            foreground=[("selected", p.text), ("active", p.text)],
            lightcolor=[("selected", p.accent)],
            # PT-PT: O `clam` alarga o separador seleccionado; com o mesmo
            #        enchimento em todos os estados, ficam alinhados.
            # EN-UK: `clam` widens the selected tab; the same padding in every
            #        state keeps them aligned.
            padding=[("selected", (18, 8))],
            expand=[("selected", (0, 0, 0, 0))],
        )

        s.configure("Treeview", background=p.surface, fieldbackground=p.surface, foreground=p.text,
                    rowheight=self.row_height, bordercolor=p.border, borderwidth=0)
        s.map("Treeview", background=[("selected", p.select)], foreground=[("selected", p.text)])
        s.configure("Treeview.Heading", background=p.raised, foreground=p.muted, font=f["bold"],
                    relief="flat", padding=(8, 6), bordercolor=p.border)
        s.map("Treeview.Heading", background=[("active", p.border)])

        s.configure("TProgressbar", troughcolor=p.raised, background=p.accent, bordercolor=p.raised,
                    lightcolor=p.accent, darkcolor=p.accent, thickness=8)
        s.configure("TScrollbar", troughcolor=p.bg, background=p.raised, bordercolor=p.bg,
                    arrowcolor=p.muted, relief="flat")
        s.map("TScrollbar", background=[("active", p.border)])
        s.configure("TSeparator", background=p.border)
        s.configure("TLabelframe", background=p.bg, bordercolor=p.border)
        s.configure("TLabelframe.Label", background=p.bg, foreground=p.muted, font=f["bold"])
        s.configure("TPanedwindow", background=p.bg)

        self.root.configure(background=p.bg)
        for widget, tipo in list(self._classicos):
            self._paint(widget, tipo)

    # -- PT-PT: Os widgets clássicos. / EN-UK: Classic widgets. -------------

    def register(self, widget: tk.Misc, kind: str) -> tk.Misc:
        """
        PT-PT: Regista um widget (`text`, `menu`, `toplevel`, ou uma tabela com
               `tree`) para ser repintado a cada mudança de tema. Devolve-o,
               para encadear.
        EN-UK: Registers a classic widget to be repainted on each theme change.
        """
        self._classicos.append((widget, kind))
        widget.bind("<Destroy>", lambda _e, w=widget: self._forget(w), add="+")
        self._paint(widget, kind)
        return widget

    def _forget(self, widget: tk.Misc) -> None:
        self._classicos = [(w, k) for w, k in self._classicos if w is not widget]

    def _paint(self, widget: tk.Misc, kind: str) -> None:
        p = self.palette
        try:
            if kind == "text":
                widget.configure(  # type: ignore[call-arg]
                    background=p.surface, foreground=p.text, insertbackground=p.text,
                    selectbackground=p.select, selectforeground=p.text, highlightthickness=1,
                    highlightbackground=p.border, highlightcolor=p.accent, relief="flat",
                    font=self.fonts["normal"], padx=10, pady=8,
                )
                widget.tag_configure("critico", foreground=p.crit)  # type: ignore[attr-defined]
                widget.tag_configure("aviso", foreground=p.warn)  # type: ignore[attr-defined]
                widget.tag_configure("ok", foreground=p.ok)  # type: ignore[attr-defined]
                widget.tag_configure("info", foreground=p.info)  # type: ignore[attr-defined]
                widget.tag_configure("muted", foreground=p.muted)  # type: ignore[attr-defined]
                widget.tag_configure("bold", font=self.fonts["bold"])  # type: ignore[attr-defined]
                widget.tag_configure("mono", font=self.fonts["mono"])  # type: ignore[attr-defined]
            elif kind == "menu":
                widget.configure(  # type: ignore[call-arg]
                    background=p.surface, foreground=p.text, activebackground=p.select,
                    activeforeground=p.text, disabledforeground=p.muted, relief="flat",
                    borderwidth=1, font=self.fonts["normal"], selectcolor=p.accent,
                )
            elif kind == "tree":
                self.tree_tags(widget)  # type: ignore[arg-type]
            elif kind == "toplevel":
                widget.configure(background=p.bg)  # type: ignore[call-arg]
        except tk.TclError:
            pass

    def tree_tags(self, tree: ttk.Treeview) -> None:
        """
        PT-PT: As etiquetas de cor de uma tabela — gravidade e riscas.
        EN-UK: A table's colour tags — severity and stripes.
        """
        p = self.palette
        tree.tag_configure("critico", foreground=p.crit)
        tree.tag_configure("aviso", foreground=p.warn)
        tree.tag_configure("info", foreground=p.info)
        tree.tag_configure("ok", foreground=p.ok)
        tree.tag_configure("muted", foreground=p.muted)
        tree.tag_configure("par", background=p.stripe)


def _first_family(root: tk.Misc, candidatas: tuple[str, ...]) -> str:
    """
    PT-PT: A primeira família de letra que existe nesta máquina, ou texto vazio
           para deixar a do sistema.
    EN-UK: The first font family that exists on this machine, or empty to keep
           the system's.
    """
    existentes = {f.casefold() for f in tkfont.families(root)}
    return next((c for c in candidatas if c.casefold() in existentes), "")
