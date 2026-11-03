#!/usr/bin/env python3
"""
PT-PT: O ecrã de ligação.

       A primeira pergunta é **a que tipo de servidor se vai ligar**: um
       anfitrião ESXi directamente, ou um vCenter. A escolha muda o utilizador
       que se sugere (`root` contra `administrator@vsphere.local`) e, depois de
       ligar, é comparada com o que o servidor diz que é. Se não coincidir,
       pergunta-se antes de continuar: ligar ao ESXi a pensar que é o vCenter é
       a maneira mais fácil de ver metade do inventário e não perceber porquê.

       A senha não sai deste ecrã para lado nenhum a não ser para a ligação, e
       o campo é limpo assim que a tentativa acaba, corra bem ou mal.

EN-UK: The connection screen. The first question is **which kind of server**:
       an ESXi host directly, or a vCenter. The choice changes the suggested
       user and, once connected, is compared against what the server says it
       is; a mismatch is asked about before carrying on. The password goes
       nowhere but the connection, and the field is cleared as soon as the
       attempt ends, either way.

Created by Redfox using Claude
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk

from .. import __version__, branding
from ..config import Settings
from ..connection import DEFAULT_PORT
from .theme import Theme

KINDS = {
    "esxi": ("ESXi", "Um anfitrião, ligado directamente. Utilizador habitual: root.", "root"),
    "vcenter": (
        "vCenter",
        "Todo o inventário gerido pelo vCenter. Utilizador habitual: administrator@vsphere.local.",
        "administrator@vsphere.local",
    ),
}


@dataclass(frozen=True)
class ConnectRequest:
    kind: str
    host: str
    port: int
    username: str
    password: str


class ConnectView(ttk.Frame):
    """
    PT-PT: O cartão de ligação, centrado na janela.
    EN-UK: The connection card, centred in the window.
    """

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        settings: Settings,
        on_connect: Callable[[ConnectRequest], None],
        on_forget: Callable[[str], None],
    ) -> None:
        super().__init__(master)
        self.theme = theme
        self.settings = settings
        self._on_connect = on_connect
        self._on_forget = on_forget

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        cartao = ttk.Frame(self, style="Card.TFrame", padding=32)
        cartao.grid(row=1, column=0)
        cartao.columnconfigure(0, weight=1)

        ttk.Label(cartao, text=branding.APP_NAME, style="Surface.Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(cartao, text="Ligar a um servidor VMware", style="Surface.Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 20))

        ttk.Label(cartao, text="Tipo de servidor", style="Surface.Strong.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
        self.kind = tk.StringVar(value="esxi")
        segmento = ttk.Frame(cartao, style="Surface.TFrame")
        segmento.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        segmento.columnconfigure((0, 1), weight=1, uniform="seg")
        for coluna, chave in enumerate(("esxi", "vcenter")):
            ttk.Radiobutton(
                segmento, text=KINDS[chave][0], value=chave, variable=self.kind,
                style="Segment.Toolbutton", command=self._kind_changed,
            ).grid(row=0, column=coluna, sticky="ew", padx=(0, 4) if coluna == 0 else (4, 0))
        self.dica = ttk.Label(cartao, text="", style="Surface.Small.TLabel", wraplength=380, justify="left")
        self.dica.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 16))

        ttk.Label(cartao, text="Servidor", style="Surface.Strong.TLabel").grid(row=5, column=0, sticky="w")
        ttk.Label(cartao, text="Porta", style="Surface.Strong.TLabel").grid(row=5, column=1, sticky="w", padx=(10, 0))
        self.host = tk.StringVar()
        self.campo_host = ttk.Combobox(cartao, textvariable=self.host, width=34,
                                       values=[s.host for s in settings.servers])
        self.campo_host.grid(row=6, column=0, sticky="ew", pady=(4, 12))
        self.campo_host.bind("<<ComboboxSelected>>", lambda _e: self._fill_known())
        self.campo_host.bind("<FocusOut>", lambda _e: self._fill_known(only_if_empty=True))
        self.port = tk.StringVar(value=str(DEFAULT_PORT))
        ttk.Entry(cartao, textvariable=self.port, width=7).grid(row=6, column=1, sticky="w", padx=(10, 0), pady=(4, 12))

        ttk.Label(cartao, text="Utilizador", style="Surface.Strong.TLabel").grid(row=7, column=0, columnspan=2, sticky="w")
        self.username = tk.StringVar()
        ttk.Entry(cartao, textvariable=self.username).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        ttk.Label(cartao, text="Senha", style="Surface.Strong.TLabel").grid(row=9, column=0, columnspan=2, sticky="w")
        self.password = tk.StringVar()
        self.campo_senha = ttk.Entry(cartao, textvariable=self.password, show="•")
        self.campo_senha.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        ttk.Label(cartao, text="A senha nunca é guardada: é pedida a cada sessão.",
                  style="Surface.Small.TLabel").grid(row=11, column=0, columnspan=2, sticky="w")

        self.estado = ttk.Label(cartao, text="", style="Surface.Muted.TLabel", wraplength=380, justify="left")
        self.estado.grid(row=12, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.progresso = ttk.Progressbar(cartao, mode="indeterminate", length=380)

        fila = ttk.Frame(cartao, style="Surface.TFrame")
        fila.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self.esquecer = ttk.Button(fila, text="Esquecer este servidor", command=self._forget)
        self.esquecer.pack(side="left")
        self.ligar = ttk.Button(fila, text="Ligar", style="Accent.TButton", command=self._submit)
        self.ligar.pack(side="right")

        ttk.Label(self, text=f"{branding.APP_NAME} {__version__}  ·  {branding.CREDIT}",
                  style="Small.TLabel").grid(row=3, column=0, pady=(0, 14))

        for campo in (self.campo_host, self.campo_senha):
            campo.bind("<Return>", lambda _e: self._submit())
        self.host.trace_add("write", lambda *_a: self._update_forget())

        if settings.servers:
            self.host.set(settings.servers[0].host)
            self._fill_known()
        else:
            self._kind_changed()
        self._update_forget()
        (self.campo_senha if self.host.get() else self.campo_host).focus_set()

    # -- PT-PT: Preenchimento. / EN-UK: Filling in. -------------------------

    def _kind_changed(self) -> None:
        chave = self.kind.get()
        self.dica.configure(text=KINDS[chave][1])
        sugeridos = {k[2] for k in KINDS.values()}
        if not self.username.get().strip() or self.username.get().strip() in sugeridos:
            self.username.set(KINDS[chave][2])

    def _fill_known(self, only_if_empty: bool = False) -> None:
        guardado = self.settings.server_for(self.host.get())
        if guardado is None:
            return
        if only_if_empty and self.username.get().strip() not in ("", *(k[2] for k in KINDS.values())):
            return
        self.port.set(str(guardado.port or DEFAULT_PORT))
        if guardado.kind in KINDS:
            self.kind.set(guardado.kind)
        self._kind_changed()
        if guardado.username:
            self.username.set(guardado.username)
        if guardado.fingerprint:
            self.show_info(f"{guardado.display} — o certificado deste servidor já foi aceite antes.")

    def _update_forget(self) -> None:
        conhecido = self.settings.server_for(self.host.get()) is not None
        self.esquecer.state(["!disabled"] if conhecido else ["disabled"])

    def _forget(self) -> None:
        anfitriao = self.host.get().strip()
        if anfitriao:
            self._on_forget(anfitriao)
            self.campo_host.configure(values=[s.host for s in self.settings.servers])
            self._update_forget()
            self.show_info(f"{anfitriao} esquecido, com a impressão digital do certificado.")

    # -- PT-PT: Submeter. / EN-UK: Submitting. ------------------------------

    def _submit(self) -> None:
        if "disabled" in self.ligar.state():
            return
        anfitriao = self.host.get().strip()
        utilizador = self.username.get().strip()
        try:
            porta = int(self.port.get().strip() or DEFAULT_PORT)
        except ValueError:
            porta = 0
        if not anfitriao:
            self.show_error("Indique o endereço do servidor.")
            return
        if not 0 < porta < 65536:
            self.show_error("A porta tem de ser um número entre 1 e 65535 (normalmente 443).")
            return
        if not utilizador:
            self.show_error("Indique o utilizador.")
            return
        senha = self.password.get()
        if not senha:
            self.show_error("Indique a senha.")
            return
        self._on_connect(ConnectRequest(self.kind.get(), anfitriao, porta, utilizador, senha))

    def clear_password(self) -> None:
        self.password.set("")

    # -- PT-PT: Estado. / EN-UK: State. -------------------------------------

    def set_busy(self, texto: str) -> None:
        self.estado.configure(text=texto, style="Surface.Muted.TLabel")
        self.progresso.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.progresso.start(12)
        self.ligar.state(["disabled"])

    def _idle(self) -> None:
        self.progresso.stop()
        self.progresso.grid_remove()
        self.ligar.state(["!disabled"])

    def show_error(self, texto: str) -> None:
        self._idle()
        self.estado.configure(text=texto, style="Surface.Crit.TLabel")

    def show_info(self, texto: str) -> None:
        self._idle()
        self.estado.configure(text=texto, style="Surface.Muted.TLabel")
