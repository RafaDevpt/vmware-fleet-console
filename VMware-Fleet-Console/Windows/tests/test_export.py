#!/usr/bin/env python3
"""
PT-PT: A exportação de máquinas para OVF.

       Duas metades, como no resto da suite. A guarda (`check_export`) é
       testada contra o parque inventado do `conftest.py`. A execução
       (`Exporter`) é testada a sério: há um servidor HTTPS verdadeiro a correr
       nesta máquina, com um certificado auto-assinado fixado pela impressão
       digital — exactamente como um ESXi de fábrica — e é dele que os "discos"
       são descarregados. Do vSphere só se simula o que não se consegue ter sem
       um: a concessão, o encerramento e o descritor.

       O que estes testes guardam, acima de tudo, são três promessas: **nunca
       se desliga à força**, **uma máquina encerrada por nós volta a ser ligada
       mesmo quando a cópia falha**, e **uma exportação falhada não deixa
       ficheiros que pareçam um backup**.

EN-UK: Exporting machines to OVF. The guard is tested against the invented
       estate; the execution is tested for real against an HTTPS server running
       locally with a pinned self-signed certificate — like a factory ESXi —
       with only the lease, the shutdown and the descriptor simulated. Above
       all these tests keep three promises: **never power off by force**, **a
       machine we shut down comes back on even when the copy fails**, and **a
       failed export leaves no files that look like a backup**.

Created by Redfox using Claude
"""

from __future__ import annotations

import hashlib
import http.server
import ssl
import threading
from pathlib import Path

import pytest

from vfc import connection, export
from vfc.export import Exporter, ExportJob, Stage, check_export
from vfc.models import PowerState, VMInfo

FIXTURES = Path(__file__).parent / "fixtures"
COOKIE = 'vmware_soap_session="sessao-de-teste"'
DISCO = b"VMDK-stream-optimized " * 50_000  # ~1 MB, para haver vários blocos


# ---------------------------------------------------------------------------
# PT-PT: A guarda.
# EN-UK: The guard.
# ---------------------------------------------------------------------------


class TestGuarda:
    def test_desligada_exporta_sem_mais(self, maquina_desligada: VMInfo, parque: object) -> None:
        decisao = check_export(maquina_desligada, parque, allow_shutdown=False)  # type: ignore[arg-type]
        assert decisao.allowed
        assert not decisao.needs_shutdown

    def test_modelo_tambem_se_exporta(self, modelo: VMInfo, parque: object) -> None:
        assert check_export(modelo, parque, allow_shutdown=False).allowed  # type: ignore[arg-type]

    def test_ligada_sem_autorizacao_e_recusada(self, maquina_normal: VMInfo, parque: object) -> None:
        decisao = check_export(maquina_normal, parque, allow_shutdown=False)  # type: ignore[arg-type]
        assert not decisao.allowed
        assert "desligadas" in decisao.reason

    def test_ligada_com_autorizacao_vai_ser_encerrada(self, maquina_normal: VMInfo, parque: object) -> None:
        decisao = check_export(maquina_normal, parque, allow_shutdown=True)  # type: ignore[arg-type]
        assert decisao.allowed
        assert decisao.needs_shutdown
        assert decisao.warning

    def test_sem_tools_nunca_e_desligada_a_forca(self, maquina_sem_tools: VMInfo, parque: object) -> None:
        # PT-PT: A promessa principal: sem encerramento limpo, não há exportação
        #        de uma máquina ligada. Nem com a opção activa.
        # EN-UK: The main promise: no clean shutdown, no export of a running
        #        machine — not even with the option on.
        decisao = check_export(maquina_sem_tools, parque, allow_shutdown=True)  # type: ignore[arg-type]
        assert not decisao.allowed
        assert "não desliga máquinas à força" in decisao.reason

    def test_anfitriao_sem_resposta(self, maquina_orfa: VMInfo, parque: object) -> None:
        decisao = check_export(maquina_orfa, parque, allow_shutdown=True)  # type: ignore[arg-type]
        assert not decisao.allowed
        assert "esx02.lab.local" in decisao.reason

    def test_suspensa_e_recusada(self, maquina_normal: VMInfo) -> None:
        maquina_normal.power_state = PowerState.SUSPENDED
        assert not check_export(maquina_normal, None, allow_shutdown=True).allowed

    def test_estado_desconhecido_e_recusado(self, maquina_normal: VMInfo) -> None:
        maquina_normal.power_state = PowerState.UNKNOWN
        assert not check_export(maquina_normal, None, allow_shutdown=True).allowed

    def test_o_proprio_vcenter_nao_e_encerrado(self, maquina_normal: VMInfo) -> None:
        maquina_normal.ip_address = "10.0.0.5"
        decisao = check_export(
            maquina_normal, None, allow_shutdown=True,
            endpoint_host="vcenter.lab.local", endpoint_addresses={"10.0.0.5"},
        )
        assert not decisao.allowed
        assert "próprio servidor" in decisao.reason

    def test_o_proprio_vcenter_pelo_nome(self, maquina_normal: VMInfo) -> None:
        maquina_normal.hostname = "VCENTER"
        maquina_normal.ip_address = ""
        assert not check_export(
            maquina_normal, None, allow_shutdown=True, endpoint_host="vcenter.lab.local"
        ).allowed

    def test_estimativa_so_conta_as_permitidas(self, maquina_desligada: VMInfo, maquina_sem_tools: VMInfo) -> None:
        maquina_desligada.committed_bytes = 10
        maquina_sem_tools.committed_bytes = 1000
        decisoes = [
            check_export(maquina_desligada, None, allow_shutdown=True),
            check_export(maquina_sem_tools, None, allow_shutdown=True),
        ]
        assert export.estimated_bytes(decisoes) == 10


