#!/usr/bin/env python3
"""
PT-PT: Testes das particularidades do Windows, na versão de Windows da
       VMware Fleet Console.

       As outras duas versões têm os seus, nas pastas ao lado, e testam coisas
       diferentes — porque as particularidades de cada sistema são diferentes.
       Aqui testa-se a detecção do `python.exe` da Microsoft Store, o Tkinter da
       janela e a página de código do modo de texto; na de Linux testa-se a
       distribuição e o ambiente gráfico; na de macOS, a arquitectura e o
       Homebrew.

       O último teste desta suite é o que mantém a promessa das três versões:
       falha se alguém puser uma ramificação por sistema operativo dentro desta.

EN-UK: Windows specifics tests, in the Windows version of VMware Fleet Console.

       The other two versions have their own and test different things, because
       each system's specifics are different.

Created by Redfox using Claude
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vfc import platform_support as ps
from vfc.config import APP_FOLDER_NAME, app_data_dir


class TestPythonDaMicrosoftStore:
    """
    PT-PT: A armadilha número um do Windows.

           Uma instalação limpa traz um `python.exe` no PATH que abre a loja.
           Quem o corre vê a Store e não percebe porquê — e conclui que o
           programa está avariado.

    EN-UK: Windows' number-one trap. A clean install carries a `python.exe` on
           the PATH that opens the Store. Whoever runs it sees the Store and
           concludes the program is broken.
    """

    def test_reconhece_o_atalho_da_loja(self) -> None:
        assert ps.is_store_python(
            r"C:\Users\rafael\AppData\Local\Microsoft\WindowsApps\python.exe"
        )
        assert ps.is_store_python(
            r"C:\Users\rafael\AppData\Local\Microsoft\WindowsApps\python3.11.exe"
        )

    def test_nao_confunde_um_python_a_serio(self) -> None:
        assert not ps.is_store_python(r"C:\Python312\python.exe")
        assert not ps.is_store_python(r"C:\Users\rafael\AppData\Local\Programs\Python\Python312\python.exe")
        assert not ps.is_store_python(r"C:\projecto\.venv\Scripts\python.exe")

    def test_ignora_maiusculas_e_barras(self) -> None:
        # PT-PT: O caminho chega em maiúsculas e minúsculas conforme quem o
        #        escreveu, e às vezes com barras normais. Falhar por causa disso
        #        deixaria a armadilha passar exactamente onde ela existe.
        # EN-UK: The path arrives in whatever case whoever wrote it used, and
        #        sometimes with forward slashes. Failing over that would let the
        #        trap through exactly where it exists.
        assert ps.is_store_python(r"C:\USERS\X\APPDATA\LOCAL\MICROSOFT\WINDOWSAPPS\PYTHON.EXE")
        assert ps.is_store_python("C:/Users/x/AppData/Local/Microsoft/WindowsApps/python.exe")

    def test_e_um_requisito_essencial(self) -> None:
        # PT-PT: Não é um aviso estético: com o atalho da loja, a aplicação não
        #        corre de todo.
        # EN-UK: Not a cosmetic warning: with the Store shim the application does
        #        not run at all.
        requisitos = {r.name: r for r in ps.check_requirements()}
        assert requisitos["Origem do Python"].essential


class TestJanela:
    """PT-PT: O que a interface gráfica precisa. / EN-UK: What the window needs."""

    def test_o_tkinter_nao_e_essencial(self) -> None:
        # PT-PT: Sem Tkinter abre-se o modo de texto: perde-se a janela, não a
        #        aplicação.
        # EN-UK: Without Tkinter, text mode opens: the window is lost, not the
        #        application.
        requisitos = {r.name: r for r in ps.check_requirements()}
        assert not requisitos["Tkinter"].essential

    def test_sem_tkinter_diz_como_o_instalar(self) -> None:
        requisitos = {r.name: r for r in ps.check_requirements()}
        assert "tcl/tk" in requisitos["Tkinter"].command

    def test_em_windows_a_janela_so_depende_do_tkinter(self) -> None:
        assert ps.gui_available() is ps.tkinter_available()

    def test_preparar_a_janela_nunca_rebenta(self) -> None:
        # PT-PT: Fora de Windows (nos runners de CI) não há `windll`; a função
        #        tem de seguir em frente sem consciência de DPI.
        # EN-UK: Outside Windows (CI runners) there is no `windll`; the function
        #        must carry on without DPI awareness.
        ps.prepare_gui()

    def test_ha_letras_preferidas(self) -> None:
        assert ps.UI_FONT_FAMILIES[0] == "Segoe UI"
        assert ps.UI_FONT_SIZE > 0


class TestPastaDeDados:
    """PT-PT: A convenção do Windows. / EN-UK: The Windows convention."""

    def test_usa_o_appdata(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("APPDATA", str(tmp_path))
        assert ps.app_data_dir("X") == tmp_path / "X"

    def test_sem_appdata_cai_no_roaming(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APPDATA", raising=False)
        assert ps.app_data_dir("X") == Path.home() / "AppData" / "Roaming" / "X"

    def test_e_a_itinerante_e_nao_a_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # PT-PT: As definições e as impressões digitais dos certificados devem
        #        seguir o utilizador para outra máquina do domínio.
        # EN-UK: Settings and certificate fingerprints should follow the user to
        #        another machine on the domain.
        monkeypatch.delenv("APPDATA", raising=False)
        assert "Roaming" in str(ps.app_data_dir("X"))
        assert "Local" not in str(ps.app_data_dir("X"))

    def test_a_configuracao_usa_esta_pasta(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("APPDATA", str(tmp_path))
        assert app_data_dir() == tmp_path / APP_FOLDER_NAME


class TestPaginaDeCodigo:
    """
    PT-PT: A causa número um de "sai tudo aos quadradinhos".
    EN-UK: The number-one cause of "it all comes out as boxes".
    """

    def test_devolve_sempre_um_numero(self) -> None:
        # PT-PT: Nos runners de CI o `chcp.com` pode não existir. Zero é a
        #        resposta para "não se sabe", e é diferente de estar errada.
        # EN-UK: On CI runners `chcp.com` may not exist. Zero answers "not
        #        known", which is different from being wrong.
        assert isinstance(ps.code_page(), int)

    def test_a_codificacao_nao_e_essencial(self) -> None:
        requisitos = {r.name: r for r in ps.check_requirements()}
        assert not requisitos["Codificação"].essential


class TestDiagnostico:
    """PT-PT: O relatório de `--diagnostico`. / EN-UK: The `--diagnostico` report."""

    def test_nomeia_o_sistema_desta_versao(self) -> None:
        assert ps.SYSTEM_NAME == "Windows"
        assert "Windows" in ps.diagnostic_report()

    def test_lista_os_requisitos_essenciais(self) -> None:
        nomes = {r.name for r in ps.check_requirements()}
        assert {"Python", "Origem do Python", "pyVmomi"} <= nomes

    def test_o_pyvmomi_e_essencial(self) -> None:
        requisitos = {r.name: r for r in ps.check_requirements()}
        assert requisitos["pyVmomi"].essential

    def test_um_requisito_em_falta_diz_como_o_resolver(self) -> None:
        em_falta = [r for r in ps.check_requirements() if not r.present and r.command]
        for requisito in em_falta:
            assert requisito.command in str(requisito)


class TestSemRamificacaoPorSistema:
    """
    PT-PT: O teste que mantém a promessa das três versões.

           Esta versão corre em Windows e sabe que corre em Windows. Um
           `sys.platform` a decidir comportamento dentro dela é o princípio de a
           transformar numa versão só com ramificações — que é exactamente o que
           as três pastas existem para evitar.

    EN-UK: The test that keeps the three-version promise. This version runs on
           Windows and knows it.
    """

    def test_nenhum_modulo_ramifica_por_sistema_operativo(self) -> None:
        raiz = Path(__file__).resolve().parent.parent / "src" / "vfc"
        proibidos = ("sys.platform", "platform.system()", "os.name ==")
        falhas: list[str] = []

        for ficheiro in raiz.rglob("*.py"):
            texto = ficheiro.read_text(encoding="utf-8")
            for linha_numero, linha in enumerate(texto.splitlines(), 1):
                sem_comentario = linha.split("#")[0]
                for proibido in proibidos:
                    if proibido in sem_comentario:
                        falhas.append(f"{ficheiro.name}:{linha_numero}: {linha.strip()}")

        assert not falhas, (
            "Esta versão é a de Windows e não deve ramificar por sistema operativo.\n"
            + "\n".join(falhas)
        )
