#!/usr/bin/env python3
"""
PT-PT: Testes das particularidades do Linux, na versão de Linux da
       VMware Fleet Console.

       As outras duas versões têm os seus, nas pastas ao lado, e testam coisas
       diferentes — porque as particularidades de cada sistema são diferentes.

       O último teste desta suite é o que mantém a promessa das três versões:
       falha se alguém puser uma ramificação por sistema operativo dentro desta.

EN-UK: Linux specifics tests, in the Linux version of VMware Fleet Console.

       The other two versions have their own, in the folders alongside, and test
       different things — because each system's specifics are different.

       The last test in this suite is what keeps the three-version promise: it
       fails if somebody puts operating-system branching inside this one.

Created by Redfox using Claude
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vfc import platform_support as ps
from vfc.config import APP_FOLDER_NAME, app_data_dir
from vfc.platform_support import Distro


class TestDeteccaoDaDistribuicao:
    """PT-PT: Que família de Linux. / EN-UK: Which Linux family."""

    @pytest.mark.parametrize(
        ("identificador", "esperado"),
        [
            ("debian", Distro.DEBIAN),
            ("ubuntu", Distro.DEBIAN),
            ("fedora", Distro.FEDORA),
            ("rocky", Distro.FEDORA),
            ("arch", Distro.ARCH),
            ("manjaro", Distro.ARCH),
            ("opensuse-leap", Distro.SUSE),
            ("alpine", Distro.ALPINE),
        ],
    )
    def test_pelo_id(self, identificador: str, esperado: Distro) -> None:
        assert ps.detect_distro(f"ID={identificador}\n") is esperado

    def test_id_entre_aspas(self) -> None:
        assert ps.detect_distro('ID="fedora"\n') is Distro.FEDORA

    def test_derivada_pelo_id_like(self) -> None:
        # PT-PT: O Linux Mint não está na lista e funciona, porque diz de quem
        #        deriva. É isto que faz o suporte cobrir distribuições que nunca
        #        vimos.
        # EN-UK: Linux Mint is not on the list and works, because it says what
        #        it derives from.
        assert ps.detect_distro('ID=neon\nID_LIKE="ubuntu debian"\n') is Distro.DEBIAN

    def test_id_tem_prioridade_sobre_id_like(self) -> None:
        assert ps.detect_distro('ID=fedora\nID_LIKE="rhel"\n') is Distro.FEDORA

    def test_ficheiro_sem_nada_util(self) -> None:
        assert ps.detect_distro('NAME="Algo"\n') is Distro.UNKNOWN

    def test_ficheiro_vazio(self) -> None:
        assert ps.detect_distro("") is Distro.UNKNOWN

    def test_nome_bonito(self) -> None:
        assert ps.distro_name('PRETTY_NAME="Ubuntu 24.04 LTS"\n') == "Ubuntu 24.04 LTS"


class TestComandosDeInstalacao:
    """PT-PT: Dizer o comando certo. / EN-UK: Saying the right command."""

    @pytest.mark.parametrize(
        ("familia", "gestor"),
        [
            (Distro.DEBIAN, "apt"),
            (Distro.FEDORA, "dnf"),
            (Distro.ARCH, "pacman"),
            (Distro.SUSE, "zypper"),
            (Distro.ALPINE, "apk"),
        ],
    )
    def test_o_gestor_de_pacotes_certo(self, familia: Distro, gestor: str) -> None:
        assert gestor in ps.install_command("pip", familia)

    def test_distribuicao_desconhecida_da_um_conselho_generico(self) -> None:
        # PT-PT: Dizer `apt` a quem está numa distribuição desconhecida é pior
        #        do que não dizer nada: manda a pessoa correr um comando que não
        #        existe e faz a aplicação parecer mal feita.
        # EN-UK: Saying `apt` to somebody on an unknown distribution is worse
        #        than saying nothing: it sends them to a command that does not
        #        exist.
        conselho = ps.install_command("pip", Distro.UNKNOWN)
        assert "apt" not in conselho
        assert "gestor de pacotes" in conselho


class TestPastaDeDados:
    """PT-PT: A convenção XDG. / EN-UK: The XDG convention."""

    def test_usa_o_xdg_config_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert ps.app_data_dir("X") == tmp_path / "X"

    def test_sem_xdg_usa_o_config_da_pasta_pessoal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert ps.app_data_dir("X") == Path.home() / ".config" / "X"

    def test_xdg_relativo_e_ignorado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # PT-PT: A especificação exige um caminho absoluto. Honrar um relativo
        #        criaria a pasta onde quer que a aplicação tivesse arrancado.
        # EN-UK: The specification requires an absolute path. Honouring a
        #        relative one would create the folder wherever the application
        #        happened to start.
        monkeypatch.setenv("XDG_CONFIG_HOME", "config-relativo")
        assert ps.app_data_dir("X") == Path.home() / ".config" / "X"

    def test_a_configuracao_usa_esta_pasta(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert app_data_dir() == tmp_path / APP_FOLDER_NAME


class TestJanela:
    """PT-PT: O que a interface gráfica precisa. / EN-UK: What the window needs."""

    def test_wayland_tambem_conta(self) -> None:
        assert ps.display_available({"WAYLAND_DISPLAY": "wayland-0"})

    def test_sem_ambiente_grafico(self) -> None:
        # PT-PT: Um servidor, uma sessão SSH sem -X: não há onde abrir a janela,
        #        e o arranque cai no modo de texto em vez de rebentar.
        # EN-UK: A server, an SSH session without -X: nowhere to open the
        #        window, so startup falls back to text mode instead of failing.
        assert not ps.display_available({})

    def test_sem_ecra_a_janela_nao_esta_disponivel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        assert not ps.gui_available()

    @pytest.mark.parametrize(
        ("familia", "pacote"),
        [
            (Distro.DEBIAN, "python3-tk"),
            (Distro.FEDORA, "python3-tkinter"),
            (Distro.ARCH, "pacman -S tk"),
            (Distro.SUSE, "python3-tk"),
            (Distro.ALPINE, "py3-tkinter"),
        ],
    )
    def test_o_pacote_do_tkinter_em_cada_familia(self, familia: Distro, pacote: str) -> None:
        assert pacote in ps.install_command("tkinter", familia)

    def test_preparar_a_janela_nao_faz_nada_nem_rebenta(self) -> None:
        assert ps.prepare_gui() is None


class TestDiagnostico:
    """PT-PT: O relatório de `--diagnostico`. / EN-UK: The `--diagnostico` report."""

    def test_nomeia_o_sistema_desta_versao(self) -> None:
        relatorio = ps.diagnostic_report()
        assert ps.SYSTEM_NAME == "Linux"
        assert "Linux" in relatorio

    def test_lista_os_requisitos_essenciais(self) -> None:
        nomes = {r.name for r in ps.check_requirements()}
        assert {"Python", "pyVmomi"} <= nomes

    def test_o_pyvmomi_e_essencial_e_a_janela_nao(self) -> None:
        # PT-PT: Sem pyVmomi não há ligação nenhuma; sem Tkinter ou sem ambiente
        #        gráfico há o modo de texto. Apresentar os dois com a mesma
        #        gravidade levaria alguém a desistir por causa do segundo.
        # EN-UK: With no pyVmomi there is no connection at all; with no Tkinter
        #        or desktop there is text mode. Same severity for both would make
        #        somebody give up over the second.
        requisitos = {r.name: r for r in ps.check_requirements()}
        assert requisitos["pyVmomi"].essential
        assert not requisitos["Tkinter"].essential
        assert not requisitos["Ambiente gráfico"].essential

    def test_um_requisito_em_falta_diz_como_o_instalar(self) -> None:
        em_falta = [r for r in ps.check_requirements() if not r.present and r.command]
        for requisito in em_falta:
            assert requisito.command in str(requisito)


class TestSemRamificacaoPorSistema:
    """
    PT-PT: O teste que mantém a promessa das três versões.

           Esta versão corre em Linux e sabe que corre em Linux. Um
           `sys.platform` ou um `platform.system()` a decidir comportamento
           dentro dela é o princípio de a transformar numa versão só com
           ramificações — que é exactamente o que as três pastas existem para
           evitar. As outras duas versões têm este mesmo teste.

    EN-UK: The test that keeps the three-version promise. This version runs on
           Linux and knows it. A `sys.platform` deciding behaviour inside it is
           the beginning of turning three versions into one with branches, which
           is exactly what the three folders exist to avoid.
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
            "Esta versão é a de Linux e não deve ramificar por sistema operativo.\n"
            + "\n".join(falhas)
        )