class TestNomes:
    @pytest.mark.parametrize(
        ("nome", "esperado"),
        [
            ("SRV-APP01", "SRV-APP01"),
            ("a/b\\c:d", "a_b_c_d"),
            ("nome.", "nome"),
            ("NUL", "_NUL"),
            ("com1.txt", "_com1.txt"),
        ],
    )
    def test_nomes_que_o_windows_aceita(self, nome: str, esperado: str) -> None:
        assert export.safe_name(nome) == esperado


# ---------------------------------------------------------------------------
# PT-PT: Um "ESXi" de bolso: um servidor HTTPS a sério e objectos que fingem
#        ser os do pyVmomi.
# EN-UK: A pocket "ESXi": a real HTTPS server and objects pretending to be
#        pyVmomi's.
# ---------------------------------------------------------------------------


class _Pedidos(http.server.BaseHTTPRequestHandler):
    exige_cookie = COOKIE
    pedidos: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 - nome imposto pelo http.server
        type(self).pedidos.append(self.path)
        if self.headers.get("Cookie") != self.exige_cookie:
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(DISCO)))
        self.end_headers()
        self.wfile.write(DISCO)

    def log_message(self, *args: object) -> None:  # silêncio nos testes
        return


class _ServidorSilencioso(http.server.ThreadingHTTPServer):
    """
    PT-PT: Um cliente que cancela a meio corta a ligação, e isso é o esperado
           — não é um erro para escrever na saída dos testes.
    EN-UK: A client cancelling halfway drops the connection, which is expected
           — not an error to print into the test output.
    """

    def handle_error(self, request: object, client_address: object) -> None:
        return


@pytest.fixture
def servidor() -> object:
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(FIXTURES / "servidor-teste.crt", FIXTURES / "servidor-teste.key")
    httpd = _ServidorSilencioso(("127.0.0.1", 0), _Pedidos)
    httpd.socket = contexto.wrap_socket(httpd.socket, server_side=True)
    _Pedidos.pedidos = []
    _Pedidos.exige_cookie = COOKIE
    fio = threading.Thread(target=httpd.serve_forever, daemon=True)
    fio.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _der() -> bytes:
    return ssl.PEM_cert_to_DER_cert((FIXTURES / "servidor-teste.crt").read_text())


