#!/usr/bin/env python3
"""
PT-PT: A assinatura e o selo que a protege.

       Estes testes são a outra metade da protecção: se alguém mudar o crédito
       em `branding.py` sem mudar o selo, a aplicação não arranca — e a suite
       falha antes disso, no primeiro `pytest`.

EN-UK: The signature and the seal protecting it. These tests are the other half
       of the protection: change the credit without the seal and the
       application will not start — and the suite fails before that.

Created by Redfox using Claude
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vfc import __main__ as arranque
from vfc import branding, cli


class TestSelo:
    def test_a_assinatura_esta_intacta(self) -> None:
        branding.verify()
        assert branding.CREDIT == "Created by Redfox using Claude"

    def test_mudar_o_credito_impede_o_arranque(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(branding, "CREDIT", "Created by outra pessoa")
        with pytest.raises(branding.BrandingTamperedError):
            branding.verify()
        assert arranque.main(["--versao"]) == cli.EXIT_TAMPERED

    def test_apagar_o_credito_impede_o_arranque(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(branding, "CREDIT", "")
        with pytest.raises(branding.BrandingTamperedError):
            branding.verify()

    def test_rodape_sem_credito_e_recusado(self) -> None:
        with pytest.raises(branding.BrandingTamperedError):
            branding.verify_displayed("VMware Fleet Console 2.0.0")
        branding.verify_displayed(f"VMware Fleet Console 2.0.0 · {branding.CREDIT}")


class TestOndeAparece:
    def test_titulo_das_janelas(self) -> None:
        assert branding.CREDIT in branding.window_title("2.0.0", "esx01")

    def test_relatorio_de_texto(self, parque: object) -> None:
        assert branding.CREDIT in cli.render_report(parque, [])  # type: ignore[arg-type]

    def test_todos_os_modulos_levam_o_credito(self) -> None:
        # PT-PT: Cada ficheiro de código diz quem o fez, como o resto do projecto.
        # EN-UK: Every source file says who made it, like the rest of the project.
        raiz = Path(__file__).resolve().parent.parent / "src" / "vfc"
        sem = [f.name for f in raiz.rglob("*.py") if branding.CREDIT not in f.read_text(encoding="utf-8")]
        assert not sem, f"Ficheiros sem o crédito: {sem}"
