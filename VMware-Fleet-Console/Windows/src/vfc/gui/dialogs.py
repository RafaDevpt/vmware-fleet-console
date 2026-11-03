#!/usr/bin/env python3
"""
PT-PT: Os diálogos: o certificado, as confirmações, o snapshot, a exportação
       e o "Sobre".

       Todos seguem a mesma regra: **a resposta de omissão é não fazer nada**.
       Fechar a janela, carregar em Esc ou em Cancelar devolve `None`, e só o
       botão de confirmar faz alguma coisa acontecer. Quando a operação não tem
       volta, o botão só fica activo depois de se escrever o nome do objecto —
       e quem decide se o que se escreveu chega é a guarda em `actions.py`, não
       este ficheiro.

EN-UK: The dialogs. Every one follows the same rule: **the default answer is to
       do nothing**. Closing, Esc or Cancel return `None`; only the confirm
       button makes anything happen. When the operation cannot be undone, that
       button only enables once the object's name is typed — and whether the
       typing suffices is decided by the guard in `actions.py`, not here.

Created by Redfox using Claude
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

from .. import __version__, branding, export
from ..actions import Guard
from ..connection import TrustDecision, TrustResult
from ..models import PowerState, VMInfo, format_bytes
from .theme import Theme
from .widgets import Column, Dialog, ReadOnlyText, Row, Table

WRAP = 520


# ---------------------------------------------------------------------------
# PT-PT: O certificado.
# EN-UK: The certificate.
# ---------------------------------------------------------------------------


class TrustDialog(Dialog):
    """
    PT-PT: A decisão sobre um certificado que esta máquina não consegue validar.
           O botão por omissão é Recusar, e a impressão digital está num campo
           que se pode seleccionar e copiar, para a comparar sem a reescrever.
    EN-UK: The decision on a certificate this machine cannot validate. The
           default button is Refuse, and the fingerprint sits in a selectable
           field so it can be compared without retyping.
    """

    def __init__(self, master: tk.Misc, theme: Theme, resultado: TrustResult, anfitriao: str) -> None:
        super().__init__(master, theme, "Certificado do servidor")
        mudou = resultado.decision is TrustDecision.FINGERPRINT_CHANGED
        b = self.body
        ttk.Label(
            b,
            text="A impressão digital do certificado MUDOU" if mudou else "Certificado por confirmar",
            style="Crit.TLabel" if mudou else "Subtitle.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        explicacao = (
            f"O certificado que {anfitriao} apresenta agora não é o que foi aceite antes. Isto "
            "acontece quando o certificado é regenerado — mas também quando não se está a falar "
            "com o servidor de sempre. Confirme na consola do servidor antes de aceitar."
            if mudou
            else f"{anfitriao} apresenta um certificado que este computador não consegue validar — "
            "o normal num ESXi ou vCenter com o certificado de fábrica. Compare a impressão "
            "digital com a que o servidor mostra. Nenhuma credencial é enviada até decidir."
        )
        ttk.Label(b, text=explicacao, wraplength=WRAP + 120, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 14))

        ttk.Label(b, text="Impressão digital SHA-256", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        # PT-PT: Em duas linhas de dezasseis pares, que é como cabe à vista e
        #        como se compara metade a metade com o ecrã do servidor.
        # EN-UK: In two lines of sixteen pairs: how it fits the eye and how it
        #        is compared half by half against the server's screen.
        completa = resultado.certificate.fingerprint_sha256
        pares = completa.split(":")
        caixa = ReadOnlyText(b, theme, height=2, wrap="none")
        caixa.text.configure(width=50)
        caixa.set([(":".join(pares[:16]) + "\n" + ":".join(pares[16:]), "mono")])
        caixa.grid(row=3, column=0, sticky="w", pady=(2, 4))
        ttk.Button(b, text="Copiar a impressão digital",
                   command=lambda: (self.clipboard_clear(), self.clipboard_append(completa))).grid(
            row=3, column=1, sticky="nw", padx=(10, 0), pady=(2, 0))

        cert = resultado.certificate
        detalhes = ttk.Frame(b)
        detalhes.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for linha, (rotulo, valor) in enumerate(
            (("Sujeito", cert.subject or "—"), ("Emissor", cert.issuer or "—"), ("Válido até", cert.not_after or "—"))
        ):
            ttk.Label(detalhes, text=rotulo, style="Muted.TLabel").grid(row=linha, column=0, sticky="nw", padx=(0, 12))
            ttk.Label(detalhes, text=valor, wraplength=WRAP - 90, justify="left").grid(row=linha, column=1, sticky="w")

        ttk.Label(
            b,
            text="Onde ver a impressão digital: no ESXi, na consola directa (DCUI) › View Support "
            "Information; no vCenter, em Administration › Certificates › Machine SSL Certificate.",
            style="Small.TLabel", wraplength=WRAP + 120, justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(14, 0))

        self.result = False
        fila = ttk.Frame(b)
        fila.grid(row=6, column=0, columnspan=2, sticky="e", pady=(18, 0))
        recusar = ttk.Button(fila, text="Recusar", command=self.cancel)
        recusar.pack(side="right")
        ttk.Button(fila, text="Confiar e ligar", style="Danger.TButton" if mudou else "Accent.TButton",
                   command=lambda: self.accept(True)).pack(side="right", padx=(0, 8))
        recusar.focus_set()


# ---------------------------------------------------------------------------
# PT-PT: Confirmação escrita.
# EN-UK: Typed confirmation.
# ---------------------------------------------------------------------------


class ConfirmDialog(Dialog):
    """
    PT-PT: Pede que se escreva o nome do objecto. O botão só acende quando a
           guarda aceita o que está escrito, e é o texto escrito — não um
           "sim" — que segue para a operação, que o volta a verificar.
    EN-UK: Asks for the object's name to be typed. The button only lights up
           once the guard accepts the text, and it is the typed text — not a
           "yes" — that goes on to the operation, which checks it again.
    """

    def __init__(self, master: tk.Misc, theme: Theme, guarda: Guard, assunto: str) -> None:
        super().__init__(master, theme, guarda.action.label)
        self.guarda = guarda
        b = self.body
        ttk.Label(b, text=f"{guarda.action.label} — {assunto}", style="Subtitle.TLabel").grid(
            row=0, column=0, sticky="w")
        if guarda.warning:
            ttk.Label(b, text=guarda.warning, wraplength=WRAP, justify="left", style="Warn.TLabel").grid(
                row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(b, text=f"Para confirmar, escreva:  {guarda.confirmation}", wraplength=WRAP).grid(
            row=2, column=0, sticky="w", pady=(14, 4))
        self.texto = tk.StringVar()
        campo = ttk.Entry(b, textvariable=self.texto, width=44)
        campo.grid(row=3, column=0, sticky="ew")
        self.ok = self.buttons(4, guarda.action.label, "Danger.TButton" if guarda.action.destructive else "Accent.TButton")
        self.ok.state(["disabled"])
        self.texto.trace_add("write", lambda *_a: self._validar())
        campo.bind("<Return>", lambda _e: self.on_ok())
        campo.focus_set()

    def _validar(self) -> None:
        self.ok.state(["!disabled"] if self.guarda.accepts(self.texto.get()) else ["disabled"])

    def on_ok(self) -> None:
        if self.guarda.accepts(self.texto.get()):
            self.accept(self.texto.get())


# ---------------------------------------------------------------------------
# PT-PT: Snapshot.
# EN-UK: Snapshot.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotRequest:
    name: str
    description: str
    with_memory: bool


class SnapshotDialog(Dialog):
    """
    PT-PT: Criar um snapshot. A memória vem desligada, e o porquê está escrito
           ao lado: incluí-la escreve no datastore tanto quanto a máquina tem de
           RAM.
    EN-UK: Create a snapshot. Memory comes unticked, with the reason written
           beside it: including it writes as much to the datastore as the
           machine has RAM.
    """

    def __init__(self, master: tk.Misc, theme: Theme, vm: VMInfo) -> None:
        super().__init__(master, theme, "Criar snapshot")
        b = self.body
        ttk.Label(b, text=f"Snapshot de {vm.name}", style="Subtitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(b, text="Nome", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(14, 2))
        self.nome = tk.StringVar(value=f"vfc {datetime.now():%Y-%m-%d %H:%M}")
        campo = ttk.Entry(b, textvariable=self.nome, width=48)
        campo.grid(row=2, column=0, sticky="ew")
        ttk.Label(b, text="Descrição", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 2))
        self.descricao = tk.StringVar(value=f"Criado pela {branding.APP_NAME}")
        ttk.Entry(b, textvariable=self.descricao, width=48).grid(row=4, column=0, sticky="ew")
        self.memoria = tk.BooleanVar(value=False)
        caixa = ttk.Checkbutton(b, text="Incluir a memória da máquina", variable=self.memoria)
        caixa.grid(row=5, column=0, sticky="w", pady=(14, 2))
        if vm.power_state is not PowerState.ON:
            caixa.state(["disabled"])
        ttk.Label(
            b,
            text=(
                f"Com memória, o snapshot restaura sem reiniciar, mas escreve no datastore mais "
                f"{format_bytes(vm.memory_bytes)}. Sem memória, e com as VMware Tools a correr, os "
                "discos são postos num estado consistente antes do snapshot."
            ),
            style="Small.TLabel", wraplength=WRAP, justify="left",
        ).grid(row=6, column=0, sticky="w")
        self.buttons(7, "Criar snapshot")
        campo.focus_set()
        campo.select_range(0, "end")

    def on_ok(self) -> None:
        nome = self.nome.get().strip()
        if nome:
            self.accept(SnapshotRequest(nome, self.descricao.get().strip(), bool(self.memoria.get())))


# ---------------------------------------------------------------------------
# PT-PT: Exportação.
# EN-UK: Export.
# ---------------------------------------------------------------------------

SHUTDOWN_WORD = "ENCERRAR"


@dataclass(frozen=True)
class ExportRequest:
    jobs: list[export.ExportJob]
    destination: Path
    shutdown_timeout_minutes: int


class ExportDialog(Dialog):
    """
    PT-PT: Preparar uma exportação: que máquinas, para onde, e o que acontece
           às que estão ligadas.

           A lista mostra, para cada máquina, o que lhe vai acontecer **antes**
           de se carregar no botão — pronta, vai ser encerrada, ou recusada e
           porquê. Se alguma vai ser encerrada, escreve-se ENCERRAR para
           confirmar. Se o destino pode não ter espaço, diz-se, e é preciso
           dizer que se sabe.

    EN-UK: Preparing an export: which machines, where to, and what happens to
           the running ones. The list shows each machine's fate **before** the
           button is pressed. If any will be shut down, ENCERRAR must be typed.
           If the destination may lack space, that is said and must be
           acknowledged.
    """

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        vms: list[VMInfo],
        fleet: object,
        endpoint_host: str,
        endpoint_addresses: set[str],
        destino_inicial: str,
        prazo_minutos: int,
    ) -> None:
        super().__init__(master, theme, "Exportar máquinas")
        self.resizable(True, False)
        self.vms = vms
        self.fleet = fleet
        self.endpoint_host = endpoint_host
        self.endpoint_addresses = endpoint_addresses
        self.decisoes: list[export.ExportCheck] = []
        b = self.body
        b.columnconfigure(0, weight=1)

        ttk.Label(b, text="Exportar para OVF", style="Subtitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            b,
            text=(
                "Cada máquina é copiada inteira — disco, hardware virtual, placas de rede — para uma "
                "pasta com o .ovf, os discos e um manifesto SHA-256, pronta a importar no vSphere. O "
                "vSphere só exporta máquinas desligadas."
            ),
            wraplength=640, justify="left", style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 12))

        lista = ttk.Frame(b)
        lista.grid(row=2, column=0, columnspan=3, sticky="ew")
        lista.columnconfigure(0, weight=1)
        self.tabela = Table(
            lista, theme,
            [
                Column("nome", "Máquina", 200),
                Column("estado", "Estado", 90),
                Column("tamanho", "Disco usado", 115, "e"),
                Column("destino", "O que vai acontecer", 320, stretch=True),
            ],
            height=min(max(len(vms), 3), 9),
        )
        self.tabela.grid(row=0, column=0, sticky="ew")
        # PT-PT: A razão completa de cada recusa — na tabela não cabe, e uma
        #        recusa sem razão é uma porta fechada sem placa.
        # EN-UK: The full reason for each refusal — it does not fit in the
        #        table, and a refusal without a reason is a door with no sign.
        self.recusas = ttk.Label(lista, text="", style="Small.TLabel", wraplength=700, justify="left")

        self.encerrar = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            b,
            text="Encerrar pelo sistema convidado (VMware Tools) as máquinas que estão ligadas, e "
            "exportá-las uma a uma",
            variable=self.encerrar, command=self._recalcular,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 4))

        opcoes = ttk.Frame(b)
        opcoes.grid(row=4, column=0, columnspan=3, sticky="w", padx=(26, 0))
        ttk.Label(opcoes, text="Depois da cópia:", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.religar = tk.BooleanVar(value=True)
        self._radios = [
            ttk.Radiobutton(opcoes, text="voltar a ligá-la", variable=self.religar, value=True,
                            command=self._recalcular),
            ttk.Radiobutton(opcoes, text="deixá-la desligada (para manutenção do anfitrião)",
                            variable=self.religar, value=False, command=self._recalcular),
        ]
        self._radios[0].grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._radios[1].grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Label(opcoes, text="Esperar pelo encerramento até", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        self.prazo = tk.IntVar(value=max(1, min(prazo_minutos, 120)))
        self._prazo = ttk.Spinbox(opcoes, from_=1, to=120, width=5, textvariable=self.prazo)
        self._prazo.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(opcoes, text="min — se não encerrar, não é forçada", style="Muted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(6, 0), pady=(6, 0))

        ttk.Label(b, text="Destino", style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(14, 2))
        self.destino = tk.StringVar(value=destino_inicial)
        ttk.Entry(b, textvariable=self.destino).grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Button(b, text="Escolher…", command=self._escolher).grid(row=6, column=2, sticky="e", padx=(8, 0))
        self.espaco = ttk.Label(b, text="", style="Muted.TLabel")
        self.espaco.grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.sei_espaco = tk.BooleanVar(value=False)
        self._caixa_espaco = ttk.Checkbutton(
            b, text="Sei que pode não caber — o OVF sai normalmente mais pequeno do que o disco usado",
            variable=self.sei_espaco, command=self._validar,
        )
        ttk.Label(
            b,
            text="Uma partilha de rede (\\\\servidor\\partilha) serve. A mesma máquina que vai ser "
            "intervencionada, não: uma cópia guardada no próprio servidor desaparece com ele.",
            style="Small.TLabel", wraplength=640, justify="left",
        ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.confirmacao = tk.StringVar()
        self._rotulo_conf = ttk.Label(b, text=f"Há máquinas que vão ser encerradas. Para confirmar, escreva:  {SHUTDOWN_WORD}")
        self._campo_conf = ttk.Entry(b, textvariable=self.confirmacao, width=20)

        self.ok = self.buttons(12, "Exportar")
        self.destino.trace_add("write", lambda *_a: self._agendar_espaco())
        self.confirmacao.trace_add("write", lambda *_a: self._validar())
        self.prazo.trace_add("write", lambda *_a: self._validar())
        self._pendente: str | None = None
        self._livre: int | None = None
        self._recalcular()
        self._medir_espaco()

    # -- PT-PT: Decisões. / EN-UK: Decisions. --------------------------------

    def _recalcular(self) -> None:
        encerrar = bool(self.encerrar.get())
        self.decisoes = [
            export.check_export(vm, self.fleet, encerrar, self.endpoint_host, self.endpoint_addresses)  # type: ignore[arg-type]
            for vm in self.vms
        ]
        linhas = []
        for decisao in self.decisoes:
            vm = decisao.vm
            if not decisao.allowed:
                texto, etiqueta = f"Recusada — {decisao.reason}", "critico"
            elif decisao.needs_shutdown:
                fim = "voltar a ser ligada" if self.religar.get() else "ficar desligada"
                texto, etiqueta = f"Vai ser encerrada, exportada e {fim}", "aviso"
            else:
                texto, etiqueta = "Pronta — já está desligada", "ok"
            linhas.append(Row(vm.moid, (vm.name, vm.power_state.label, format_bytes(vm.committed_bytes), texto),
                              (vm.name, vm.power_state.label, vm.committed_bytes or 0, texto), (etiqueta,)))
        self.tabela.set_rows(linhas)
        recusadas = [d for d in self.decisoes if not d.allowed]
        if recusadas:
            self.recusas.configure(text="\n".join(f"{d.vm.name}: {d.reason}" for d in recusadas))
            self.recusas.grid(row=1, column=0, sticky="w", pady=(6, 0))
        else:
            self.recusas.grid_remove()
        for radio in self._radios:
            radio.state(["!disabled"] if encerrar else ["disabled"])
        self._prazo.state(["!disabled"] if encerrar else ["disabled"])
        if any(d.needs_shutdown for d in self.decisoes):
            self._rotulo_conf.grid(row=10, column=0, columnspan=3, sticky="w", pady=(14, 4))
            self._campo_conf.grid(row=11, column=0, sticky="w")
        else:
            self._rotulo_conf.grid_remove()
            self._campo_conf.grid_remove()
        self._mostrar_espaco()

    def _escolher(self) -> None:
        pasta = filedialog.askdirectory(parent=self, title="Destino da exportação",
                                        initialdir=self.destino.get() or str(Path.home()), mustexist=False)
        if pasta:
            self.destino.set(pasta)

    def _agendar_espaco(self) -> None:
        # PT-PT: Medir uma partilha de rede pode demorar um segundo; não se mede
        #        a cada tecla.
        # EN-UK: Measuring a network share can take a second; not on every key.
        if self._pendente is not None:
            self.after_cancel(self._pendente)
        self._pendente = self.after(450, self._medir_espaco)

    def _medir_espaco(self) -> None:
        self._pendente = None
        caminho = self.destino.get().strip()
        self._livre = None
        if caminho:
            alvo = Path(caminho)
            while not alvo.exists() and alvo.parent != alvo:
                alvo = alvo.parent
            self._livre = export.free_bytes(alvo) if alvo.exists() else None
        self._mostrar_espaco()

    def _mostrar_espaco(self) -> None:
        necessario = export.estimated_bytes(self.decisoes)
        if not self.destino.get().strip():
            self.espaco.configure(text="Escolha a pasta de destino.", style="Muted.TLabel")
        elif self._livre is None:
            self.espaco.configure(text="Não foi possível medir o espaço livre neste destino.", style="Warn.TLabel")
        else:
            curto = self._livre < necessario
            self.espaco.configure(
                text=f"Livre no destino: {format_bytes(self._livre)}   ·   Disco usado pelas máquinas "
                f"(tecto): {format_bytes(necessario)}",
                style="Warn.TLabel" if curto else "Muted.TLabel",
            )
        if self._falta_espaco():
            self._caixa_espaco.grid(row=8, column=0, columnspan=3, sticky="w", pady=(2, 0))
        else:
            self._caixa_espaco.grid_remove()
        self._validar()

    def _falta_espaco(self) -> bool:
        return self._livre is not None and self._livre < export.estimated_bytes(self.decisoes)

    def _validar(self) -> bool:
        valido = (
            bool(self.destino.get().strip())
            and any(d.allowed for d in self.decisoes)
            and (not any(d.needs_shutdown for d in self.decisoes)
                 or self.confirmacao.get().strip().upper() == SHUTDOWN_WORD)
            and (not self._falta_espaco() or bool(self.sei_espaco.get()))
            and self._prazo_valido() is not None
        )
        self.ok.state(["!disabled"] if valido else ["disabled"])
        return valido

    def _prazo_valido(self) -> int | None:
        try:
            minutos = int(self.prazo.get())
        except (tk.TclError, ValueError):
            return None
        return minutos if 1 <= minutos <= 120 else None

    def on_ok(self) -> None:
        if not self._validar():
            return
        religar = bool(self.religar.get())
        trabalhos = [export.ExportJob(d, power_on_after=religar) for d in self.decisoes if d.allowed]
        self.accept(ExportRequest(trabalhos, Path(self.destino.get().strip()), self._prazo_valido() or 10))


# ---------------------------------------------------------------------------
# PT-PT: Texto e "Sobre".
# EN-UK: Text and "About".
# ---------------------------------------------------------------------------


class TextDialog(Dialog):
    """PT-PT: Um texto longo, só de leitura (o diagnóstico). / EN-UK: Long read-only text."""

    def __init__(self, master: tk.Misc, theme: Theme, title: str, text: str) -> None:
        super().__init__(master, theme, title)
        self.resizable(True, True)
        ttk.Label(self.body, text=title, style="Subtitle.TLabel").grid(row=0, column=0, sticky="w")
        caixa = ReadOnlyText(self.body, theme, height=20, wrap="none")
        caixa.text.configure(width=96)
        caixa.set([(text, "mono")])
        caixa.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.body.rowconfigure(1, weight=1)
        self.body.columnconfigure(0, weight=1)
        fila = ttk.Frame(self.body)
        fila.grid(row=2, column=0, sticky="e", pady=(14, 0))
        ttk.Button(fila, text="Fechar", command=self.cancel).pack(side="right")
        ttk.Button(fila, text="Copiar", command=lambda: self._copiar(text)).pack(side="right", padx=(0, 8))

    def _copiar(self, texto: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(texto)


class AboutDialog(Dialog):
    """PT-PT: Sobre a aplicação. / EN-UK: About the application."""

    def __init__(self, master: tk.Misc, theme: Theme) -> None:
        super().__init__(master, theme, "Sobre")
        b = self.body
        ttk.Label(b, text=branding.APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(b, text=f"Versão {__version__}", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(
            b,
            text=(
                "Estado, manutenção e exportação de máquinas de um vCenter ou de um anfitrião ESXi, "
                "sem abrir o cliente web."
            ),
            wraplength=WRAP, justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(12, 12))
        ttk.Label(b, text=f"© {datetime.now():%Y} {branding.AUTHOR}", style="Strong.TLabel").grid(
            row=3, column=0, sticky="w")
        ttk.Label(b, text="Licença MIT — o aviso de autoria tem de ser mantido em todas as cópias.",
                  style="Muted.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Label(b, text=branding.CREDIT, style="Info.TLabel").grid(row=5, column=0, sticky="w", pady=(12, 0))
        fila = ttk.Frame(b)
        fila.grid(row=6, column=0, sticky="e", pady=(18, 0))
        ttk.Button(fila, text="Fechar", style="Accent.TButton", command=self.cancel).pack(side="right")