class _Tarefa:
    def __init__(self, estado: str = "success") -> None:
        self.info = type("Info", (), {"state": estado, "error": None})()


class _Concessao:
    def __init__(self, porta: int) -> None:
        self.state = "ready"
        self.error = None
        self.progressos: list[int] = []
        self.completa = False
        self.abortada = False
        disco = type("Url", (), {
            "key": "/vm-1/VirtualLsiLogicController0:0",
            "url": f"https://*:{porta}/nfc/bilhete/disk-0.vmdk",
            "targetId": "disk-0.vmdk",
            "sslThumbprint": "",
            "disk": True,
        })()
        cd = type("Url", (), {"key": "/vm-1/cdrom", "url": f"https://*:{porta}/nfc/cd.iso",
                              "targetId": None, "sslThumbprint": "", "disk": False})()
        self.info = type("Info", (), {"deviceUrl": [disco, cd], "leaseTimeout": 300})()

    def HttpNfcLeaseProgress(self, percent: int) -> None:  # noqa: N802
        self.progressos.append(percent)

    def HttpNfcLeaseComplete(self) -> None:  # noqa: N802
        self.completa = True

    def HttpNfcLeaseAbort(self) -> None:  # noqa: N802
        self.abortada = True


class _VM:
    """PT-PT: Uma máquina que encerra ao fim de `encerra_ao_fim` consultas."""

    def __init__(self, porta: int, estado: str, encerra_ao_fim: int = 1) -> None:
        self.runtime = type("Runtime", (), {"powerState": estado})()
        self._porta = porta
        self._consultas = encerra_ao_fim
        self.pedidos: list[str] = []
        self.concessao: _Concessao | None = None

    def ShutdownGuest(self) -> None:  # noqa: N802
        self.pedidos.append("ShutdownGuest")
        vm = self

        class _Runtime:
            @property
            def powerState(self) -> str:  # noqa: N802
                vm._consultas -= 1
                return "poweredOff" if vm._consultas < 0 else "poweredOn"

        if self._consultas >= 0:
            self.runtime = _Runtime()

    def PowerOffVM_Task(self) -> _Tarefa:  # noqa: N802
        self.pedidos.append("PowerOffVM_Task")  # nunca devia acontecer
        return _Tarefa()

    def PowerOnVM_Task(self) -> _Tarefa:  # noqa: N802
        self.pedidos.append("PowerOnVM_Task")
        self.runtime = type("Runtime", (), {"powerState": "poweredOn"})()
        return _Tarefa()

    def ExportVm(self) -> _Concessao:  # noqa: N802
        self.pedidos.append("ExportVm")
        self.concessao = _Concessao(self._porta)
        return self.concessao


class _Ovf:
    def __init__(self) -> None:
        self.parametros = None

    def CreateDescriptor(self, obj: object, cdp: object) -> object:  # noqa: N802
        self.parametros = cdp
        ficheiros = "".join(f'<File ovf:href="{f.path}" ovf:size="{f.size}"/>' for f in cdp.ovfFiles)
        return type("R", (), {"ovfDescriptor": f"<Envelope>{ficheiros}</Envelope>", "error": [], "warning": []})()


class _Sessao:
    def __init__(self, porta: int, vm: _VM) -> None:
        self.endpoint = connection.Endpoint("127.0.0.1", "root", porta)
        self.ssl_context = connection._anchored_context(_der())
        self.content = type("C", (), {"ovfManager": _Ovf()})()
        self.vm = vm

    def cookie_header(self) -> str:
        return COOKIE

    def vm_by_moid(self, moid: str) -> _VM:
        return self.vm


