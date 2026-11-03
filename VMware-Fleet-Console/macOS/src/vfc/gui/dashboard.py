#!/usr/bin/env python3
"""
PT-PT: O painel: o estado do parque, as tabelas, as operações e a exportação.

       O primeiro separador é o dos achados, **e é o primeiro de propósito**: a
       pergunta que traz alguém aqui é "está tudo bem?", não "quantas máquinas
       há". O segundo é o das máquinas, e abre filtrado nas que estão ligadas —
       que é o que se quer ver antes de uma intervenção.

       As operações vivem num menu de "Acções" por separador, que é o mesmo
       que aparece com o botão direito. Uma acção que a guarda recusa aparece
       desactivada — não escondida — para se ver que existe e que agora não se
       pode.

EN-UK: The dashboard: the estate's state, the tables, operations and export.
       Findings come first on purpose: the question that brings somebody here
       is "is everything all right?". Machines come second, opening filtered to
       the running ones — what you want to see before an intervention.
       Operations live in a per-tab "Actions" menu, the same one the right
       mouse button shows. An action the guard refuses appears disabled — not
       hidden — so it is visible that it exists and cannot be done now.

Created by Redfox using Claude
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

from .. import __version__, branding, health
from ..actions import Action, Guard, guard_host, guard_snapshot, guard_vm
from ..export import BatchResult, ExportEvent, ExportJob, Stage
from ..models import (
    Finding,
    Fleet,
    HostInfo,
    Severity,
    SnapshotInfo,
    VMInfo,
    format_bytes,
    format_uptime,
)
from .theme import Theme
from .widgets import Column, ReadOnlyText, Row, Table

if TYPE_CHECKING:
    from .app import FleetApp

SEVERITY_TAG = {Severity.CRITICAL: "critico", Severity.WARNING: "aviso", Severity.INFO: "info"}


class Dashboard(ttk.Frame):
    """PT-PT: A janela principal depois de ligar. / EN-UK: The main window once connected."""

    def __init__(self, master: tk.Misc, theme: Theme, app: FleetApp) -> None:
        super().__init__(master)
        self.theme = theme
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build_header()
        self._build_toolbar()

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=12)
        self._build_findings_tab()
        self._build_vms_tab()
        self._build_hosts_tab()
        self._build_datastores_tab()
        self._build_snapshots_tab()
        self.export_panel = ExportPanel(self.notebook, theme, app)
        self.notebook.add(self.export_panel, text="Exportação")
        self.notebook.select(1)

        self._build_statusbar()

    # =====================================================================
    # PT-PT: Cabeçalho, barra de ferramentas e barra de estado.
    # EN-UK: Header, toolbar and status bar.
    # =====================================================================

    def _build_header(self) -> None:
        cabeca = ttk.Frame(self, style="Header.TFrame", padding=(20, 16))
        cabeca.grid(row=0, column=0, sticky="ew")
        cabeca.columnconfigure(0, weight=1)
        self.h_servidor = ttk.Label(cabeca, text="", style="Header.Title.TLabel")
        self.h_servidor.grid(row=0, column=0, sticky="w")
        self.h_produto = ttk.Label(cabeca, text="", style="Header.Muted.TLabel")
        self.h_produto.grid(row=1, column=0, sticky="w")
        self.h_estado = ttk.Label(cabeca, text="", style="Header.Ok.TLabel")
        self.h_estado.grid(row=0, column=1, sticky="e")
        self.h_contagens = ttk.Label(cabeca, text="", style="Header.Muted.TLabel")
        self.h_contagens.grid(row=1, column=1, sticky="e")
        self.h_aviso = ttk.Label(cabeca, text="", style="Header.Warn.TLabel", wraplength=900, justify="left")

    def _build_toolbar(self) -> None:
        barra = ttk.Frame(self, padding=(12, 10))
        barra.grid(row=1, column=0, sticky="ew")
        self.b_actualizar = ttk.Button(barra, text="Actualizar  (F5)", command=lambda: self.app.refresh(manual=True))
        self.b_actualizar.pack(side="left")
        self.b_relatorio = ttk.Button(barra, text="Guardar relatório", command=self.app.save_report)
        self.b_relatorio.pack(side="left", padx=(8, 0))
        self.b_exportar = ttk.Button(barra, text="Exportar máquinas…", style="Accent.TButton",
                                     command=self._export_selected)
        self.b_exportar.pack(side="left", padx=(8, 0))
        ttk.Button(barra, text="Terminar sessão", command=self.app.disconnect).pack(side="right")

    def _build_statusbar(self) -> None:
        barra = ttk.Frame(self, style="Status.TFrame", padding=(14, 6))
        barra.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        barra.columnconfigure(0, weight=1)
        self.s_mensagem = ttk.Label(barra, text="", style="Status.TLabel")
        self.s_mensagem.grid(row=0, column=0, sticky="w")
        self.s_hora = ttk.Label(barra, text="", style="Credit.TLabel")
        self.s_hora.grid(row=0, column=1, sticky="e", padx=(0, 18))
        self.s_credito = ttk.Label(barra, text=f"{branding.APP_NAME} {__version__}  ·  {branding.CREDIT}",
                                   style="Credit.TLabel")
        self.s_credito.grid(row=0, column=2, sticky="e")
        # PT-PT: O rodapé é verificado contra o selo depois de criado.
        # EN-UK: The footer is checked against the seal once created.
        branding.verify_displayed(str(self.s_credito.cget("text")))

    def set_status(self, texto: str, tipo: str = "") -> None:
        """
        PT-PT: A mensagem da barra de estado. O tipo vai escrito à frente —
               "Erro:", "Atenção:" — e não só em cor.
        EN-UK: The status bar message. The kind is written in front, not only
               coloured.
        """
        prefixo = {"erro": "Erro: ", "aviso": "Atenção: "}.get(tipo, "")
        self.s_mensagem.configure(text=prefixo + texto)

    def set_busy(self, ocupado: bool, exportando: bool) -> None:
        """
        PT-PT: Durante uma exportação não se actualiza nem se opera: a thread do
               vSphere está ocupada com ela, e um pedido em fila só ia esperar.
        EN-UK: During an export nothing refreshes or operates: the vSphere thread
               is busy with it, and a queued request would only wait.
        """
        for botao in (self.b_actualizar, self.b_exportar):
            botao.state(["disabled"] if exportando else ["!disabled"])
        self.b_actualizar.configure(text="A actualizar…" if ocupado and not exportando else "Actualizar  (F5)")

    # =====================================================================
    # PT-PT: Actualização do conteúdo.
    # EN-UK: Content refresh.
    # =====================================================================

    def update_fleet(self, parque: Fleet, achados: list[Finding]) -> None:
        totais = health.fleet_totals(parque)
        contagem = health.summarise(achados)
        tipo = "vCenter" if parque.is_vcenter else "Anfitrião ESXi"
        self.h_servidor.configure(text=parque.endpoint or "—")
        self.h_produto.configure(
            text=f"{tipo}  ·  {parque.product_name or 'produto desconhecido'}  ·  {self.app.certificate_note}"
        )
        pior = health.worst(achados)
        texto, estilo = {
            Severity.CRITICAL: ("HÁ PROBLEMAS CRÍTICOS", "Header.Crit.TLabel"),
            Severity.WARNING: ("HÁ AVISOS", "Header.Warn.TLabel"),
        }.get(pior, ("SEM PROBLEMAS", "Header.Ok.TLabel"))
        if pior is Severity.INFO and not contagem[Severity.INFO]:
            texto = "SEM PROBLEMAS"
        self.h_estado.configure(
            text=f"{texto}  —  {contagem[Severity.CRITICAL]} críticos, {contagem[Severity.WARNING]} avisos",
            style=estilo,
        )
        self.h_contagens.configure(
            text=(
                f"{totais['anfitrioes_ligados']}/{totais['anfitrioes']} anfitriões  ·  "
                f"{totais['maquinas_ligadas']}/{totais['maquinas']} máquinas ligadas  ·  "
                f"{totais['datastores']} datastores  ·  {totais['snapshots']} snapshots"
            )
        )
        if parque.read_only_reason:
            self.h_aviso.configure(text=parque.read_only_reason)
            self.h_aviso.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        else:
            self.h_aviso.grid_remove()
        self.s_hora.configure(text=f"Actualizado às {parque.collected_at.astimezone():%H:%M:%S}")

        self._achados = achados
        self._fill_findings()
        self._fill_vms()
        self._fill_hosts()
        self._fill_datastores()
        self._fill_snapshots()

    # =====================================================================
    # PT-PT: Estado (achados).
    # EN-UK: Status (findings).
    # =====================================================================

    def _build_findings_tab(self) -> None:
        aba = ttk.Frame(self.notebook, padding=12)
        aba.columnconfigure(0, weight=1)
        aba.rowconfigure(0, weight=3)
        aba.rowconfigure(1, weight=1)
        self.t_achados = Table(
            aba, self.theme,
            [Column("gravidade", "Gravidade", 110), Column("onde", "Onde", 220), Column("oque", "O que se passa", 620, stretch=True)],
            on_select=self._finding_selected,
        )
        self.t_achados.grid(row=0, column=0, sticky="nsew")
        self.d_achado = ReadOnlyText(aba, self.theme, height=5)
        self.d_achado.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.notebook.add(aba, text="Estado")
        self._achados: list[Finding] = []

    def _fill_findings(self) -> None:
        linhas = [
            Row(str(i), (a.severity.label, a.subject, a.message.splitlines()[0] if a.message else ""),
                (-int(a.severity), a.subject, a.message), (SEVERITY_TAG[a.severity],))
            for i, a in enumerate(self._achados)
        ]
        self.t_achados.set_rows(linhas)
        if not linhas:
            self.d_achado.set([("Nada a apontar. ", "ok"), ("Nenhuma regra de saúde encontrou problemas neste inventário.", "")])
        else:
            self._finding_selected()

    def _finding_selected(self) -> None:
        escolhidos = self.t_achados.selected()
        if not escolhidos:
            self.d_achado.set([("Escolha um achado para ver o que fazer.", "muted")])
            return
        achado = self._achados[int(escolhidos[0])]
        partes = [(f"{achado.severity.label}  ·  {achado.subject}\n", SEVERITY_TAG[achado.severity]),
                  (achado.message + "\n", "")]
        if achado.remedy:
            partes += [("\nO que fazer\n", "bold"), (achado.remedy, "")]
        self.d_achado.set(partes)

    # =====================================================================
    # PT-PT: Máquinas.
    # EN-UK: Machines.
    # =====================================================================

    def _build_vms_tab(self) -> None:
        aba = ttk.Frame(self.notebook, padding=12)
        aba.columnconfigure(0, weight=1)
        aba.rowconfigure(1, weight=3)
        aba.rowconfigure(2, weight=1)

        filtros = ttk.Frame(aba)
        filtros.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(filtros, text="Procurar", style="Muted.TLabel").pack(side="left")
        self.procura = tk.StringVar()
        ttk.Entry(filtros, textvariable=self.procura, width=28).pack(side="left", padx=(8, 14))
        self.so_ligadas = tk.BooleanVar(value=True)
        ttk.Checkbutton(filtros, text="Só as ligadas", variable=self.so_ligadas, command=self._fill_vms).pack(side="left")
        self.l_contagem = ttk.Label(filtros, text="", style="Muted.TLabel")
        self.l_contagem.pack(side="left", padx=(14, 0))
        self.b_acoes_vm = ttk.Button(filtros, text="Acções  ▾", command=lambda: self._popup(self.b_acoes_vm, self._vm_menu))
        self.b_acoes_vm.pack(side="right")
        self.procura.trace_add("write", lambda *_a: self._fill_vms())

        self.t_vms = Table(
            aba, self.theme,
            [
                Column("nome", "Nome", 180, stretch=True),
                Column("estado", "Estado", 90),
                Column("sistema", "Sistema", 180),
                Column("ip", "IP", 115),
                Column("cpu", "vCPU", 64, "e"),
                Column("mem", "Memória", 95, "e"),
                Column("disco", "Disco usado", 115, "e"),
                Column("tools", "VMware Tools", 120),
                Column("anfitriao", "Anfitrião", 150),
                Column("snaps", "Snapshots", 95, "e"),
            ],
            on_select=self._vm_selected, selectmode="extended",
        )
        self.t_vms.grid(row=1, column=0, sticky="nsew")
        self.d_vm = ReadOnlyText(aba, self.theme, height=6)
        self.d_vm.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        ttk.Label(aba, text="Ctrl ou Shift para escolher várias máquinas para exportar. Botão direito para as acções.",
                  style="Small.TLabel").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._vm_menu = self._menu()
        self.t_vms.tree.bind("<Button-3>", lambda e: self._context(e, self.t_vms, self._vm_menu, self._fill_vm_menu))
        self.t_vms.tree.bind("<Control-e>", lambda _e: self._export_selected())
        self.notebook.add(aba, text="Máquinas")

    def _visible_vms(self) -> list[VMInfo]:
        parque = self.app.fleet
        if parque is None:
            return []
        termo = self.procura.get().strip().casefold()
        saida = []
        for vm in parque.running_vms if self.so_ligadas.get() else parque.vms:
            if termo and not any(termo in campo.casefold() for campo in (vm.name, vm.ip_address, vm.hostname, vm.guest_os, vm.host_name)):
                continue
            saida.append(vm)
        return saida

    def _fill_vms(self) -> None:
        parque = self.app.fleet
        if parque is None:
            return
        visiveis = self._visible_vms()
        linhas = []
        for vm in visiveis:
            estado = "Modelo" if vm.is_template else vm.power_state.label
            etiquetas = () if vm.running else ("muted",)
            linhas.append(Row(
                vm.moid,
                (vm.name, estado, vm.guest_os, vm.ip_address, str(vm.cpu_count),
                 format_bytes(vm.memory_bytes), format_bytes(vm.committed_bytes), vm.tools_status.label,
                 vm.host_name, str(vm.snapshot_count) if vm.snapshot_count else ""),
                (vm.name, estado, vm.guest_os, _ip_key(vm.ip_address), vm.cpu_count, vm.memory_mb,
                 vm.committed_bytes or 0, vm.tools_status.label, vm.host_name, vm.snapshot_count),
                etiquetas,
            ))
        self.t_vms.set_rows(linhas)
        total = sum(1 for vm in parque.vms if not vm.is_template)
        self.l_contagem.configure(text=f"{len(visiveis)} visíveis de {len(parque.vms)} ({total} máquinas, "
                                       f"{len(parque.vms) - total} modelos)")
        self._vm_selected()

    def selected_vms(self) -> list[VMInfo]:
        parque = self.app.fleet
        if parque is None:
            return []
        return [vm for moid in self.t_vms.selected() if (vm := parque.vm_by_moid(moid)) is not None]

    def _vm_selected(self) -> None:
        escolhidas = self.selected_vms()
        if not escolhidas:
            self.d_vm.set([("Escolha uma máquina para ver o detalhe.", "muted")])
            return
        if len(escolhidas) > 1:
            total = sum(int(vm.committed_bytes or 0) for vm in escolhidas)
            self.d_vm.set([(f"{len(escolhidas)} máquinas escolhidas", "bold"),
                           (f"  ·  {format_bytes(total)} de disco usado no total. «Exportar máquinas…» exporta-as todas.", "")])
            return
        vm = escolhidas[0]
        linhas: list[tuple[str, str]] = [
            (f"{vm.name}\n", "bold"),
            ("Estado: ", "muted"), (f"{vm.power_state.label}", ""),
            ("    Tools: ", "muted"), (vm.tools_status.label + ("" if vm.tools_version_ok else " (desactualizadas)"), ""),
            ("    Uptime: ", "muted"), (format_uptime(vm.uptime_seconds), "") ,
            ("\nSistema: ", "muted"), (vm.guest_os or "—", ""),
            ("    Nome: ", "muted"), (vm.hostname or "—", ""),
            ("    IP: ", "muted"), (vm.ip_address or "—", ""),
            ("\nCPU / memória: ", "muted"), (f"{vm.cpu_count} vCPU, {format_bytes(vm.memory_bytes)}", ""),
            ("    Disco: ", "muted"),
            (f"{format_bytes(vm.committed_bytes)} usados de {format_bytes(vm.provisioned_bytes)} aprovisionados", ""),
            ("\nAnfitrião: ", "muted"), (vm.host_name or "—", ""),
            ("    Datastores: ", "muted"), (", ".join(vm.datastore_names) or "—", ""),
            ("    Snapshots: ", "muted"), (str(vm.snapshot_count), ""),
        ]
        if vm.annotation:
            linhas += [("\nNotas: ", "muted"), (vm.annotation, "")]
        self.d_vm.set(linhas)

    def _fill_vm_menu(self, menu: tk.Menu) -> None:
        escolhidas = self.selected_vms()
        uma = escolhidas[0] if len(escolhidas) == 1 else None
        parque = self.app.fleet
        ops: list[tuple[str, Action, Callable[..., object]]] = [
            ("Ligar", Action.VM_POWER_ON, lambda o, vm: o.vm_power_on(vm, parque)),
            ("Encerrar o sistema convidado", Action.VM_GUEST_SHUTDOWN, lambda o, vm: o.vm_guest_shutdown(vm, parque)),
            ("Reiniciar o sistema convidado", Action.VM_GUEST_RESTART, lambda o, vm: o.vm_guest_restart(vm, parque)),
            ("Suspender", Action.VM_SUSPEND, lambda o, vm: o.vm_suspend(vm, parque)),
        ]
        for rotulo, accao, chamada in ops:
            guarda = guard_vm(accao, uma, parque) if uma else None
            self._menu_item(menu, rotulo, guarda, uma.name if uma else "", chamada, uma)
        menu.add_separator()
        for rotulo, accao, chamada in (
            ("Desligar à força…", Action.VM_POWER_OFF, lambda o, vm, t: o.vm_power_off(vm, t, parque)),
            ("Reset…", Action.VM_RESET, lambda o, vm, t: o.vm_reset(vm, t, parque)),
        ):
            guarda = guard_vm(accao, uma, parque) if uma else None
            self._menu_item(menu, rotulo, guarda, uma.name if uma else "", chamada, uma)
        menu.add_separator()
        criar = guard_snapshot(Action.SNAPSHOT_CREATE, uma) if uma else None
        menu.add_command(label="Criar snapshot…", command=lambda: self.app.create_snapshot(uma),  # type: ignore[arg-type]
                         state="normal" if criar and criar.allowed else "disabled")
        menu.add_separator()
        menu.add_command(label=f"Exportar para OVF… ({len(escolhidas)})" if len(escolhidas) > 1 else "Exportar para OVF…",
                         command=self._export_selected, state="normal" if escolhidas and not self.app.exporting else "disabled")

    def _export_selected(self) -> None:
        escolhidas = self.selected_vms()
        if not escolhidas:
            self.notebook.select(1)
            self.set_status("Escolha uma ou mais máquinas no separador Máquinas e carregue em «Exportar máquinas…».", "aviso")
            return
        self.app.open_export_dialog(escolhidas)

    # =====================================================================
    # PT-PT: Anfitriões.
    # EN-UK: Hosts.
    # =====================================================================

    def _build_hosts_tab(self) -> None:
        aba = ttk.Frame(self.notebook, padding=12)
        aba.columnconfigure(0, weight=1)
        aba.rowconfigure(1, weight=1)
        topo = ttk.Frame(aba)
        topo.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.b_acoes_host = ttk.Button(topo, text="Acções  ▾", command=lambda: self._popup(self.b_acoes_host, self._host_menu))
        self.b_acoes_host.pack(side="right")
        self.t_hosts = Table(
            aba, self.theme,
            [
                Column("nome", "Nome", 180),
                Column("estado", "Estado", 150),
                Column("cpu", "CPU", 64, "e"),
                Column("mem", "Memória", 90, "e"),
                Column("vms", "Máquinas", 95, "e"),
                Column("versao", "Versão", 240, stretch=True),
                Column("uptime", "Uptime", 85, "e"),
                Column("modelo", "Modelo", 220),
                Column("alertas", "Alertas de hardware", 180),
            ],
        )
        self.t_hosts.grid(row=1, column=0, sticky="nsew")
        self._host_menu = self._menu()
        self.t_hosts.tree.bind("<Button-3>", lambda e: self._context(e, self.t_hosts, self._host_menu, self._fill_host_menu))
        self.notebook.add(aba, text="Anfitriões")

    def _fill_hosts(self) -> None:
        parque = self.app.fleet
        if parque is None:
            return
        linhas = []
        for h in parque.hosts:
            estado = h.connection_state.label + (" · manutenção" if h.in_maintenance_mode else "")
            etiqueta = "critico" if not h.reachable else ("aviso" if h.in_maintenance_mode or h.hardware_alerts else "")
            linhas.append(Row(
                h.moid,
                (h.name, estado, _pct(h.cpu_used_percent), _pct(h.memory_used_percent),
                 f"{h.running_vm_count}/{h.vm_count}", h.version, format_uptime(h.uptime_seconds),
                 f"{h.vendor} {h.model}".strip(), ", ".join(h.hardware_alerts)),
                (h.name, estado, h.cpu_used_percent, h.memory_used_percent, h.running_vm_count, h.version,
                 h.uptime_seconds, h.model, len(h.hardware_alerts)),
                (etiqueta,) if etiqueta else (),
            ))
        self.t_hosts.set_rows(linhas)

    def _selected_host(self) -> HostInfo | None:
        parque = self.app.fleet
        escolhidos = self.t_hosts.selected()
        return parque.host_by_moid(escolhidos[0]) if parque and escolhidos else None

    def _fill_host_menu(self, menu: tk.Menu) -> None:
        h = self._selected_host()
        parque = self.app.fleet
        for rotulo, accao, chamada in (
            ("Sair do modo de manutenção", Action.HOST_MAINTENANCE_EXIT, lambda o, x: o.host_exit_maintenance(x, parque)),
            ("Entrar em modo de manutenção…", Action.HOST_MAINTENANCE_ENTER, lambda o, x, t: o.host_enter_maintenance(x, t, parque)),
            ("Reiniciar o anfitrião…", Action.HOST_REBOOT, lambda o, x, t: o.host_reboot(x, t, parque)),
            ("Desligar o anfitrião…", Action.HOST_SHUTDOWN, lambda o, x, t: o.host_shutdown(x, t, parque)),
        ):
            guarda = guard_host(accao, h, parque) if h else None
            self._menu_item(menu, rotulo, guarda, h.name if h else "", chamada, h)

    # =====================================================================
    # PT-PT: Datastores.
    # EN-UK: Datastores.
    # =====================================================================

    def _build_datastores_tab(self) -> None:
        aba = ttk.Frame(self.notebook, padding=12)
        aba.columnconfigure(0, weight=1)
        aba.rowconfigure(0, weight=1)
        self.t_ds = Table(
            aba, self.theme,
            [
                Column("nome", "Nome", 240, stretch=True),
                Column("tipo", "Tipo", 80),
                Column("cap", "Capacidade", 110, "e"),
                Column("livre", "Livre", 110, "e"),
                Column("pct", "% livre", 80, "e"),
                Column("estado", "Estado", 140),
                Column("hosts", "Anfitriões", 260),
            ],
        )
        self.t_ds.grid(row=0, column=0, sticky="nsew")
        self.notebook.add(aba, text="Datastores")

    def _fill_datastores(self) -> None:
        parque = self.app.fleet
        if parque is None:
            return
        limiares = self.app.settings
        linhas = []
        for d in parque.datastores:
            livre = d.free_percent
            if not d.accessible:
                etiqueta, estado = "critico", "INACESSÍVEL"
            elif livre is not None and livre < limiares.datastore_free_critical_pct:
                etiqueta, estado = "critico", "Quase cheio"
            elif livre is not None and livre < limiares.datastore_free_warning_pct:
                etiqueta, estado = "aviso", "A encher"
            else:
                etiqueta, estado = "", "Normal"
            if d.maintenance_mode not in ("normal", ""):
                estado += " · manutenção"
            linhas.append(Row(
                d.moid,
                (d.name, d.kind, format_bytes(d.capacity_bytes), format_bytes(d.free_bytes), _pct(livre), estado,
                 ", ".join(d.host_names)),
                (d.name, d.kind, d.capacity_bytes, d.free_bytes, livre, estado, len(d.host_names)),
                (etiqueta,) if etiqueta else (),
            ))
        self.t_ds.set_rows(linhas)

    # =====================================================================
    # PT-PT: Snapshots.
    # EN-UK: Snapshots.
    # =====================================================================

    def _build_snapshots_tab(self) -> None:
        aba = ttk.Frame(self.notebook, padding=12)
        aba.columnconfigure(0, weight=1)
        aba.rowconfigure(1, weight=1)
        topo = ttk.Frame(aba)
        topo.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.b_acoes_snap = ttk.Button(topo, text="Acções  ▾", command=lambda: self._popup(self.b_acoes_snap, self._snap_menu))
        self.b_acoes_snap.pack(side="right")
        self.t_snaps = Table(
            aba, self.theme,
            [
                Column("vm", "Máquina", 220),
                Column("nome", "Snapshot", 260, stretch=True),
                Column("criado", "Criado em", 140),
                Column("idade", "Idade", 80, "e"),
                Column("tam", "Tamanho", 100, "e"),
                Column("actual", "Actual", 70, "center"),
            ],
        )
        self.t_snaps.grid(row=1, column=0, sticky="nsew")
        self._snap_menu = self._menu()
        self.t_snaps.tree.bind("<Button-3>", lambda e: self._context(e, self.t_snaps, self._snap_menu, self._fill_snap_menu))
        self.notebook.add(aba, text="Snapshots")

    def _fill_snapshots(self) -> None:
        parque = self.app.fleet
        if parque is None:
            return
        cfg = self.app.settings
        linhas = []
        for vm in parque.vms:
            for s in vm.snapshots:
                idade = s.age_days()
                etiqueta = ""
                if idade is not None and idade >= cfg.snapshot_age_critical_days:
                    etiqueta = "critico"
                elif idade is not None and idade >= cfg.snapshot_age_warning_days:
                    etiqueta = "aviso"
                criado = s.created.astimezone().strftime("%Y-%m-%d %H:%M") if s.created else "—"
                linhas.append(Row(
                    f"{vm.moid}:{s.identifier}",
                    (vm.name, "    " * (s.depth - 1) + s.name, criado,
                     f"{idade} d" if idade is not None else "—", format_bytes(s.size_bytes), "sim" if s.is_current else ""),
                    (vm.name, s.name, s.created.timestamp() if s.created else None, idade, s.size_bytes or 0, s.is_current),
                    (etiqueta,) if etiqueta else (),
                ))
        self.t_snaps.set_rows(linhas)

    def _selected_snapshot(self) -> tuple[VMInfo, SnapshotInfo] | None:
        parque = self.app.fleet
        escolhidos = self.t_snaps.selected()
        if not parque or not escolhidos:
            return None
        moid, _, ident = escolhidos[0].rpartition(":")
        vm = parque.vm_by_moid(moid)
        if vm is None:
            return None
        snap = next((s for s in vm.snapshots if str(s.identifier) == ident), None)
        return (vm, snap) if snap else None

    def _fill_snap_menu(self, menu: tk.Menu) -> None:
        par = self._selected_snapshot()
        vm, snap = par if par else (None, None)
        for rotulo, accao, chamada in (
            ("Reverter para este snapshot…", Action.SNAPSHOT_REVERT, lambda o, v, t: o.snapshot_revert(v, snap, t)),
            ("Apagar este snapshot…", Action.SNAPSHOT_DELETE, lambda o, v, t: o.snapshot_delete(v, snap, t)),
        ):
            guarda = guard_snapshot(accao, vm, snap) if vm else None
            self._menu_item(menu, rotulo, guarda, vm.name if vm else "", chamada, vm)

    # =====================================================================
    # PT-PT: Menus.
    # EN-UK: Menus.
    # =====================================================================

    def _menu(self) -> tk.Menu:
        return self.theme.register(tk.Menu(self, tearoff=False), "menu")  # type: ignore[return-value]

    def _menu_item(
        self,
        menu: tk.Menu,
        rotulo: str,
        guarda: Guard | None,
        assunto: str,
        chamada: Callable[..., object],
        alvo: object,
    ) -> None:
        """
        PT-PT: Uma entrada de menu ligada a uma guarda. Recusada aparece
               desactivada; com confirmação, passa pelo diálogo de escrever o
               nome antes de chegar à operação.
        EN-UK: A menu entry bound to a guard. Refused, it shows disabled; with a
               confirmation, it goes through the typed-name dialog first.
        """
        if guarda is None or not guarda.allowed:
            menu.add_command(label=rotulo, state="disabled")
            return
        if guarda.needs_confirmation:
            menu.add_command(label=rotulo, command=lambda: self.app.confirm_and_run(guarda, assunto, chamada, alvo))
        else:
            menu.add_command(label=rotulo, command=lambda: self.app.run_operation(lambda o: chamada(o, alvo)))

    def _context(self, evento: tk.Event, tabela: Table, menu: tk.Menu, preencher: Callable[[tk.Menu], None]) -> None:
        linha = tabela.tree.identify_row(evento.y)
        if linha and linha not in tabela.selected():
            tabela.tree.selection_set(linha)
        menu.delete(0, "end")
        preencher(menu)
        menu.tk_popup(evento.x_root, evento.y_root)

    def _popup(self, botao: ttk.Button, menu: tk.Menu) -> None:
        menu.delete(0, "end")
        preencher = {id(self._vm_menu): self._fill_vm_menu, id(self._host_menu): self._fill_host_menu,
                     id(self._snap_menu): self._fill_snap_menu}[id(menu)]
        preencher(menu)
        menu.tk_popup(botao.winfo_rootx(), botao.winfo_rooty() + botao.winfo_height())


# =========================================================================
# PT-PT: O separador da exportação.
# EN-UK: The export tab.
# =========================================================================


class ExportPanel(ttk.Frame):
    """
    PT-PT: O progresso de uma exportação: máquina a máquina, com o ritmo e o
           tempo que falta, o registo do que aconteceu, e o botão de cancelar.

           O tempo que falta é uma estimativa a partir do disco usado, que é um
           tecto: os discos chegam comprimidos, e o fim costuma vir antes do
           previsto.

    EN-UK: An export's progress machine by machine, with rate and time left,
           the log, and the cancel button. Time left is estimated from disk used,
           a ceiling: disks arrive compressed and the end usually comes early.
    """

    def __init__(self, master: tk.Misc, theme: Theme, app: FleetApp) -> None:
        super().__init__(master, padding=12)
        self.theme = theme
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=2)
        self.rowconfigure(4, weight=1)
        self._lote: BatchResult | None = None
        self._destino: Path | None = None
        self._inicio: dict[int, tuple[float, int]] = {}
        self._n = 0

        topo = ttk.Frame(self)
        topo.grid(row=0, column=0, sticky="ew")
        topo.columnconfigure(0, weight=1)
        self.titulo = ttk.Label(topo, text="Sem exportações nesta sessão", style="Subtitle.TLabel")
        self.titulo.grid(row=0, column=0, sticky="w")
        self.b_cancelar = ttk.Button(topo, text="Cancelar exportação", style="Danger.TButton", command=self.app.cancel_export)
        self.b_cancelar.grid(row=0, column=1, sticky="e")
        self.b_cancelar.state(["disabled"])
        self.b_pasta = ttk.Button(topo, text="Abrir destino", command=lambda: self._abrir(self._destino))
        self.b_pasta.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.b_pasta.state(["disabled"])
        self.b_relatorio = ttk.Button(topo, text="Abrir relatório", command=self._abrir_relatorio)
        self.b_relatorio.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.b_relatorio.state(["disabled"])

        self.resumo = ttk.Label(
            self,
            text="Escolha máquinas no separador Máquinas (Ctrl ou Shift para várias) e carregue em «Exportar máquinas…».",
            style="Muted.TLabel",
        )
        self.resumo.grid(row=1, column=0, sticky="w", pady=(6, 8))
        self.barra = ttk.Progressbar(self, mode="determinate")
        self.barra.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        self.tabela = Table(
            self, theme,
            [Column("vm", "Máquina", 220), Column("etapa", "Etapa", 170), Column("bytes", "Transferido", 120, "e"),
             Column("res", "Resultado", 520, stretch=True)],
            height=6,
        )
        self.tabela.grid(row=3, column=0, sticky="nsew")
        self.registo = ReadOnlyText(self, theme, height=6)
        self.registo.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        self._linhas: dict[int, list[str]] = {}

    def started(self, trabalhos: list[ExportJob], destino: Path) -> None:
        self._destino = destino
        self._lote = None
        self._n = len(trabalhos)
        self._inicio.clear()
        self._linhas = {
            i: [t.check.vm.name, Stage.QUEUED.label, "", t.check.warning or ""] for i, t in enumerate(trabalhos)
        }
        self.titulo.configure(text=f"A exportar {self._n} máquina(s)")
        self.resumo.configure(text=f"Destino: {destino}", style="Muted.TLabel")
        self.barra.configure(maximum=max(self._n, 1) * 100, value=0)
        self.b_cancelar.state(["!disabled"])
        self.b_pasta.state(["!disabled"])
        self.b_relatorio.state(["disabled"])
        self.registo.set([(f"{datetime.now():%H:%M:%S}  Início — {self._n} máquina(s) para {destino}\n", "muted")])
        self._redraw()

    def on_event(self, e: ExportEvent) -> None:
        linha = self._linhas.get(e.index)
        if linha is None:
            return
        anterior = linha[1]
        linha[1] = e.stage.label
        if e.bytes_done:
            linha[2] = format_bytes(e.bytes_done)
        if e.stage is Stage.DOWNLOADING:
            linha[3] = f"A copiar {e.message}" if e.message else ""
        elif e.stage.finished or e.message:
            linha[3] = e.message

        if e.stage is Stage.DOWNLOADING:
            inicio = self._inicio.setdefault(e.index, (time.monotonic(), e.bytes_done))
            decorrido = time.monotonic() - inicio[0]
            ritmo = (e.bytes_done - inicio[1]) / decorrido if decorrido > 1 else 0
            falta = ""
            if ritmo > 0 and e.bytes_expected > e.bytes_done:
                segundos = int((e.bytes_expected - e.bytes_done) / ritmo)
                falta = f"  ·  faltam até ~{_duracao(segundos)}"
            # PT-PT: A estimativa é um tecto; se já foi ultrapassada, não se
            #        mostra um "de" que mentiria.
            # EN-UK: The estimate is a ceiling; once exceeded, a "of" that
            #        would lie is not shown.
            tecto = f" de ~{format_bytes(e.bytes_expected)}" if e.bytes_expected > e.bytes_done else ""
            self.resumo.configure(
                text=f"{e.index + 1} de {self._n}  ·  {e.vm_name}  ·  {format_bytes(e.bytes_done)}{tecto}"
                f"  ·  {format_bytes(ritmo)}/s{falta}",
                style="Muted.TLabel",
            )
            fracao = min(e.bytes_done / e.bytes_expected, 0.99) if e.bytes_expected > e.bytes_done else 0.5
            self.barra.configure(value=e.index * 100 + int(fracao * 100))
        elif e.stage.finished:
            self.barra.configure(value=(e.index + 1) * 100)
        else:
            self.resumo.configure(text=f"{e.index + 1} de {self._n}  ·  {e.vm_name}  ·  {e.stage.label}", style="Muted.TLabel")

        if anterior != linha[1] or e.stage.finished:
            etiqueta = {Stage.DONE: "ok", Stage.FAILED: "critico", Stage.CANCELLED: "aviso"}.get(e.stage, "")
            self.registo.append(f"{datetime.now():%H:%M:%S}  {e.vm_name}: {e.stage.label}", etiqueta)
            if e.message and e.stage is not Stage.DOWNLOADING:
                self.registo.append(f" — {e.message}", etiqueta)
            self.registo.append("\n")
        self._redraw()

    def finished(self, lote: BatchResult) -> None:
        self._lote = lote
        self.b_cancelar.state(["disabled"])
        self.b_relatorio.state(["!disabled"] if lote.report_path else ["disabled"])
        falhas = sum(1 for r in lote.results if r.stage is Stage.FAILED)
        self.titulo.configure(text=f"Exportação terminada — {lote.succeeded} de {len(lote.results)} concluída(s)")
        estilo = "Crit.TLabel" if falhas else ("Ok.TLabel" if lote.succeeded == len(lote.results) else "Warn.TLabel")
        self.resumo.configure(text=f"Relatório: {lote.report_path}", style=estilo)
        self.barra.configure(value=self.barra.cget("maximum"))
        self.registo.append(f"{datetime.now():%H:%M:%S}  Fim — {lote.succeeded} concluída(s), {falhas} falhada(s)\n",
                            "critico" if falhas else "ok")
        for r in lote.results:
            if r.was_shut_down and not r.powered_back_on:
                self.registo.append(f"           {r.vm_name} ficou desligada.\n", "aviso")

    def failed(self, mensagem: str) -> None:
        self.b_cancelar.state(["disabled"])
        self.titulo.configure(text="A exportação não chegou ao fim")
        self.resumo.configure(text=mensagem, style="Crit.TLabel")
        self.registo.append(f"{datetime.now():%H:%M:%S}  {mensagem}\n", "critico")

    def _redraw(self) -> None:
        etiquetas = {Stage.DONE.label: "ok", Stage.FAILED.label: "critico", Stage.CANCELLED.label: "aviso"}
        self.tabela.set_rows([
            Row(str(i), tuple(v), (i, v[1], v[2], v[3]), (etiquetas[v[1]],) if v[1] in etiquetas else ())
            for i, v in self._linhas.items()
        ])

    def _abrir(self, caminho: Path | None) -> None:
        if caminho is not None:
            self.app.open_path(caminho)

    def _abrir_relatorio(self) -> None:
        if self._lote and self._lote.report_path:
            self.app.open_path(Path(self._lote.report_path))


# =========================================================================
# PT-PT: Formatação.
# EN-UK: Formatting.
# =========================================================================


def _pct(valor: float | None) -> str:
    return "--" if valor is None else f"{valor:.0f}%"


def _ip_key(ip: str) -> tuple[int, tuple[int, ...] | str] | str:
    """
    PT-PT: Ordena 10.0.0.9 antes de 10.0.0.10; um IPv6 ou um nome vão depois
           dos IPv4, e um vazio fica vazio (vai para o fim).
    EN-UK: Sorts 10.0.0.9 before 10.0.0.10; IPv6 or names after IPv4; blank
           stays blank (sinks to the end).
    """
    if not ip:
        return ""
    try:
        return (0, tuple(int(p) for p in ip.split(".")))
    except ValueError:
        return (1, ip.casefold())


def _duracao(segundos: int) -> str:
    if segundos < 90:
        return f"{segundos} s"
    if segundos < 5400:
        return f"{segundos // 60} min"
    return f"{segundos // 3600} h {segundos % 3600 // 60:02d} min"

