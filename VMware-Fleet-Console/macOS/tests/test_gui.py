#!/usr/bin/env python3
"""
PT-PT: A janela, montada a sério sobre o parque inventado do `conftest.py`.

       Não se testa o aspecto — isso vê-se. Testa-se o que partiria sem se ver:
       que cada separador se preenche com um parque que tem de tudo (um
       anfitrião caído, um snapshot de oito meses, uma máquina sem Tools), que
       as entradas de menu ficam activas ou desactivadas conforme a guarda, e
       que os diálogos de confirmação não deixam avançar sem o nome escrito.

       Precisa de um ecrã. Num servidor de CI sem ambiente gráfico os testes
       saltam-se em vez de falharem.

EN-UK: The window, built for real on the invented estate. Not the looks —
       those are seen. What would break unseen: every tab fills from an estate
       with everything in it, menu entries enable or disable per the guard, and
       confirmation dialogs do not proceed without the typed name. Needs a
       display; on headless CI the tests skip rather than fail.

Created by Redfox using Claude
"""

from __future__ import annotations

import tkinter as tk

import pytest

from vfc import health
from vfc.actions import Action, guard_vm
from vfc.config import Settings
from vfc.gui.dashboard import Dashboard
from vfc.gui.dialogs import ConfirmDialog, ExportDialog
from vfc.gui.theme import Theme
from vfc.models import Fleet


@pytest.fixture
def raiz() -> tk.Tk:
    try:
        janela = tk.Tk()
    except tk.TclError as erro:
        pytest.skip(f"sem ecrã: {erro}")
    janela.withdraw()
    yield janela
    janela.destroy()


class _App:
    """PT-PT: O mínimo que o painel pede à aplicação. / EN-UK: What the dashboard asks of the app."""

    def __init__(self, parque: Fleet) -> None:
        self.fleet = parque
        self.settings = Settings()
        self.exporting = False
        self.certificate_note = "certificado fixado AA:BB:CC ... 77:88:99"
        self.pedidos: list[str] = []

    def __getattr__(self, nome: str) -> object:
        return lambda *a, **k: self.pedidos.append(nome)


def _entradas(menu: tk.Menu) -> dict[str, str]:
    saida = {}
    for i in range((menu.index("end") or 0) + 1):
        if menu.type(i) == "command":
            saida[str(menu.entrycget(i, "label"))] = str(menu.entrycget(i, "state"))
    return saida


class TestPainel:
    def test_todos_os_separadores_se_preenchem(self, raiz: tk.Tk, parque: Fleet) -> None:
        app = _App(parque)
        painel = Dashboard(raiz, Theme(raiz, "escuro"), app)  # type: ignore[arg-type]
        achados = health.evaluate(parque)
        painel.update_fleet(parque, achados)
        assert len(painel.t_achados.tree.get_children()) == len(achados)
        assert len(painel.t_hosts.tree.get_children()) == len(parque.hosts)
        assert len(painel.t_ds.tree.get_children()) == len(parque.datastores)
        assert len(painel.t_snaps.tree.get_children()) == sum(v.snapshot_count for v in parque.vms)
        # PT-PT: Abre filtrado nas ligadas — o que se quer ver antes de mexer.
        # EN-UK: Opens filtered to running machines.
        assert len(painel.t_vms.tree.get_children()) == sum(1 for v in parque.vms if v.running)
        assert "CRÍTICOS" in str(painel.h_estado.cget("text"))

    def test_o_rodape_leva_a_assinatura(self, raiz: tk.Tk, parque: Fleet) -> None:
        painel = Dashboard(raiz, Theme(raiz, "claro"), _App(parque))  # type: ignore[arg-type]
        assert "Created by Redfox using Claude" in str(painel.s_credito.cget("text"))

    def test_menu_segue_a_guarda(self, raiz: tk.Tk, parque: Fleet) -> None:
        painel = Dashboard(raiz, Theme(raiz, "escuro"), _App(parque))  # type: ignore[arg-type]
        painel.update_fleet(parque, [])
        maquina = next(v for v in parque.vms if v.name == "SRV-LEGACY")  # ligada, sem Tools
        painel.t_vms.tree.selection_set([maquina.moid])
        menu = painel._vm_menu
        menu.delete(0, "end")
        painel._fill_vm_menu(menu)
        estados = _entradas(menu)
        assert estados["Ligar"] == "disabled"
        assert estados["Encerrar o sistema convidado"] == "disabled"
        assert estados["Desligar à força…"] == "normal"
        assert estados["Exportar para OVF…"] == "normal"

    def test_a_procura_filtra(self, raiz: tk.Tk, parque: Fleet) -> None:
        painel = Dashboard(raiz, Theme(raiz, "escuro"), _App(parque))  # type: ignore[arg-type]
        painel.update_fleet(parque, [])
        painel.so_ligadas.set(False)
        painel.procura.set("legacy")
        assert painel.t_vms.tree.get_children() == ("vm-2",)

    def test_mudar_de_tema_nao_rebenta(self, raiz: tk.Tk, parque: Fleet) -> None:
        tema = Theme(raiz, "escuro")
        painel = Dashboard(raiz, tema, _App(parque))  # type: ignore[arg-type]
        painel.update_fleet(parque, health.evaluate(parque))
        tema.apply("claro")
        tema.apply("escuro")


class TestDialogos:
    def test_confirmar_so_com_o_nome(self, raiz: tk.Tk, parque: Fleet) -> None:
        maquina = next(v for v in parque.vms if v.name == "SRV-APP01")
        guarda = guard_vm(Action.VM_POWER_OFF, maquina, parque)
        dialogo = ConfirmDialog(raiz, Theme(raiz, "escuro"), guarda, maquina.name)
        assert "disabled" in dialogo.ok.state()
        dialogo.texto.set("SRV-APP0")
        assert "disabled" in dialogo.ok.state()
        dialogo.texto.set("srv-app01 ")
        assert "disabled" not in dialogo.ok.state()
        dialogo.destroy()

    def test_exportar_exige_escrever_encerrar(self, raiz: tk.Tk, parque: Fleet, tmp_path: object) -> None:
        ligada = next(v for v in parque.vms if v.name == "SRV-APP01")
        dialogo = ExportDialog(raiz, Theme(raiz, "escuro"), [ligada], parque, "vc", set(), str(tmp_path), 10)
        assert "disabled" in dialogo.ok.state()  # ligada, sem autorização para encerrar
        dialogo.encerrar.set(True)
        dialogo._recalcular()
        assert dialogo.decisoes[0].needs_shutdown
        assert "disabled" in dialogo.ok.state()
        dialogo.confirmacao.set("encerrar")
        assert "disabled" not in dialogo.ok.state()
        dialogo.on_ok()
        pedido = dialogo.result
        assert pedido is not None and len(pedido.jobs) == 1  # type: ignore[attr-defined]
        assert pedido.jobs[0].power_on_after  # type: ignore[attr-defined]

    def test_maquinas_recusadas_nao_seguem(self, raiz: tk.Tk, parque: Fleet, tmp_path: object) -> None:
        escolhidas = [v for v in parque.vms if v.name in ("SRV-TESTE", "SRV-LEGACY")]
        dialogo = ExportDialog(raiz, Theme(raiz, "escuro"), escolhidas, parque, "vc", set(), str(tmp_path), 10)
        dialogo.encerrar.set(True)
        dialogo._recalcular()
        assert "SRV-LEGACY" in str(dialogo.recusas.cget("text"))
        dialogo.on_ok()
        assert [j.check.vm.name for j in dialogo.result.jobs] == ["SRV-TESTE"]  # type: ignore[attr-defined]