def _exportar(tmp_path: Path, sessao: _Sessao, vm_modelo: VMInfo, **opcoes: object) -> export.BatchResult:
    eventos: list[export.ExportEvent] = []
    cancelar = opcoes.pop("cancelar", threading.Event())
    ligar_depois = bool(opcoes.pop("power_on_after", True))
    exportador = Exporter(
        sessao, tmp_path / "destino", eventos.append, cancelar,  # type: ignore[arg-type]
        shutdown_timeout=int(opcoes.pop("shutdown_timeout", 30)), poll_interval=0.01,
    )
    decisao = check_export(vm_modelo, None, allow_shutdown=True)
    lote = exportador.run([ExportJob(decisao, power_on_after=ligar_depois)])
    lote.eventos = eventos  # type: ignore[attr-defined]
    return lote


class TestExportacao:
    def test_maquina_desligada_fica_completa_e_verificavel(
        self, servidor: object, tmp_path: Path, maquina_desligada: VMInfo
    ) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        vm = _VM(porta, "poweredOff")
        sessao = _Sessao(porta, vm)
        lote = _exportar(tmp_path, sessao, maquina_desligada)

        resultado = lote.results[0]
        assert resultado.stage is Stage.DONE, resultado.message
        pasta = Path(resultado.folder)
        nomes = sorted(p.name for p in pasta.iterdir())
        assert nomes == ["LEIA-ME.txt", "SRV-TESTE-disk-0.vmdk", "SRV-TESTE.mf", "SRV-TESTE.ovf"]

        # PT-PT: O disco chegou inteiro e o manifesto confere.
        # EN-UK: The disk arrived whole and the manifest checks out.
        assert (pasta / "SRV-TESTE-disk-0.vmdk").read_bytes() == DISCO
        manifesto = (pasta / "SRV-TESTE.mf").read_text().splitlines()
        assert f"SHA256(SRV-TESTE-disk-0.vmdk)= {hashlib.sha256(DISCO).hexdigest()}" in manifesto
        ovf = (pasta / "SRV-TESTE.ovf").read_bytes()
        assert f"SHA256(SRV-TESTE.ovf)= {hashlib.sha256(ovf).hexdigest()}" in manifesto

        # PT-PT: O descritor referencia o ficheiro com o tamanho real; a
        #        entrada sem targetId (o CD) não foi descarregada.
        # EN-UK: The descriptor references the file at its real size; the
        #        entry with no targetId (the CD) was not downloaded.
        ficheiro = sessao.content.ovfManager.parametros.ovfFiles[0]  # type: ignore[attr-defined]
        assert (ficheiro.path, ficheiro.size) == ("SRV-TESTE-disk-0.vmdk", len(DISCO))
        assert _Pedidos.pedidos == ["/nfc/bilhete/disk-0.vmdk"]

        assert vm.concessao is not None and vm.concessao.completa and not vm.concessao.abortada
        assert vm.pedidos == ["ExportVm"]  # nem encerrada nem ligada
        relatorio = Path(lote.report_path).read_text(encoding="utf-8")
        assert "Created by Redfox using Claude" in relatorio
        assert "Created by Redfox using Claude" in (pasta / "LEIA-ME.txt").read_text(encoding="utf-8")

    def test_ligada_e_encerrada_exportada_e_religada(
        self, servidor: object, tmp_path: Path, maquina_normal: VMInfo
    ) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        vm = _VM(porta, "poweredOn", encerra_ao_fim=2)
        lote = _exportar(tmp_path, _Sessao(porta, vm), maquina_normal)

        resultado = lote.results[0]
        assert resultado.stage is Stage.DONE, resultado.message
        assert vm.pedidos == ["ShutdownGuest", "ExportVm", "PowerOnVM_Task"]
        assert resultado.was_shut_down and resultado.powered_back_on
        etapas = [e.stage for e in lote.eventos]  # type: ignore[attr-defined]
        assert etapas.index(Stage.SHUTTING_DOWN) < etapas.index(Stage.DOWNLOADING) < etapas.index(Stage.POWERING_ON)

    def test_pode_ficar_desligada_para_a_manutencao(
        self, servidor: object, tmp_path: Path, maquina_normal: VMInfo
    ) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        vm = _VM(porta, "poweredOn")
        lote = _exportar(tmp_path, _Sessao(porta, vm), maquina_normal, power_on_after=False)
        assert lote.results[0].stage is Stage.DONE
        assert "PowerOnVM_Task" not in vm.pedidos

    def test_nao_encerrou_a_tempo_nao_e_forcada(
        self, servidor: object, tmp_path: Path, maquina_normal: VMInfo
    ) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        vm = _VM(porta, "poweredOn", encerra_ao_fim=10_000)
        lote = _exportar(tmp_path, _Sessao(porta, vm), maquina_normal, shutdown_timeout=0)
        resultado = lote.results[0]
        assert resultado.stage is Stage.FAILED
        assert "não foi desligada à força" in resultado.message.lower()
        assert "PowerOffVM_Task" not in vm.pedidos
        assert "ExportVm" not in vm.pedidos
        # PT-PT: Continua ligada — não se lhe pede para ligar outra vez.
        # EN-UK: Still running — it is not asked to power on again.
        assert "PowerOnVM_Task" not in vm.pedidos

    def test_falha_na_transferencia_nao_deixa_restos_e_religa(
        self, servidor: object, tmp_path: Path, maquina_normal: VMInfo
    ) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        _Pedidos.exige_cookie = "outro-cookie"
        vm = _VM(porta, "poweredOn")
        lote = _exportar(tmp_path, _Sessao(porta, vm), maquina_normal)

        resultado = lote.results[0]
        assert resultado.stage is Stage.FAILED
        assert "HTTP 403" in resultado.message
        assert vm.concessao is not None and vm.concessao.abortada
        assert vm.pedidos[-1] == "PowerOnVM_Task"
        # PT-PT: Só ficou o relatório na raiz — nenhuma pasta de máquina.
        # EN-UK: Only the report at the root — no machine folder.
        assert all(p.is_file() for p in (tmp_path / "destino").iterdir())

    def test_cancelar_a_meio_apaga_e_religa(
        self, servidor: object, tmp_path: Path, maquina_normal: VMInfo
    ) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        vm = _VM(porta, "poweredOn")
        cancelar = threading.Event()
        sessao = _Sessao(porta, vm)
        original = Exporter._emit

        def emitir(self: Exporter, indice: int, nome: str, etapa: Stage, *resto: object) -> None:
            if etapa is Stage.DOWNLOADING:
                cancelar.set()
            original(self, indice, nome, etapa, *resto)  # type: ignore[arg-type]

        Exporter._emit = emitir  # type: ignore[method-assign]
        try:
            lote = _exportar(tmp_path, sessao, maquina_normal, cancelar=cancelar)
        finally:
            Exporter._emit = original  # type: ignore[method-assign]

        assert lote.results[0].stage is Stage.CANCELLED
        assert vm.concessao is not None and vm.concessao.abortada
        assert vm.pedidos[-1] == "PowerOnVM_Task"
        assert not list((tmp_path / "destino").glob("SRV-APP01_*"))

    def test_sem_espaco_nao_encerra_ninguem(
        self, servidor: object, tmp_path: Path, maquina_normal: VMInfo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        monkeypatch.setattr(export, "free_bytes", lambda _destino: 1024)
        vm = _VM(porta, "poweredOn")
        lote = _exportar(tmp_path, _Sessao(porta, vm), maquina_normal)
        assert lote.results[0].stage is Stage.FAILED
        assert vm.pedidos == []

    def test_ligada_depois_de_escolhida_nao_e_encerrada(
        self, servidor: object, tmp_path: Path, maquina_desligada: VMInfo
    ) -> None:
        # PT-PT: Escolhida desligada, mas entretanto alguém a ligou. A guarda
        #        não autorizou encerrar, portanto não se encerra.
        # EN-UK: Chosen while off, but somebody powered it on since. The guard
        #        never authorised a shutdown, so none happens.
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        vm = _VM(porta, "poweredOn")
        lote = _exportar(tmp_path, _Sessao(porta, vm), maquina_desligada)
        assert lote.results[0].stage is Stage.FAILED
        assert vm.pedidos == []


class TestEnderecos:
    def test_o_asterisco_e_o_servidor_da_sessao(self) -> None:
        sessao = type("S", (), {"endpoint": connection.Endpoint("esx01.lab.local", "root")})()
        exportador = Exporter(sessao, Path("."), lambda _e: None, threading.Event())
        assert exportador._resolve_url("https://*/nfc/x/disk-0.vmdk") == "https://esx01.lab.local/nfc/x/disk-0.vmdk"

    def test_ipv6_leva_parenteses(self) -> None:
        sessao = type("S", (), {"endpoint": connection.Endpoint("fd00::10", "root")})()
        exportador = Exporter(sessao, Path("."), lambda _e: None, threading.Event())
        assert exportador._resolve_url("https://*/nfc/x") == "https://[fd00::10]/nfc/x"

    def test_porta_da_sessao_quando_nao_e_a_443(self) -> None:
        sessao = type("S", (), {"endpoint": connection.Endpoint("esx01", "root", 8443)})()
        exportador = Exporter(sessao, Path("."), lambda _e: None, threading.Event())
        assert exportador._resolve_url("https://*/nfc/x") == "https://esx01:8443/nfc/x"

    def test_endereco_do_vcenter_fica_como_esta(self) -> None:
        sessao = type("S", (), {"endpoint": connection.Endpoint("vc.lab.local", "u")})()
        exportador = Exporter(sessao, Path("."), lambda _e: None, threading.Event())
        assert exportador._resolve_url("https://esx01/nfc/x") == "https://esx01/nfc/x"


class TestCertificadoDaTransferencia:
    """
    PT-PT: O cookie da sessão é uma credencial. Só sai para um certificado que
           alguém (ou o próprio servidor autenticado) validou.
    EN-UK: The session cookie is a credential. It only leaves for a certificate
           somebody (or the authenticated server itself) vouched for.
    """

    def test_mesmo_servidor_reutiliza_o_contexto(self) -> None:
        sessao = connection.Session(object(), connection.Endpoint("esx01", "root"), ssl.create_default_context())
        assert connection.transfer_context(sessao, "ESX01") is sessao.ssl_context

    def test_impressao_sha1_anunciada_e_imposta(self, servidor: object) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        sessao = connection.Session(object(), connection.Endpoint("vcenter", "u"))
        certa = connection.sha1_fingerprint_of(_der())
        contexto = connection.transfer_context(sessao, "127.0.0.1", porta, certa)
        assert contexto.verify_mode is ssl.CERT_REQUIRED

    def test_impressao_errada_trava_antes_do_cookie(self, servidor: object) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        sessao = connection.Session(object(), connection.Endpoint("vcenter", "u"))
        with pytest.raises(connection.VSphereConnectionError, match="não é o que o vCenter anunciou"):
            connection.transfer_context(sessao, "127.0.0.1", porta, "00:" * 19 + "00")
        assert _Pedidos.pedidos == []

    def test_sem_impressao_e_sem_cadeia_valida_recusa(self, servidor: object) -> None:
        porta = servidor.server_address[1]  # type: ignore[attr-defined]
        sessao = connection.Session(object(), connection.Endpoint("vcenter", "u"))
        with pytest.raises(connection.VSphereConnectionError, match="download.zip"):
            connection.transfer_context(sessao, "127.0.0.1", porta, "")


class TestCertificadoEmitidoPorUmaAutoridade:
    """
    PT-PT: A correcção da 2.0 em `connection._anchored_context`: um certificado
           que não é a sua própria raiz (o de um ESXi gerido por vCenter, emitido
           pela VMCA) tem de ser aceite quando é exactamente o que foi fixado.
    EN-UK: The 2.0 fix: a certificate that is not its own root (a vCenter-managed
           ESXi's, issued by the VMCA) must be accepted when it is exactly the
           pinned one.
    """

    def test_contexto_aceita_cadeia_parcial(self) -> None:
        contexto = connection._anchored_context(_der())
        assert contexto.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
