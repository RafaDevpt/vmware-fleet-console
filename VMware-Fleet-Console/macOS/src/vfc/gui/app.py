#!/usr/bin/env python3
"""
PT-PT: A aplicação gráfica: a janela, a sessão, e o caminho de cada pedido.

       Este é o único sítio que junta as peças. O ecrã de ligação e o painel
       não falam com o vSphere: pedem aqui, e aqui decide-se o que vai para a
       thread do vSphere, o que precisa de um diálogo antes, e o que acontece
       quando corre mal.

       **A senha.** Entra por `connect`, viaja numa variável local até à
       chamada que abre a sessão, e o campo do ecrã é limpo logo a seguir. Não
       é guardada em atributo nenhum desta classe.

       **O certificado.** Primeiro avalia-se (`evaluate_trust`) sem enviar
       nada. Se ninguém o aceitou ainda, mostra-se a impressão digital e
       espera-se pela decisão. Só depois a senha sai.

EN-UK: The graphical application: the window, the session, and each request's
       path. The only place joining the pieces: the screens never talk to
       vSphere; they ask here, and this decides what goes to the vSphere
       thread, what needs a dialog first, and what happens when it fails. The
       password travels in a local variable to the call opening the session
       and is never kept in an attribute. The certificate is evaluated before
       anything is sent, and the password only leaves once it is trusted.

Created by Redfox using Claude
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from .. import (
    __version__,
    branding,
    cli,
    collect,
    config,
    connection,
    export,
    health,
    platform_support,
)
from ..actions import Guard, OperationRefusedError, Operations, explain_failure
from ..config import Server, Settings
from ..connection import Endpoint, TrustDecision, TrustResult
from ..models import Finding, Fleet, VMInfo
from .connect import KINDS, ConnectRequest, ConnectView
from .dashboard import Dashboard
from .dialogs import (
    AboutDialog,
    ConfirmDialog,
    ExportDialog,
    ExportRequest,
    SnapshotDialog,
    TextDialog,
    TrustDialog,
)
from .theme import Theme
from .worker import Worker

logger = logging.getLogger(__name__)


class FleetApp:
    """PT-PT: A aplicação. / EN-UK: The application."""

    def __init__(self, settings: Settings) -> None:
        platform_support.prepare_gui()
        self.settings = settings
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(branding.window_title(__version__))
        self.root.minsize(1080, 680)
        self.theme = Theme(self.root, settings.theme)
        self.worker = Worker(self.root)

        self.session: connection.Session | None = None
        self.operations: Operations | None = None
        self.fleet: Fleet | None = None
        self.findings: list[Finding] = []
        self.endpoint_addresses: set[str] = set()
        self.certificate_note = ""
        self.exporting = False
        self._cancelar_exportacao: threading.Event | None = None
        self._temporizador: str | None = None
        self._a_fechar = False
        self.view: ConnectView | Dashboard | None = None
        self._menubar: tk.Menu | None = None

        self.tema = tk.StringVar(value=self.theme.name)
        self.root.report_callback_exception = self._unexpected
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.bind_all("<F5>", lambda _e: self.refresh(manual=True))
        self.root.bind_all("<Control-s>", lambda _e: self.save_report())
        self.show_connect()

        largura, altura = 1280, 800
        x = max((self.root.winfo_screenwidth() - largura) // 2, 0)
        y = max((self.root.winfo_screenheight() - altura) // 3, 0)
        self.root.geometry(f"{largura}x{altura}+{x}+{y}")
        self.root.deiconify()

    def run(self) -> int:
        self.root.mainloop()
        return 0

    def _unexpected(self, tipo: type, erro: BaseException, rasto: object) -> None:
        """
        PT-PT: Uma falha não prevista dentro da janela. Vai para o registo com o
               rasto completo e é mostrada — arrancada sem consola, uma falha que
               só fosse escrita no `stderr` não chegava a ninguém.
        EN-UK: An unforeseen failure inside the window. Logged with the full
               traceback and shown — started with no console, a failure written
               only to `stderr` would reach nobody.
        """
        logger.error("Falha inesperada na interface", exc_info=(tipo, erro, rasto))  # type: ignore[arg-type]
        messagebox.showerror(
            "Falha inesperada",
            f"{erro}\n\nO detalhe ficou no registo: {config.log_dir() / 'consola.log'}",
            parent=self.root,
        )

    # =====================================================================
    # PT-PT: Ecrãs e menus.
    # EN-UK: Screens and menus.
    # =====================================================================

    def _set_view(self, vista: ConnectView | Dashboard) -> None:
        if self.view is not None:
            self.view.destroy()
        self.view = vista
        vista.pack(fill="both", expand=True)
        self._build_menu()

    def _build_menu(self) -> None:
        ligado = isinstance(self.view, Dashboard)
        if self._menubar is not None:
            self._menubar.destroy()
        barra = self.theme.register(tk.Menu(self.root), "menu")
        self._menubar = barra
        ficheiro = self.theme.register(tk.Menu(barra, tearoff=False), "menu")
        if ligado:
            ficheiro.add_command(label="Guardar relatório", accelerator="Ctrl+S", command=self.save_report)
            ficheiro.add_command(label="Exportar máquinas…", command=lambda: self._dashboard_export())
            ficheiro.add_separator()
            ficheiro.add_command(label="Terminar sessão", command=self.disconnect)
        ficheiro.add_command(label="Sair", command=self.quit)
        barra.add_cascade(label="Ficheiro", menu=ficheiro)

        ver = self.theme.register(tk.Menu(barra, tearoff=False), "menu")
        if ligado:
            ver.add_command(label="Actualizar", accelerator="F5", command=lambda: self.refresh(manual=True))
            ver.add_separator()
        ver.add_radiobutton(label="Tema escuro", value="escuro", variable=self.tema, command=self._change_theme)
        ver.add_radiobutton(label="Tema claro", value="claro", variable=self.tema, command=self._change_theme)
        barra.add_cascade(label="Ver", menu=ver)

        ajuda = self.theme.register(tk.Menu(barra, tearoff=False), "menu")
        ajuda.add_command(label="Diagnóstico desta máquina…", command=self._diagnostic)
        ajuda.add_command(label="Abrir a pasta do registo", command=lambda: self.open_path(config.log_dir()))
        ajuda.add_separator()
        ajuda.add_command(label=f"Sobre a {branding.APP_NAME}", command=lambda: AboutDialog(self.root, self.theme).show())
        barra.add_cascade(label="Ajuda", menu=ajuda)
        self.root.configure(menu=barra)

    def _change_theme(self) -> None:
        self.theme.apply(self.tema.get())
        self.settings.theme = self.theme.name
        config.save_settings(self.settings)

    def _diagnostic(self) -> None:
        TextDialog(self.root, self.theme, "Diagnóstico desta máquina", platform_support.diagnostic_report()).show()

    def show_connect(self, mensagem: str = "", erro: bool = False) -> None:
        self.root.title(branding.window_title(__version__))
        vista = ConnectView(self.root, self.theme, self.settings, self.connect, self._forget_server)
        self._set_view(vista)
        if mensagem:
            (vista.show_error if erro else vista.show_info)(mensagem)

    def _connect_view(self) -> ConnectView | None:
        return self.view if isinstance(self.view, ConnectView) else None

    def _dashboard(self) -> Dashboard | None:
        return self.view if isinstance(self.view, Dashboard) else None

    def _forget_server(self, anfitriao: str) -> None:
        if self.settings.forget(anfitriao):
            config.save_settings(self.settings)

    # =====================================================================
    # PT-PT: Ligação.
    # EN-UK: Connection.
    # =====================================================================

    def connect(self, pedido: ConnectRequest) -> None:
        vista = self._connect_view()
        if vista is None:
            return
        vista.set_busy(f"A verificar o certificado de {pedido.host}…")
        guardado = self.settings.server_for(pedido.host)
        impressao = guardado.fingerprint if guardado and guardado.port == pedido.port else ""
        self.worker.submit(
            lambda: connection.evaluate_trust(pedido.host, pedido.port, impressao, float(self.settings.connect_timeout)),
            on_done=lambda r: self._trust_evaluated(r, pedido),  # type: ignore[arg-type]
            on_error=lambda e: self._connect_failed(f"Falha inesperada: {e}"),
        )

    def _trust_evaluated(self, resultado: TrustResult, pedido: ConnectRequest) -> None:
        if resultado.decision is TrustDecision.UNREACHABLE:
            self._connect_failed(resultado.message)
            return
        # PT-PT: O que fica escrito no cabeçalho do painel sobre o certificado
        #        desta sessão: a impressão digital fixada, ou que a cadeia
        #        valida.
        # EN-UK: What the dashboard header says about this session's
        #        certificate: the pinned fingerprint, or that the chain is valid.
        self.certificate_note = (
            "certificado validado por uma autoridade"
            if resultado.decision is TrustDecision.VALID_CHAIN
            else f"certificado fixado {resultado.certificate.short_fingerprint}"
        )
        if resultado.may_connect:
            impressao = resultado.certificate.fingerprint_sha256 if resultado.decision is TrustDecision.PINNED_MATCH else ""
            self._open_session(pedido, impressao)
            return
        aceite = TrustDialog(self.root, self.theme, resultado, pedido.host).show()
        if not aceite:
            self._connect_failed("Certificado recusado. Nenhuma credencial foi enviada para o servidor.")
            return
        impressao = resultado.certificate.fingerprint_sha256
        self._remember(pedido, impressao)
        self._open_session(pedido, impressao)

    def _open_session(self, pedido: ConnectRequest, impressao: str) -> None:
        vista = self._connect_view()
        if vista is not None:
            vista.set_busy(f"A ligar a {pedido.host} e a ler o inventário…")
        senha = pedido.password
        alvo = Endpoint(host=pedido.host, username=pedido.username, port=pedido.port)
        prazo = float(self.settings.connect_timeout)

        def abrir() -> tuple[connection.Session, Fleet, set[str]]:
            sessao = connection.connect(alvo, senha, impressao, timeout=prazo)
            try:
                parque = collect.collect_fleet(sessao)
                enderecos = export.resolve_addresses(pedido.host)
            except Exception:
                sessao.close()
                raise
            return sessao, parque, enderecos

        def falhou(erro: BaseException) -> None:
            if isinstance(erro, connection.VSphereConnectionError):
                self._connect_failed(str(erro))
            else:
                logger.exception("Falha inesperada ao ligar", exc_info=erro)
                self._connect_failed(f"Falha inesperada: {erro}")

        self.worker.submit(abrir, on_done=lambda r: self._session_opened(r, pedido), on_error=falhou)  # type: ignore[arg-type]
        if vista is not None:
            # PT-PT: A senha já seguiu na chamada; o campo não tem de a guardar.
            # EN-UK: The password has gone with the call; the field need not keep it.
            vista.clear_password()

    def _session_opened(self, resultado: tuple[connection.Session, Fleet, set[str]], pedido: ConnectRequest) -> None:
        sessao, parque, enderecos = resultado
        real = "vcenter" if sessao.is_vcenter else "esxi"
        if real != pedido.kind:
            continuar = messagebox.askyesno(
                "Tipo de servidor diferente",
                f"Escolheu {KINDS[pedido.kind][0]}, mas {pedido.host} é um {KINDS[real][0]} "
                f"({sessao.product}).\n\nContinuar ligado a este {KINDS[real][0]}?",
                parent=self.root,
            )
            if not continuar:
                self.worker.submit(sessao.close)
                self._connect_failed("Ligação cancelada: o servidor não é do tipo escolhido.")
                return

        self._remember(ConnectRequest(real, pedido.host, pedido.port, pedido.username, ""), "")
        self.session = sessao
        self.operations = Operations(sessao)
        self.endpoint_addresses = enderecos
        logger.info("%s — sessão aberta em %s como %s", branding.CREDIT, pedido.host, pedido.username)

        self.root.title(branding.window_title(__version__, pedido.host))
        self._set_view(Dashboard(self.root, self.theme, self))
        self._fleet_updated(parque)
        self._schedule_refresh()
        if parque.read_only_reason:
            messagebox.showwarning("Licenciamento", parque.read_only_reason, parent=self.root)

    def _remember(self, pedido: ConnectRequest, impressao: str) -> None:
        guardado = self.settings.server_for(pedido.host)
        self.settings.remember(Server(
            label=guardado.label if guardado else pedido.host,
            host=pedido.host,
            username=pedido.username,
            port=pedido.port,
            fingerprint=impressao,
            kind=pedido.kind,
        ))
        config.save_settings(self.settings)

    def _connect_failed(self, mensagem: str) -> None:
        vista = self._connect_view()
        if vista is not None:
            vista.clear_password()
            vista.show_error(mensagem)
        else:
            messagebox.showerror("Ligação", mensagem, parent=self.root)

    def disconnect(self) -> None:
        if self.exporting:
            messagebox.showinfo("Exportação em curso",
                                "Há uma exportação a correr. Cancele-a, ou espere que acabe, antes de terminar a sessão.",
                                parent=self.root)
            return
        self._stop_refresh()
        sessao = self.session
        self.session = self.operations = self.fleet = None
        if sessao is not None:
            self.worker.submit(sessao.close)
        self.show_connect("Sessão terminada.")

    # =====================================================================
    # PT-PT: Inventário.
    # EN-UK: Inventory.
    # =====================================================================

    def refresh(self, manual: bool = False) -> None:
        painel = self._dashboard()
        if self.session is None or painel is None:
            return
        if self.exporting:
            if manual:
                painel.set_status("A actualização fica parada enquanto a exportação corre.", "aviso")
            return
        if self.worker.busy:
            if manual:
                painel.set_status("Já há um pedido ao servidor a correr — espere que termine.", "aviso")
            return
        sessao = self.session
        painel.set_busy(True, False)
        self.worker.submit(lambda: collect.collect_fleet(sessao), on_done=self._fleet_updated,  # type: ignore[arg-type]
                           on_error=self._refresh_failed)

    def _fleet_updated(self, parque: Fleet) -> None:
        painel = self._dashboard()
        if painel is None:
            return
        self.fleet = parque
        self.findings = health.evaluate(parque, self.settings.thresholds())  # type: ignore[arg-type]
        painel.update_fleet(parque, self.findings)
        painel.set_busy(False, self.exporting)

    def _refresh_failed(self, erro: BaseException) -> None:
        painel = self._dashboard()
        logger.error("Falha a actualizar o inventário: %s", erro)
        if painel is not None:
            painel.set_busy(False, self.exporting)
            painel.set_status(f"Não foi possível actualizar — {explain_failure(erro)}", "erro")

    def _schedule_refresh(self) -> None:
        self._stop_refresh()
        if self.settings.refresh_seconds > 0:
            self._temporizador = self.root.after(self.settings.refresh_seconds * 1000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self._temporizador = None
        if self.session is None:
            return
        # PT-PT: Com um diálogo aberto, não se mexe nas tabelas por baixo dele.
        # EN-UK: With a dialog open, the tables beneath it stay still.
        if self.root.grab_current() is None:
            self.refresh()
        self._schedule_refresh()

    def _stop_refresh(self) -> None:
        if self._temporizador is not None:
            self.root.after_cancel(self._temporizador)
            self._temporizador = None

    # =====================================================================
    # PT-PT: Operações.
    # EN-UK: Operations.
    # =====================================================================

    def run_operation(self, chamada: Callable[[Operations], object]) -> None:
        painel = self._dashboard()
        operacoes = self.operations
        if painel is None or operacoes is None:
            return
        if self.exporting:
            painel.set_status("As operações ficam paradas enquanto a exportação corre.", "aviso")
            return
        painel.set_status("A pedir ao servidor…")

        def feito(resultado: object) -> None:
            painel.set_status(str(getattr(resultado, "message", "Pedido enviado.")))
            # PT-PT: Relê pouco depois, para o ecrã mostrar o estado novo.
            # EN-UK: Re-reads shortly after so the screen shows the new state.
            self.root.after(2500, self.refresh)

        def falhou(erro: BaseException) -> None:
            if isinstance(erro, OperationRefusedError):
                painel.set_status(str(erro), "aviso")
                messagebox.showwarning("Operação recusada", str(erro), parent=self.root)
                return
            logger.error("Falha a executar a operação: %s", erro)
            texto = explain_failure(erro)
            painel.set_status(texto, "erro")
            messagebox.showerror("O servidor recusou", texto, parent=self.root)

        self.worker.submit(lambda: chamada(operacoes), on_done=feito, on_error=falhou)

    def confirm_and_run(self, guarda: Guard, assunto: str, chamada: Callable[..., object], alvo: object) -> None:
        """
        PT-PT: Pede a confirmação escrita e entrega o texto à operação, que o
               volta a passar pela guarda.
        EN-UK: Asks for the typed confirmation and hands the text to the
               operation, which runs it through the guard again.
        """
        texto = ConfirmDialog(self.root, self.theme, guarda, assunto).show()
        if isinstance(texto, str):
            self.run_operation(lambda o: chamada(o, alvo, texto))

    def create_snapshot(self, vm: VMInfo) -> None:
        pedido = SnapshotDialog(self.root, self.theme, vm).show()
        if pedido is not None:
            self.run_operation(lambda o: o.snapshot_create(
                vm, pedido.name, pedido.description, with_memory=pedido.with_memory))  # type: ignore[attr-defined]

    # =====================================================================
    # PT-PT: Exportação.
    # EN-UK: Export.
    # =====================================================================

    def _dashboard_export(self) -> None:
        painel = self._dashboard()
        if painel is not None:
            painel.notebook.select(1)
            vms = painel.selected_vms()
            if vms:
                self.open_export_dialog(vms)
            else:
                painel.set_status("Escolha uma ou mais máquinas no separador Máquinas.", "aviso")

    def open_export_dialog(self, vms: list[VMInfo]) -> None:
        painel = self._dashboard()
        if painel is None or self.session is None or self.exporting:
            return
        destino = self.settings.export_dir or str(config.reports_dir() / "Exportações")
        pedido = ExportDialog(
            self.root, self.theme, vms, self.fleet, self.session.endpoint.host, self.endpoint_addresses,
            destino, self.settings.shutdown_timeout_minutes,
        ).show()
        if isinstance(pedido, ExportRequest):
            self._start_export(pedido)

    def _start_export(self, pedido: ExportRequest) -> None:
        painel = self._dashboard()
        sessao = self.session
        if painel is None or sessao is None:
            return
        self.settings.export_dir = str(pedido.destination)
        self.settings.shutdown_timeout_minutes = pedido.shutdown_timeout_minutes
        config.save_settings(self.settings)

        self.exporting = True
        self._cancelar_exportacao = threading.Event()
        painel.set_busy(False, True)
        painel.export_panel.started(pedido.jobs, pedido.destination)
        painel.notebook.select(painel.export_panel)
        painel.set_status(f"A exportar {len(pedido.jobs)} máquina(s) para {pedido.destination}…")

        exportador = export.Exporter(
            sessao, pedido.destination,
            report=lambda e: self.worker.post(painel.export_panel.on_event, e),
            cancel=self._cancelar_exportacao,
            shutdown_timeout=pedido.shutdown_timeout_minutes * 60,
        )
        self.worker.submit(lambda: exportador.run(pedido.jobs), on_done=self._export_finished,  # type: ignore[arg-type]
                           on_error=self._export_failed)

    def cancel_export(self) -> None:
        if self._cancelar_exportacao is None or not self.exporting:
            return
        if messagebox.askyesno(
            "Cancelar a exportação",
            "Cancelar agora? A máquina em curso fica sem cópia, o que estava a meio é apagado e, se tinha "
            "sido encerrada para a cópia e era para voltar a ligar, volta a ser ligada.",
            parent=self.root,
        ):
            self._cancelar_exportacao.set()
            painel = self._dashboard()
            if painel is not None:
                painel.set_status("A cancelar — a terminar o passo em curso…", "aviso")

    def _export_finished(self, lote: export.BatchResult) -> None:
        self.exporting = False
        painel = self._dashboard()
        if painel is not None:
            painel.export_panel.finished(lote)
            painel.set_busy(False, False)
            painel.set_status(f"Exportação terminada: {lote.succeeded} de {len(lote.results)} concluída(s).")
        if self._a_fechar:
            self._close_now()
            return
        self.refresh()

    def _export_failed(self, erro: BaseException) -> None:
        self.exporting = False
        logger.error("A exportação parou: %s", erro, exc_info=erro)
        painel = self._dashboard()
        if painel is not None:
            texto = f"A exportação parou: {explain_failure(erro)}"
            painel.export_panel.failed(texto)
            painel.set_busy(False, False)
            painel.set_status(texto, "erro")
        if self._a_fechar:
            self._close_now()

    # =====================================================================
    # PT-PT: Ficheiros.
    # EN-UK: Files.
    # =====================================================================

    def save_report(self) -> None:
        """
        PT-PT: O estado actual em texto, para um email ou um ticket. Vai para a
               pasta do utilizador, nunca para a do programa.
        EN-UK: The current state as text, for an email or a ticket. It goes to
               the user's folder, never the program's.
        """
        painel = self._dashboard()
        if painel is None or self.fleet is None:
            return
        texto = cli.render_report(self.fleet, self.findings)
        pasta = Path(self.settings.output_dir) if self.settings.output_dir else config.reports_dir()
        destino = pasta / f"estado-{datetime.now():%Y%m%d-%H%M%S}.txt"
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto, encoding="utf-8")
        except OSError as erro:
            painel.set_status(f"Não foi possível gravar o relatório: {erro}", "erro")
            return
        painel.set_status(f"Relatório gravado em {destino}")
        if messagebox.askyesno("Relatório gravado", f"Gravado em:\n{destino}\n\nAbrir a pasta?", parent=self.root):
            self.open_path(pasta)

    def open_path(self, caminho: Path) -> None:
        try:
            if not caminho.exists() and not caminho.suffix:
                caminho.mkdir(parents=True, exist_ok=True)
            platform_support.open_path(caminho)
        except OSError as erro:
            messagebox.showerror("Abrir", f"Não foi possível abrir {caminho}: {erro}", parent=self.root)

    # =====================================================================
    # PT-PT: Fechar.
    # EN-UK: Closing.
    # =====================================================================

    def quit(self) -> None:
        """
        PT-PT: Fechar a meio de uma exportação pede confirmação e cancela-a
               primeiro, para a máquina encerrada voltar a ser ligada antes de
               a aplicação sair.
        EN-UK: Closing mid-export asks first and cancels it, so a shut-down
               machine is powered back on before the application exits.
        """
        if self.exporting and self._cancelar_exportacao is not None:
            if not messagebox.askyesno(
                "Exportação em curso",
                "Há uma exportação a correr. Cancelar e sair? A aplicação espera que o passo em curso "
                "termine e que a máquina encerrada volte a ser ligada.",
                parent=self.root,
            ):
                return
            self._a_fechar = True
            self._cancelar_exportacao.set()
            painel = self._dashboard()
            if painel is not None:
                painel.set_status("A cancelar a exportação antes de sair…", "aviso")
            return
        self._close_now()

    def _close_now(self) -> None:
        self._stop_refresh()
        sessao = self.session
        self.session = None
        if sessao is not None:
            sessao.close()
        self.worker.stop()
        self.root.destroy()


def run(settings: Settings) -> int:
    """
    PT-PT: Arranca a interface gráfica e devolve o código de saída.
    EN-UK: Starts the graphical interface and returns the exit code.
    """
    return FleetApp(settings).run()
