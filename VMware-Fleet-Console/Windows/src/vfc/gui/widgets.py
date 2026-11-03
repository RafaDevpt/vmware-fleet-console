#!/usr/bin/env python3
"""
PT-PT: As peças que se repetem: a tabela ordenável, a caixa de texto só de
       leitura e a base dos diálogos.

       **A tabela mantém a selecção quando o inventário se actualiza.** É a
       diferença entre uma interface que se pode usar com a actualização
       automática ligada e uma que tira a máquina de baixo do cursor de minuto
       a minuto — precisamente quando alguém está a ler o nome dela para a
       confirmar.

EN-UK: The repeated pieces: the sortable table, the read-only text box and the
       dialog base. The table keeps its selection across inventory refreshes —
       the difference between an interface usable with auto-refresh on and one
       that pulls the machine out from under the cursor every minute.

Created by Redfox using Claude
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from .. import __version__, branding
from .theme import Theme


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    width: int
    anchor: str = "w"
    stretch: bool = False


@dataclass(frozen=True)
class Row:
    """
    PT-PT: Uma linha. `sort` tem um valor por coluna para ordenar — números
           como números, para "9 GB" não vir depois de "10 GB".
    EN-UK: One row. `sort` holds one value per column for sorting — numbers as
           numbers, so "9 GB" does not come after "10 GB".
    """

    iid: str
    values: tuple[str, ...]
    sort: tuple[object, ...]
    tags: tuple[str, ...] = ()


class Table(ttk.Frame):
    """
    PT-PT: Uma `Treeview` com barra de deslocamento, ordenação por coluna e
           selecção preservada entre actualizações.
    EN-UK: A `Treeview` with a scrollbar, per-column sorting and selection kept
           across refreshes.
    """

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        columns: list[Column],
        on_select: Callable[[], None] | None = None,
        selectmode: str = "browse",
        height: int = 12,
    ) -> None:
        super().__init__(master)
        self.columns = columns
        self._linhas: list[Row] = []
        self._ordem: tuple[int, bool] = (0, False)
        self.tree = ttk.Treeview(
            self, columns=[c.key for c in columns], show="headings", selectmode=selectmode, height=height
        )
        for indice, coluna in enumerate(columns):
            self.tree.heading(coluna.key, text=coluna.title, anchor=coluna.anchor,
                              command=lambda i=indice: self._sort_by(i))
            self.tree.column(coluna.key, width=coluna.width, minwidth=40, anchor=coluna.anchor,
                             stretch=coluna.stretch)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        lateral = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=barra.set, xscrollcommand=lateral.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        lateral.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        theme.register(self.tree, "tree")
        if on_select is not None:
            self.tree.bind("<<TreeviewSelect>>", lambda _e: on_select(), add="+")

    def set_rows(self, rows: list[Row]) -> None:
        """
        PT-PT: Substitui as linhas, mantendo a selecção, o foco e a ordenação.
        EN-UK: Replaces the rows, keeping selection, focus and sort order.
        """
        seleccionadas = set(self.tree.selection())
        foco = self.tree.focus()
        topo = self.tree.yview()[0]
        self._linhas = rows
        self.tree.delete(*self.tree.get_children())
        for linha in self._sorted():
            self.tree.insert("", "end", iid=linha.iid, values=linha.values, tags=linha.tags)
        self._stripe()
        ainda = [i for i in seleccionadas if self.tree.exists(i)]
        if ainda:
            self.tree.selection_set(ainda)
        if foco and self.tree.exists(foco):
            self.tree.focus(foco)
        self.tree.yview_moveto(topo)

    def selected(self) -> list[str]:
        return list(self.tree.selection())

    def _sorted(self) -> list[Row]:
        indice, inverso = self._ordem

        def chave(linha: Row) -> tuple[int, object]:
            valor = linha.sort[indice] if indice < len(linha.sort) else ""
            # PT-PT: Os vazios vão sempre para o fim, numa ordem ou na outra.
            # EN-UK: Blanks always sink to the end, either way round.
            if valor is None or valor == "":
                return (1, "")
            return (0, valor.casefold() if isinstance(valor, str) else valor)

        cheias = [linha for linha in self._linhas if chave(linha)[0] == 0]
        vazias = [linha for linha in self._linhas if chave(linha)[0] == 1]
        try:
            cheias.sort(key=lambda linha: chave(linha)[1], reverse=inverso)  # type: ignore[arg-type,return-value]
        except TypeError:
            cheias.sort(key=lambda linha: str(chave(linha)[1]), reverse=inverso)
        return cheias + vazias

    def _sort_by(self, indice: int) -> None:
        actual, inverso = self._ordem
        self._ordem = (indice, not inverso if actual == indice else False)
        for i, coluna in enumerate(self.columns):
            seta = ""
            if i == indice:
                seta = "  ▼" if self._ordem[1] else "  ▲"
            self.tree.heading(coluna.key, text=coluna.title + seta)
        self.set_rows(self._linhas)

    def _stripe(self) -> None:
        for posicao, iid in enumerate(self.tree.get_children()):
            tags = [t for t in self.tree.item(iid, "tags") if t != "par"]
            if posicao % 2:
                tags.append("par")
            self.tree.item(iid, tags=tags)


class ReadOnlyText(ttk.Frame):
    """
    PT-PT: Texto só de leitura, seleccionável e copiável — para detalhes,
           registos e relatórios.
    EN-UK: Read-only text, selectable and copyable — for details, logs and
           reports.
    """

    def __init__(self, master: tk.Misc, theme: Theme, height: int = 6, wrap: str = "word") -> None:
        super().__init__(master)
        self.text = tk.Text(self, height=height, wrap=wrap, borderwidth=0)
        theme.register(self.text, "text")
        barra = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=barra.set, state="disabled")
        self.text.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def set(self, parts: list[tuple[str, str]]) -> None:
        """
        PT-PT: Substitui o conteúdo. `parts` são pares (texto, etiqueta).
        EN-UK: Replaces the content. `parts` are (text, tag) pairs.
        """
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for texto, etiqueta in parts:
            self.text.insert("end", texto, etiqueta or ())
        self.text.configure(state="disabled")

    def append(self, texto: str, etiqueta: str = "") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", texto, etiqueta or ())
        self.text.see("end")
        self.text.configure(state="disabled")


class Dialog(tk.Toplevel):
    """
    PT-PT: A base dos diálogos: modal, centrado sobre a janela, Esc fecha,
           e o título leva a assinatura como as outras janelas.

           `result` fica `None` quando se fecha sem confirmar — que é a
           resposta de omissão de qualquer diálogo desta aplicação.

    EN-UK: The dialog base: modal, centred on the window, Esc closes, and the
           title carries the signature like the other windows. `result` stays
           `None` when closed without confirming — every dialog's default.
    """

    def __init__(self, master: tk.Misc, theme: Theme, title: str) -> None:
        super().__init__(master)
        self.theme = theme
        self.result: object | None = None
        self.withdraw()
        self.title(branding.window_title(__version__, title))
        theme.register(self, "toplevel")
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _e: self.cancel())
        self.body = ttk.Frame(self, padding=22)
        self.body.pack(fill="both", expand=True)

    def show(self) -> object | None:
        """
        PT-PT: Mostra o diálogo e espera que se feche. Devolve `result`.
        EN-UK: Shows the dialog and waits for it to close. Returns `result`.
        """
        self.update_idletasks()
        dono = self.master.winfo_toplevel()
        x = dono.winfo_rootx() + max((dono.winfo_width() - self.winfo_reqwidth()) // 2, 0)
        y = dono.winfo_rooty() + max((dono.winfo_height() - self.winfo_reqheight()) // 3, 0)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()
        self.grab_set()
        self.focus_force()
        self.wait_window(self)
        return self.result

    def accept(self, result: object) -> None:
        self.result = result
        self.grab_release()
        self.destroy()

    def cancel(self) -> None:
        self.result = None
        self.grab_release()
        self.destroy()

    def buttons(self, row: int, ok_text: str, ok_style: str = "Accent.TButton",
                cancel_text: str = "Cancelar") -> ttk.Button:
        """
        PT-PT: A fila de botões no fundo. Devolve o de confirmar.
        EN-UK: The button row at the bottom. Returns the confirm one.
        """
        fila = ttk.Frame(self.body)
        fila.grid(row=row, column=0, columnspan=4, sticky="e", pady=(18, 0))
        ttk.Button(fila, text=cancel_text, command=self.cancel).pack(side="right")
        ok = ttk.Button(fila, text=ok_text, style=ok_style, command=self.on_ok)
        ok.pack(side="right", padx=(0, 8))
        return ok

    def on_ok(self) -> None:  # pragma: no cover - cada diálogo define o seu
        raise NotImplementedError
