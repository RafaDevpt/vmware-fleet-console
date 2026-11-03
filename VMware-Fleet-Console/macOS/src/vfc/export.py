#!/usr/bin/env python3
"""
PT-PT: Exportação de máquinas virtuais para OVF — a cópia da máquina inteira,
       não do que está dentro dela.

       **Porque existe.** Um backup feito com agente dentro do Windows protege
       os dados e o sistema, mas para recuperar a máquina é preciso um restauro
       a partir do zero: perde-se o `.vmx`, o hardware virtual, as placas de
       rede e as VLANs a que estavam ligadas. Antes de mexer no armazenamento
       de um anfitrião — refazer um RAID, por exemplo — o que se quer é a
       máquina tal como o vSphere a vê, pronta a importar.

       **Como funciona, sem ferramentas externas.** É o mesmo mecanismo que o
       `ovftool` e o cliente web usam por baixo:

       1. `VirtualMachine.ExportVm()` devolve uma concessão (`HttpNfcLease`)
          com um endereço HTTPS por disco.
       2. Os discos descarregam-se por esses endereços, já no formato
          *stream-optimized* — comprimido, só com os blocos usados.
       3. A concessão tem de ser mantida viva enquanto se descarrega
          (`HttpNfcLeaseProgress`), senão o servidor fecha-a a meio.
       4. No fim, `OvfManager.CreateDescriptor()` escreve o `.ovf` que
          descreve a máquina e referencia os discos descarregados.
       5. Escreve-se o manifesto `.mf` com o SHA-256 de cada ficheiro, que o
          vSphere verifica ao importar.

       **A regra que não se negocia: o vSphere só exporta máquinas
       desligadas.** Para uma máquina ligada, a aplicação pode — se lhe for
       pedido explicitamente — encerrar o sistema convidado pelas VMware Tools,
       exportar, e voltar a ligá-la. Uma máquina de cada vez, para que o tempo
       parado de cada uma seja só o da sua própria cópia. **Nunca desliga à
       força**: se o sistema convidado não encerrar dentro do prazo, a máquina
       fica como está e a exportação dela é dada como falhada.

       **Uma exportação que falha não deixa nada para trás.** Ficheiros a meio
       são apagados. Uma pasta com um disco incompleto é pior do que nenhuma,
       porque parece um backup.

EN-UK: Exporting virtual machines to OVF — a copy of the whole machine, not of
       what is inside it.

       An agent-based backup inside Windows protects data and the OS, but
       recovering the machine means a bare-metal restore: the `.vmx`, the
       virtual hardware, the NICs and their VLANs are gone. Before touching a
       host's storage, what you want is the machine as vSphere sees it.

       No external tools: `ExportVm()` hands out an `HttpNfcLease` with one
       HTTPS URL per disk; the disks download stream-optimized; the lease is
       kept alive with `HttpNfcLeaseProgress`; `CreateDescriptor()` writes the
       `.ovf`; a SHA-256 `.mf` manifest is written for import-time checking.

       vSphere only exports powered-off machines. For a running machine the
       application can — when explicitly asked — shut the guest down through
       VMware Tools, export, and power it back on, one machine at a time. It
       **never powers off by force**. A failed export leaves nothing behind:
       a folder holding half a disk looks like a backup, which is worse than
       no folder at all.

Created by Redfox using Claude
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import re
import shutil
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from . import __version__, branding
from .actions import explain_failure
from .connection import VSphereConnectionError, transfer_context
from .models import Fleet, PowerState, VMInfo, format_bytes

logger = logging.getLogger(__name__)

CHUNK_BYTES = 1024 * 1024
MIN_FREE_BYTES = 1024**3
DEFAULT_SHUTDOWN_TIMEOUT = 600
LEASE_READY_TIMEOUT = 180
POWER_ON_TIMEOUT = 300
PROGRESS_INTERVAL = 0.25

# PT-PT: Caracteres que o Windows não aceita num nome de ficheiro, e o NTFS
#        também não gosta de um nome acabado em ponto ou espaço.
# EN-UK: Characters Windows refuses in a file name; NTFS also dislikes a name
#        ending in a dot or a space.
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class Stage(str, Enum):
    """
    PT-PT: Em que ponto está a exportação de uma máquina.
    EN-UK: Where a machine's export stands.
    """

    QUEUED = "em-fila"
    SHUTTING_DOWN = "a-encerrar"
    PREPARING = "a-preparar"
    DOWNLOADING = "a-descarregar"
    DESCRIBING = "a-descrever"
    POWERING_ON = "a-ligar"
    DONE = "concluida"
    FAILED = "falhou"
    CANCELLED = "cancelada"

    @property
    def label(self) -> str:
        return {
            "em-fila": "Em fila",
            "a-encerrar": "A encerrar o sistema",
            "a-preparar": "A preparar",
            "a-descarregar": "A descarregar",
            "a-descrever": "A escrever o OVF",
            "a-ligar": "A voltar a ligar",
            "concluida": "Concluída",
            "falhou": "Falhou",
            "cancelada": "Cancelada",
        }[self.value]

    @property
    def finished(self) -> bool:
        return self in (Stage.DONE, Stage.FAILED, Stage.CANCELLED)


# ---------------------------------------------------------------------------
# PT-PT: A decisão — sem rede, testável.
# EN-UK: The decision — no network, testable.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportCheck:
    """
    PT-PT: Se esta máquina pode ser exportada, e o que isso implica.

           `needs_shutdown` diz que a máquina está ligada e vai ser encerrada
           pelo sistema convidado antes da cópia. É uma consequência que a
           pessoa tem de ver escrita antes de confirmar, e por isso vem aqui e
           não é decidida em silêncio na execução.

    EN-UK: Whether this machine can be exported, and what that implies.
           `needs_shutdown` says it is running and will be shut down through
           the guest before the copy — a consequence the person must see
           written before confirming, so it lives here rather than being
           decided silently during execution.
    """

    vm: VMInfo
    allowed: bool
    reason: str = ""
    needs_shutdown: bool = False
    warning: str = ""


def serves_connection(vm: VMInfo, endpoint_host: str, endpoint_addresses: set[str]) -> bool:
    """
    PT-PT: Se esta máquina é, provavelmente, o próprio servidor desta sessão.

           O caso real é o vCenter em appliance a correr no anfitrião que se
           gere por ele: encerrá-lo para o exportar corta a sessão a meio, e a
           máquina fica desligada sem ninguém para a voltar a ligar. Compara-se
           o endereço e o nome que as Tools reportam com o endereço a que se
           está ligado. Sem Tools não há como saber — e sem Tools também não há
           encerramento limpo, portanto essa máquina já é recusada por outra
           razão.

    EN-UK: Whether this machine is, most likely, this session's own server. The
           real case is a vCenter appliance on the host it manages: shutting it
           down to export it kills the session halfway and leaves the machine
           off with nobody to power it back on. Compared on the address and
           name Tools report against what the session is connected to.

    >>> from vfc.models import VMInfo
    >>> serves_connection(VMInfo("vm-1", "vcsa", ip_address="10.0.0.5"), "vc.local", {"10.0.0.5"})
    True
    >>> serves_connection(VMInfo("vm-2", "sql", ip_address="10.0.0.9"), "vc.local", {"10.0.0.5"})
    False
    """
    alvo = endpoint_host.strip().casefold()
    curto = alvo.split(".", 1)[0]
    nome = vm.hostname.strip().casefold()
    if vm.ip_address and (vm.ip_address == alvo or vm.ip_address in endpoint_addresses):
        return True
    return bool(nome) and (nome == alvo or nome.split(".", 1)[0] == curto)


def check_export(
    vm: VMInfo,
    fleet: Fleet | None,
    allow_shutdown: bool,
    endpoint_host: str = "",
    endpoint_addresses: set[str] | None = None,
) -> ExportCheck:
    """
    PT-PT: A guarda da exportação. A ordem é a das perguntas que importam.

           Os modelos (templates) passam: estão sempre desligados e
           exportam-se como qualquer máquina desligada.

    EN-UK: The export guard, asking the questions in the order they matter.
           Templates pass: they are always powered off and export like any
           powered-off machine.
    """
    if fleet is not None and vm.host_name:
        anfitriao = next((h for h in fleet.hosts if h.name == vm.host_name), None)
        if anfitriao is not None and not anfitriao.reachable:
            return ExportCheck(
                vm,
                allowed=False,
                reason=(
                    f"O anfitrião {anfitriao.name} está "
                    f"{anfitriao.connection_state.label.lower()}: os discos não têm de onde vir."
                ),
            )

    if vm.power_state is PowerState.UNKNOWN:
        return ExportCheck(
            vm, allowed=False, reason="Estado de alimentação desconhecido. Actualize o inventário."
        )

    if vm.power_state is PowerState.SUSPENDED:
        return ExportCheck(
            vm,
            allowed=False,
            reason=(
                "Está suspensa. O vSphere só exporta máquinas desligadas: ligue-a e "
                "encerre-a, ou desligue-a, e volte a tentar."
            ),
        )

    if vm.power_state is PowerState.OFF:
        return ExportCheck(vm, allowed=True)

    # PT-PT: Daqui para baixo, a máquina está ligada.
    # EN-UK: From here on, the machine is running.
    if not allow_shutdown:
        return ExportCheck(
            vm,
            allowed=False,
            reason=(
                "Está ligada, e o vSphere só exporta máquinas desligadas. Active a opção "
                "de encerrar as máquinas ligadas, ou encerre-a primeiro."
            ),
        )

    if not vm.tools_status.allows_guest_operations:
        return ExportCheck(
            vm,
            allowed=False,
            reason=(
                f"Está ligada e as VMware Tools não estão a correr (estado: "
                f"{vm.tools_status.label.lower()}). Sem elas não há encerramento limpo, e esta "
                "aplicação não desliga máquinas à força para as exportar. Encerre-a pelo próprio "
                "sistema e volte a tentar."
            ),
        )

    if endpoint_host and serves_connection(vm, endpoint_host, endpoint_addresses or set()):
        return ExportCheck(
            vm,
            allowed=False,
            reason=(
                "Parece ser o próprio servidor a que esta sessão está ligada. Encerrá-la "
                "cortava a sessão a meio e deixava-a desligada. Exporte-a ligando "
                "directamente ao anfitrião ESXi."
            ),
        )

    return ExportCheck(
        vm,
        allowed=True,
        needs_shutdown=True,
        warning=(
            "Vai ser encerrada pelo sistema convidado antes da cópia e fica parada "
            "durante a exportação."
        ),
    )


def resolve_addresses(host: str) -> set[str]:
    """
    PT-PT: Os endereços IP do servidor, para `serves_connection`. Uma falha de
           resolução devolve um conjunto vazio — a comparação pelo nome ainda
           funciona.
    EN-UK: The server's IP addresses, for `serves_connection`. A resolution
           failure returns an empty set — the name comparison still works.
    """
    try:
        _, _, enderecos = socket.gethostbyname_ex(host)
    except OSError:
        return set()
    return set(enderecos)


def safe_name(name: str) -> str:
    """
    PT-PT: Um nome de máquina transformado num nome de pasta que o Windows
           aceite. Nomes de máquinas têm barras, dois pontos e afins com
           frequência; um `/` num nome partia o caminho em dois.
    EN-UK: A machine name turned into a folder name Windows accepts.

    >>> safe_name('SRV/DC01: "prod"')
    'SRV_DC01_ _prod_'
    >>> safe_name("CON")
    '_CON'
    >>> safe_name("  ")
    'maquina'
    """
    limpo = _INVALID.sub("_", name).strip().rstrip(".")
    if not limpo:
        return "maquina"
    if limpo.split(".", 1)[0].upper() in _RESERVED:
        limpo = "_" + limpo
    return limpo[:120]


def estimated_bytes(checks: list[ExportCheck]) -> int:
    """
    PT-PT: Quanto espaço a exportação deve precisar, por cima.

           Usa o espaço que as máquinas ocupam no datastore (`committed`). O
           OVF sai normalmente mais pequeno, porque os discos vêm comprimidos e
           sem os blocos vazios — por isso isto é um tecto, não uma previsão.
    EN-UK: An upper bound on the space needed, from what the machines occupy on
           the datastore. OVF usually comes out smaller, since disks arrive
           compressed without empty blocks — a ceiling, not a forecast.
    """
    return sum(int(c.vm.committed_bytes or 0) for c in checks if c.allowed)


def free_bytes(destination: Path) -> int | None:
    """
    PT-PT: Espaço livre no destino. Funciona também com partilhas UNC
           (`\\\\servidor\\partilha`). `None` quando não se consegue saber.
    EN-UK: Free space at the destination, UNC shares included. `None` when it
           cannot be determined.
    """
    try:
        return shutil.disk_usage(destination).free
    except OSError:
        return None


# ---------------------------------------------------------------------------
# PT-PT: O que se vai reportando à interface.
# EN-UK: What gets reported to the interface.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportEvent:
    """
    PT-PT: Um ponto de situação. `bytes_expected` é a estimativa (o espaço
           ocupado no datastore), não um total exacto — o tamanho real só se
           sabe no fim.
    EN-UK: A progress update. `bytes_expected` is the estimate (datastore
           space), not an exact total — the real size is only known at the end.
    """

    index: int
    vm_name: str
    stage: Stage
    bytes_done: int = 0
    bytes_expected: int = 0
    message: str = ""


@dataclass
class ExportedFile:
    name: str
    size_bytes: int
    sha256: str


@dataclass
class VMExportResult:
    """
    PT-PT: O resultado de uma máquina, tal como vai para o relatório.
    EN-UK: One machine's result, as it goes into the report.
    """

    vm_name: str
    vm_moid: str
    stage: Stage = Stage.QUEUED
    folder: str = ""
    files: list[ExportedFile] = field(default_factory=list)
    started: str = ""
    finished: str = ""
    was_shut_down: bool = False
    powered_back_on: bool = False
    message: str = ""

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)


@dataclass
class BatchResult:
    destination: str
    server: str
    username: str
    started: str
    finished: str = ""
    results: list[VMExportResult] = field(default_factory=list)
    report_path: str = ""

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.stage is Stage.DONE)


class ExportCancelledError(RuntimeError):
    """PT-PT: Alguém carregou em cancelar. / EN-UK: Somebody pressed cancel."""


class ExportError(RuntimeError):
    """PT-PT: Uma falha já explicada em português. / EN-UK: An already-explained failure."""


# ---------------------------------------------------------------------------
# PT-PT: A execução.
# EN-UK: The execution.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportJob:
    """
    PT-PT: Uma máquina a exportar. `power_on_after` só tem efeito numa máquina
           que esta aplicação encerrou: nunca se liga uma que já estava
           desligada.
    EN-UK: One machine to export. `power_on_after` only applies to a machine
           this application shut down: one that was already off is never
           powered on.
    """

    check: ExportCheck
    power_on_after: bool = True


class Exporter:
    """
    PT-PT: Exporta uma lista de máquinas, uma a uma, para uma pasta.

           Corre inteiro numa só thread — a da interface que o chama em
           segundo plano — e fala com o vSphere só por ela, como o resto da
           aplicação. `report` recebe os pontos de situação e `cancel` é
           consultado entre blocos: cancelar aborta a concessão, apaga o que
           estava a meio e, se a máquina foi encerrada por nós e era para
           voltar a ligar, volta a ligá-la.

    EN-UK: Exports a list of machines, one at a time, into a folder. It runs on
           a single thread and talks to vSphere only through it. `report`
           receives progress and `cancel` is checked between chunks: cancelling
           aborts the lease, deletes what was half-written and, if we shut the
           machine down and it was meant to come back, powers it back on.
    """

    def __init__(
        self,
        session: object,
        destination: Path,
        report: Callable[[ExportEvent], None],
        cancel: threading.Event,
        shutdown_timeout: int = DEFAULT_SHUTDOWN_TIMEOUT,
        http_timeout: float = 60.0,
        poll_interval: float = 2.0,
    ) -> None:
        self.session = session
        self.destination = destination
        self.report = report
        self.cancel = cancel
        self.shutdown_timeout = shutdown_timeout
        self.http_timeout = http_timeout
        self.poll_interval = poll_interval

    # -- PT-PT: O lote. / EN-UK: The batch. ----------------------------------

    def run(self, jobs: list[ExportJob]) -> BatchResult:
        """
        PT-PT: Exporta tudo o que a guarda deixou, por ordem, e escreve o
               relatório no destino — também quando foi cancelado ou quando
               alguma falhou, porque é aí que o relatório mais interessa.
        EN-UK: Exports everything the guard allowed, in order, and writes the
               report at the destination — also when cancelled or when one
               failed, because that is when the report matters most.
        """
        endpoint = getattr(self.session, "endpoint", None)
        lote = BatchResult(
            destination=str(self.destination),
            server=str(getattr(endpoint, "host", "")),
            username=str(getattr(endpoint, "username", "")),
            started=_now(),
        )
        self.destination.mkdir(parents=True, exist_ok=True)

        for indice, trabalho in enumerate(jobs):
            vm = trabalho.check.vm
            resultado = VMExportResult(vm_name=vm.name, vm_moid=vm.moid)
            lote.results.append(resultado)

            if self.cancel.is_set():
                resultado.stage = Stage.CANCELLED
                resultado.message = "Cancelada antes de começar."
                self._emit(indice, vm.name, Stage.CANCELLED, 0, 0, resultado.message)
                continue

            if not trabalho.check.allowed:
                resultado.stage = Stage.FAILED
                resultado.message = trabalho.check.reason
                self._emit(indice, vm.name, Stage.FAILED, 0, 0, resultado.message)
                continue

            livre = free_bytes(self.destination)
            if livre is not None and livre < MIN_FREE_BYTES:
                resultado.stage = Stage.FAILED
                resultado.message = (
                    f"Só restam {format_bytes(livre)} livres no destino. A exportação parou "
                    "antes de encerrar mais máquinas."
                )
                self._emit(indice, vm.name, Stage.FAILED, 0, 0, resultado.message)
                break

            if not self._export_one(indice, trabalho, resultado):
                # PT-PT: Sem espaço, as próximas falhavam da mesma maneira — e
                #        algumas seriam encerradas para nada.
                # EN-UK: Out of space, the rest would fail the same way — some
                #        of them shut down for nothing.
                break

        # PT-PT: As que nem chegaram a começar porque o lote parou.
        # EN-UK: The ones that never started because the batch stopped.
        for trabalho in jobs[len(lote.results):]:
            lote.results.append(
                VMExportResult(
                    vm_name=trabalho.check.vm.name,
                    vm_moid=trabalho.check.vm.moid,
                    stage=Stage.CANCELLED,
                    message="Não chegou a começar: o lote parou antes.",
                )
            )

        lote.finished = _now()
        lote.report_path = str(write_report(lote, self.destination))
        return lote

    # -- PT-PT: Uma máquina. / EN-UK: One machine. ---------------------------

    def _export_one(self, indice: int, trabalho: ExportJob, resultado: VMExportResult) -> bool:
        """
        PT-PT: Exporta uma máquina. Devolve se o lote pode continuar — só não
               pode quando acabou o espaço no destino.
        EN-UK: Exports one machine. Returns whether the batch may go on — it may
               not only when the destination ran out of space.
        """
        vm_modelo = trabalho.check.vm
        continuar = True
        esperado = int(vm_modelo.committed_bytes or 0)
        vm = self.session.vm_by_moid(vm_modelo.moid)  # type: ignore[attr-defined]
        resultado.started = _now()
        pasta = self.destination / f"{safe_name(vm_modelo.name)}_{datetime.now():%Y%m%d-%H%M%S}"
        concessao = None

        try:
            # PT-PT: A guarda é verificada outra vez contra o estado vivo: a
            #        lista que a pessoa viu pode ter minutos.
            # EN-UK: The guard is checked again against live state: the list
            #        the person saw may be minutes old.
            estado = str(getattr(getattr(vm, "runtime", None), "powerState", ""))
            if estado == PowerState.ON.value:
                if not trabalho.check.needs_shutdown:
                    raise ExportError(
                        "Foi ligada depois de ter sido escolhida. Não foi encerrada — "
                        "volte a escolhê-la com a opção de encerrar activa."
                    )
                self._emit(indice, vm_modelo.name, Stage.SHUTTING_DOWN, 0, esperado,
                           "Pedido de encerramento enviado às VMware Tools.")
                logger.info("A encerrar %s para exportar", vm_modelo.name)
                vm.ShutdownGuest()
                try:
                    self._wait_powered_off(vm, vm_modelo.name)
                except ExportCancelledError:
                    # PT-PT: O encerramento já foi pedido e não se desfaz: o
                    #        sistema convidado vai acabar de encerrar sozinho.
                    #        Diz-se isso, em vez de fingir que nada aconteceu.
                    # EN-UK: The shutdown was already requested and cannot be
                    #        undone: the guest will finish shutting down on its
                    #        own. That is said, rather than pretending otherwise.
                    raise ExportCancelledError(
                        "Cancelada durante o encerramento. O pedido já tinha sido enviado: "
                        "a máquina vai acabar de encerrar e fica desligada — ligue-a no "
                        "separador Máquinas."
                    ) from None
                resultado.was_shut_down = True
            elif estado != PowerState.OFF.value:
                raise ExportError(f"Estado actual '{estado or 'desconhecido'}': só se exporta desligada.")

            self._emit(indice, vm_modelo.name, Stage.PREPARING, 0, esperado,
                       "A pedir a concessão de exportação ao servidor.")
            concessao = vm.ExportVm()
            self._wait_lease_ready(concessao)

            pasta.mkdir(parents=True, exist_ok=False)
            resultado.folder = str(pasta)
            ficheiros_ovf = self._download_all(indice, vm_modelo, concessao, pasta, esperado, resultado)

            self._emit(indice, vm_modelo.name, Stage.DESCRIBING, resultado.total_bytes, esperado,
                       "A escrever o descritor OVF e o manifesto.")
            self._write_descriptor(vm, vm_modelo, ficheiros_ovf, pasta, resultado)

            _lease_call(concessao, "HttpNfcLeaseProgress", 100)
            concessao.HttpNfcLeaseComplete()
            concessao = None
            write_readme(pasta, vm_modelo, resultado, self.session)

            resultado.stage = Stage.DONE
            resultado.message = (
                f"{len(resultado.files)} ficheiro(s), {format_bytes(resultado.total_bytes)}."
            )
            logger.info("Exportada %s para %s", vm_modelo.name, pasta)
        except ExportCancelledError as erro:
            resultado.stage = Stage.CANCELLED
            resultado.message = str(erro) or "Cancelada. O que estava a meio foi apagado."
        except ExportError as erro:
            resultado.stage = Stage.FAILED
            resultado.message = str(erro)
        except VSphereConnectionError as erro:
            resultado.stage = Stage.FAILED
            resultado.message = str(erro)
        except OSError as erro:
            resultado.stage = Stage.FAILED
            if erro.errno == errno.ENOSPC:
                resultado.message = "Acabou o espaço no destino a meio da cópia."
                continuar = False
            else:
                resultado.message = f"Falha a escrever no destino: {erro}"
        except Exception as erro:  # noqa: BLE001
            logger.exception("Falha a exportar %s", vm_modelo.name)
            resultado.stage = Stage.FAILED
            resultado.message = explain_failure(erro)
        finally:
            if concessao is not None:
                _abort_lease(concessao)
            if resultado.stage is not Stage.DONE and pasta.exists():
                shutil.rmtree(pasta, ignore_errors=True)
                resultado.folder = ""
                resultado.files = []
            if resultado.was_shut_down and trabalho.power_on_after:
                self._power_back_on(indice, vm, vm_modelo, resultado)
            resultado.finished = _now()
            self._emit(indice, vm_modelo.name, resultado.stage, resultado.total_bytes, esperado,
                       resultado.message)
        return continuar

    # -- PT-PT: Alimentação. / EN-UK: Power. ---------------------------------

    def _wait_powered_off(self, vm: object, nome: str) -> None:
        """
        PT-PT: Espera que o sistema convidado acabe de encerrar. Ao fim do
               prazo **não força nada**: diz que não encerrou e deixa-a como
               está, que é ligada ou a acabar de encerrar.
        EN-UK: Waits for the guest to finish shutting down. When the time runs
               out it **forces nothing**: it says so and leaves the machine be.
        """
        limite = time.monotonic() + self.shutdown_timeout
        while time.monotonic() < limite:
            if str(getattr(getattr(vm, "runtime", None), "powerState", "")) == PowerState.OFF.value:
                return
            if self.cancel.wait(self.poll_interval):
                raise ExportCancelledError()
        raise ExportError(
            f"{nome} não encerrou em {self.shutdown_timeout // 60} min. Não foi desligada à "
            "força: veja na consola o que a está a prender."
        )

    def _power_back_on(self, indice: int, vm: object, modelo: VMInfo, resultado: VMExportResult) -> None:
        """
        PT-PT: Volta a ligar a máquina que esta aplicação encerrou. Corre
               também depois de uma falha ou de um cancelamento: a cópia pode
               ter corrido mal, mas a máquina não tem de ficar parada por isso.
        EN-UK: Powers back on the machine this application shut down. It runs
               after a failure or a cancel too: the copy may have gone wrong,
               but the machine need not stay down because of it.
        """
        self._emit(indice, modelo.name, Stage.POWERING_ON, resultado.total_bytes,
                   int(modelo.committed_bytes or 0), "A voltar a ligar a máquina.")
        try:
            tarefa = vm.PowerOnVM_Task()  # type: ignore[attr-defined]
            _wait_task(tarefa, POWER_ON_TIMEOUT, self.poll_interval)
            resultado.powered_back_on = True
            logger.info("%s voltou a ser ligada", modelo.name)
        except Exception as erro:  # noqa: BLE001
            logger.error("Não foi possível voltar a ligar %s: %s", modelo.name, erro)
            resultado.message = (
                (resultado.message + " " if resultado.message else "")
                + f"ATENÇÃO: não foi possível voltar a ligar a máquina — {explain_failure(erro)}"
            )

    # -- PT-PT: A concessão. / EN-UK: The lease. -----------------------------

    def _wait_lease_ready(self, concessao: object) -> None:
        limite = time.monotonic() + LEASE_READY_TIMEOUT
        while time.monotonic() < limite:
            estado = str(getattr(concessao, "state", ""))
            if estado == "ready":
                return
            if estado == "error":
                causa = getattr(concessao, "error", None)
                raise ExportError(
                    "O servidor recusou preparar a exportação: "
                    + (explain_failure(causa) if isinstance(causa, BaseException) else str(causa))
                )
            if self.cancel.wait(0.5):
                raise ExportCancelledError()
        raise ExportError("O servidor não preparou a exportação a tempo.")

    def _download_all(
        self,
        indice: int,
        modelo: VMInfo,
        concessao: object,
        pasta: Path,
        esperado: int,
        resultado: VMExportResult,
    ) -> list[tuple[str, str, int]]:
        """
        PT-PT: Descarrega cada ficheiro da concessão. Devolve, por ficheiro, o
               trio que o `CreateDescriptor` precisa: a chave do dispositivo, o
               nome com que ficou na pasta, e o tamanho real.

               Só se descarregam as entradas com `targetId` — são as que o
               vSphere quer no OVF (os discos e, desde a 6.7, a NVRAM). As
               outras são imagens de CD ou afins que não fazem parte da cópia.

        EN-UK: Downloads each file in the lease, returning for each the triple
               `CreateDescriptor` needs. Only entries with a `targetId` are
               fetched — the ones vSphere wants in the OVF (disks and, since
               6.7, NVRAM).
        """
        info = getattr(concessao, "info", None)
        dispositivos = [d for d in (getattr(info, "deviceUrl", None) or []) if getattr(d, "targetId", None)]
        if not dispositivos:
            raise ExportError("O servidor não devolveu nenhum disco para exportar.")

        prazo = int(getattr(info, "leaseTimeout", 0) or 0)
        manter_viva = max(5.0, min(30.0, prazo / 3 if prazo else 30.0))
        base = safe_name(modelo.name)
        saida: list[tuple[str, str, int]] = []
        relogio = _Throttle(manter_viva)

        for dispositivo in dispositivos:
            alvo = str(dispositivo.targetId)
            nome = alvo if alvo.casefold().startswith(base.casefold()) else f"{base}-{alvo}"
            nome = safe_name(nome)
            url = self._resolve_url(str(dispositivo.url))
            tamanho, resumo = self._download(
                indice, modelo.name, concessao, url, str(getattr(dispositivo, "sslThumbprint", "") or ""),
                pasta / nome, resultado.total_bytes, esperado, relogio,
            )
            resultado.files.append(ExportedFile(name=nome, size_bytes=tamanho, sha256=resumo))
            saida.append((str(dispositivo.key), nome, tamanho))
        return saida

    def _resolve_url(self, url: str) -> str:
        """
        PT-PT: Numa ligação directa ao ESXi, o endereço vem com `*` no lugar do
               anfitrião — o servidor não sabe por que nome ou endereço o
               estamos a ver. Põe-se o da sessão.
        EN-UK: On a direct ESXi connection the URL carries `*` for the host —
               the server does not know which name we reach it by. The
               session's goes in.
        """
        if "://*" not in url:
            return url
        endpoint = self.session.endpoint  # type: ignore[attr-defined]
        anfitriao = endpoint.host
        if ":" in anfitriao and not anfitriao.startswith("["):
            anfitriao = f"[{anfitriao}]"
        # PT-PT: O mesmo servidor, pela mesma porta da sessão — que só não é a
        #        443 quando há um reencaminhamento pelo meio.
        # EN-UK: Same server, same port as the session — only not 443 when a
        #        port forward sits in between.
        porta = getattr(endpoint, "port", 443) or 443
        if porta != 443 and url.startswith("https://*/"):
            anfitriao = f"{anfitriao}:{porta}"
        return url.replace("://*", f"://{anfitriao}", 1)

    def _download(
        self,
        indice: int,
        nome_vm: str,
        concessao: object,
        url: str,
        impressao_sha1: str,
        destino: Path,
        ja_feito: int,
        esperado: int,
        relogio: _Throttle,
    ) -> tuple[int, str]:
        """
        PT-PT: Um ficheiro, em blocos, com o SHA-256 calculado pelo caminho.

               Escreve para `.part` e só renomeia no fim: um ficheiro com o
               nome final está, por definição, completo.

               O `ProxyHandler({})` é deliberado. Se esta máquina tiver um proxy
               definido no ambiente, o `urllib` usava-o — e mandava a sessão do
               vSphere e os discos das máquinas por um intermediário. Esta
               transferência vai directa ao anfitrião, como a ligação principal.

        EN-UK: One file, in chunks, hashing on the way. Writes to `.part` and
               renames at the end: a file with its final name is, by
               definition, complete. `ProxyHandler({})` is deliberate: an
               environment proxy would otherwise carry the vSphere session and
               the machines' disks through a middleman.
        """
        partes = urllib.parse.urlsplit(url)
        anfitriao = partes.hostname or ""
        porta = partes.port or 443
        contexto = transfer_context(self.session, anfitriao, porta, impressao_sha1)  # type: ignore[arg-type]
        abridor = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=contexto)
        )
        pedido = urllib.request.Request(  # noqa: S310 - https, validado acima
            url,
            headers={
                "Cookie": self.session.cookie_header(),  # type: ignore[attr-defined]
                "Accept": "application/x-vnd.vmware-streamVmdk",
            },
        )
        logger.info("A descarregar %s de %s", destino.name, anfitriao)

        temporario = destino.with_name(destino.name + ".part")
        resumo = hashlib.sha256()
        feito = 0
        ultimo = 0.0
        try:
            with abridor.open(pedido, timeout=self.http_timeout) as resposta, temporario.open("wb") as saida:
                while True:
                    if self.cancel.is_set():
                        raise ExportCancelledError()
                    try:
                        bloco = resposta.read(CHUNK_BYTES)
                    except OSError as erro:
                        # PT-PT: Uma falha a *ler* é da rede, não do destino.
                        # EN-UK: A failure *reading* is the network's, not the
                        #        destination's.
                        raise ExportError(
                            f"A transferência de {destino.name} foi interrompida: {erro}"
                        ) from erro
                    if not bloco:
                        break
                    saida.write(bloco)
                    resumo.update(bloco)
                    feito += len(bloco)
                    agora = time.monotonic()
                    if agora - ultimo >= PROGRESS_INTERVAL:
                        ultimo = agora
                        self._emit(indice, nome_vm, Stage.DOWNLOADING, ja_feito + feito, esperado, destino.name)
                    if relogio.due():
                        percentagem = int(min(99, 100 * (ja_feito + feito) / esperado)) if esperado else 50
                        _lease_call(concessao, "HttpNfcLeaseProgress", percentagem)
        except urllib.error.HTTPError as erro:
            raise ExportError(f"O anfitrião recusou o ficheiro {destino.name}: HTTP {erro.code}.") from erro
        except urllib.error.URLError as erro:
            razao = getattr(erro, "reason", erro)
            if isinstance(razao, OSError) and getattr(razao, "errno", None) == errno.ENOSPC:
                raise razao from erro
            raise ExportError(f"A transferência de {destino.name} falhou: {razao}") from erro
        temporario.replace(destino)
        self._emit(indice, nome_vm, Stage.DOWNLOADING, ja_feito + feito, esperado, destino.name)
        return feito, resumo.hexdigest()

    # -- PT-PT: O descritor. / EN-UK: The descriptor. ------------------------

    def _write_descriptor(
        self,
        vm: object,
        modelo: VMInfo,
        ficheiros: list[tuple[str, str, int]],
        pasta: Path,
        resultado: VMExportResult,
    ) -> None:
        """
        PT-PT: Pede ao servidor o `.ovf` e escreve o manifesto.

               Não se passa `description`: no vSphere esse campo substitui as
               notas da máquina no OVF, e uma cópia de segurança não muda o que
               copia.

        EN-UK: Asks the server for the `.ovf` and writes the manifest.
               `description` is not passed: in vSphere it replaces the machine's
               notes in the OVF, and a backup does not alter what it copies.
        """
        from pyVmomi import vim  # noqa: PLC0415

        parametros = vim.OvfManager.CreateDescriptorParams(
            name=modelo.name,
            ovfFiles=[
                vim.OvfManager.OvfFile(deviceId=chave, path=nome, size=tamanho)
                for chave, nome, tamanho in ficheiros
            ],
        )
        gestor = self.session.content.ovfManager  # type: ignore[attr-defined]
        descricao = gestor.CreateDescriptor(obj=vm, cdp=parametros)
        erros = list(getattr(descricao, "error", None) or [])
        if erros:
            raise ExportError(
                "O servidor não conseguiu descrever a máquina: "
                + "; ".join(explain_failure(e) for e in erros)
            )

        base = safe_name(modelo.name)
        ovf = pasta / f"{base}.ovf"
        conteudo = str(descricao.ovfDescriptor).encode("utf-8")
        ovf.write_bytes(conteudo)
        resultado.files.insert(
            0, ExportedFile(name=ovf.name, size_bytes=len(conteudo), sha256=hashlib.sha256(conteudo).hexdigest())
        )

        # PT-PT: O formato do manifesto é o que o vSphere lê: uma linha por
        #        ficheiro, `SHA256(nome)= resumo`. Nada mais — uma linha a mais
        #        e a importação recusa o manifesto.
        # EN-UK: The manifest format is what vSphere reads: one line per file,
        #        `SHA256(name)= digest`. Nothing else — one extra line and the
        #        import rejects the manifest.
        linhas = [f"SHA256({f.name})= {f.sha256}" for f in resultado.files]
        (pasta / f"{base}.mf").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    # -- PT-PT: Utilidades. / EN-UK: Helpers. --------------------------------

    def _emit(
        self, indice: int, nome: str, etapa: Stage, feito: int = 0, esperado: int = 0, mensagem: str = ""
    ) -> None:
        try:
            self.report(ExportEvent(indice, nome, etapa, feito, esperado, mensagem))
        except Exception as erro:  # noqa: BLE001
            logger.debug("Falha a reportar o progresso: %s", erro)


class _Throttle:
    """PT-PT: Diz quando passou o intervalo. / EN-UK: Says when the interval has passed."""

    def __init__(self, intervalo: float) -> None:
        self.intervalo = intervalo
        self._ultimo = time.monotonic()

    def due(self) -> bool:
        agora = time.monotonic()
        if agora - self._ultimo >= self.intervalo:
            self._ultimo = agora
            return True
        return False


def _lease_call(concessao: object, metodo: str, percentagem: int) -> None:
    """
    PT-PT: Mantém a concessão viva. Uma falha aqui fica no registo mas não
           pára a cópia: se a concessão tiver mesmo expirado, a transferência
           seguinte falha por si, com uma mensagem melhor.
    EN-UK: Keeps the lease alive. A failure is logged but does not stop the
           copy: if the lease really expired, the next transfer fails on its
           own, with a better message.
    """
    try:
        getattr(concessao, metodo)(percent=percentagem)
    except Exception as erro:  # noqa: BLE001
        logger.warning("Falha a manter a concessão viva: %s", erro)


def _abort_lease(concessao: object) -> None:
    try:
        concessao.HttpNfcLeaseAbort()  # type: ignore[attr-defined]
    except Exception as erro:  # noqa: BLE001
        logger.debug("Falha a abortar a concessão: %s", erro)


def _wait_task(tarefa: object, prazo: float, intervalo: float) -> None:
    """PT-PT: Espera por uma tarefa do vSphere. / EN-UK: Waits for a vSphere task."""
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        info = getattr(tarefa, "info", None)
        estado = str(getattr(info, "state", ""))
        if estado == "success":
            return
        if estado == "error":
            causa = getattr(info, "error", None)
            if isinstance(causa, BaseException):
                raise causa
            raise ExportError(str(causa or "a tarefa falhou"))
        time.sleep(intervalo)
    raise ExportError("A tarefa não terminou a tempo.")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# PT-PT: O que fica escrito ao lado das cópias.
# EN-UK: What gets written next to the copies.
# ---------------------------------------------------------------------------


def write_readme(pasta: Path, modelo: VMInfo, resultado: VMExportResult, session: object) -> None:
    """
    PT-PT: Um `LEIA-ME.txt` dentro da pasta de cada máquina, para quem a
           encontrar daqui a seis meses saber o que é, de onde veio, e como se
           volta a pôr de pé. Não faz parte do OVF e o vSphere ignora-o.
    EN-UK: A `LEIA-ME.txt` in each machine's folder, so whoever finds it in six
           months knows what it is, where it came from and how to restore it.
           It is not part of the OVF and vSphere ignores it.
    """
    endpoint = getattr(session, "endpoint", None)
    linhas = [
        f"{branding.APP_NAME} {__version__} — exportação OVF",
        "",
        f"Máquina:        {modelo.name}",
        f"Sistema:        {modelo.guest_os or '(desconhecido)'}",
        f"CPU / memória:  {modelo.cpu_count} vCPU, {modelo.memory_mb} MB",
        f"Anfitrião:      {modelo.host_name or '(desconhecido)'}",
        f"Servidor:       {getattr(endpoint, 'host', '')}",
        f"Exportada em:   {resultado.started}",
        f"Encerrada para a cópia: {'sim' if resultado.was_shut_down else 'não (já estava desligada)'}",
        "",
        "Ficheiros (SHA-256):",
        *(f"  {f.sha256}  {f.name}  ({format_bytes(f.size_bytes)})" for f in resultado.files),
        "",
        "Para restaurar: no vSphere Client, 'Deploy OVF Template', e escolher o .ovf,",
        "os .vmdk e o .mf desta pasta. O manifesto (.mf) é verificado na importação.",
        "",
        branding.CREDIT,
    ]
    (pasta / "LEIA-ME.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def write_report(lote: BatchResult, destino: Path) -> Path:
    """
    PT-PT: O relatório do lote, em JSON (para máquinas) e em texto (para
           pessoas), na raiz do destino. Devolve o caminho do de texto.
    EN-UK: The batch report, as JSON (for machines) and text (for people), at
           the destination root. Returns the text one's path.
    """
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    dados = {
        "aplicacao": f"{branding.APP_NAME} {__version__}",
        "gerado_por": branding.CREDIT,
        "servidor": lote.server,
        "utilizador": lote.username,
        "inicio": lote.started,
        "fim": lote.finished,
        "destino": lote.destination,
        "maquinas": [
            {
                **{k: v for k, v in asdict(r).items() if k not in ("stage", "files")},
                "estado": r.stage.label,
                "ficheiros": [asdict(f) for f in r.files],
                "total_bytes": r.total_bytes,
            }
            for r in lote.results
        ],
    }
    json_path = destino / f"exportacao-{carimbo}.json"
    json_path.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")

    linhas = [
        f"{branding.APP_NAME} {__version__} — relatório de exportação",
        f"Servidor: {lote.server}   Utilizador: {lote.username}",
        f"Início: {lote.started}   Fim: {lote.finished}",
        f"Destino: {lote.destination}",
        f"Concluídas: {lote.succeeded} de {len(lote.results)}",
        "",
    ]
    for r in lote.results:
        linhas.append(f"[{r.stage.label.upper():^10}] {r.vm_name}")
        if r.message:
            linhas.append(f"             {r.message}")
        if r.folder:
            linhas.append(f"             {r.folder}")
        if r.was_shut_down:
            linhas.append(
                "             Encerrada para a cópia; "
                + ("voltou a ser ligada." if r.powered_back_on else "ficou desligada.")
            )
    linhas += ["", branding.CREDIT]
    texto_path = destino / f"exportacao-{carimbo}.txt"
    texto_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return texto_path
