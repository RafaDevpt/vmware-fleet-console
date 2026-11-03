#!/usr/bin/env python3
"""
PT-PT: A ligação ao vCenter ou ao anfitrião ESXi, e a questão do certificado.

       **O problema, dito como ele é.** Praticamente todos os ESXi e vCenter do
       mundo apresentam um certificado auto-assinado, porque é o que vem de
       fábrica e substituí-lo por um de uma autoridade a sério dá trabalho. O
       resultado é que toda a gente que escreve automação para vSphere acaba,
       mais cedo ou mais tarde, a escrever a linha que desliga a verificação:

           contexto.verify_mode = ssl.CERT_NONE

       E a partir dessa linha a ligação está cifrada mas não está autenticada:
       qualquer coisa entre a estação e o servidor pode apresentar-se como o
       servidor e receber a senha de administrador do vSphere em texto limpo do
       outro lado do túnel. Não é um risco teórico numa rede de gestão que passa
       pelos mesmos switches que o resto.

       **O que se faz aqui em vez disso.** Confiança na primeira utilização, que
       é o modelo do SSH e funciona pela mesma razão:

       1. Tenta-se validar o certificado como se fosse um certificado normal. Se
          o parque tiver uma autoridade interna instalada na máquina, isto passa
          e não há mais nada a discutir.
       2. Se não validar, **não se liga**. Mostra-se a impressão digital SHA-256
          do certificado e pede-se que a compare com a que o servidor mostra
          (na consola do ESXi, em DCUI, ou em Administration > Certificates no
          vCenter). Ninguém decide por si.
       3. Aceite uma vez, a impressão digital fica guardada. Nas ligações
          seguintes é comparada, e **uma impressão digital diferente pára a
          ligação** com um aviso — que é exactamente o momento em que se quer
          ser interrompido.

       A diferença prática entre isto e `CERT_NONE` é que aqui há uma janela de
       exposição (a primeira ligação) em vez de uma permanente, e uma
       substituição de certificado é notada em vez de passar despercebida.

       O certificado do ESXi muda quando se lhe muda o nome ou se regenera —
       nessa altura a aplicação avisa e a impressão digital tem de ser aceite de
       novo. É chato uma vez por ano e é o comportamento certo.

EN-UK: The connection to vCenter or an ESXi host, and the certificate question.

       Nearly every ESXi and vCenter presents a self-signed certificate, and so
       nearly everybody writing vSphere automation ends up writing the line that
       switches verification off. Past that line the connection is encrypted but
       not authenticated: anything sitting between the workstation and the
       server can present itself as the server and take a vSphere administrator
       password in clear text out of the far end of the tunnel.

       What happens here instead is trust on first use, the SSH model: normal
       validation is tried first; if it fails the connection **stops**, the
       SHA-256 fingerprint is shown to be compared against what the server
       displays, and once accepted it is pinned. A changed fingerprint stops the
       connection — which is exactly when you want to be interrupted.

Created by Redfox using Claude
"""

from __future__ import annotations

import hashlib
import logging
import socket
import ssl
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

DEFAULT_PORT = 443


class TrustDecision(str, Enum):
    """
    PT-PT: Como correu a verificação do certificado.
    EN-UK: How the certificate check went.
    """

    VALID_CHAIN = "cadeia-valida"
    PINNED_MATCH = "impressao-conhecida"
    UNKNOWN_CERTIFICATE = "certificado-desconhecido"
    FINGERPRINT_CHANGED = "impressao-mudou"
    UNREACHABLE = "inacessivel"


@dataclass(frozen=True)
class CertificateInfo:
    """
    PT-PT: O que se conseguiu saber do certificado do servidor.
    EN-UK: What could be learned about the server's certificate.
    """

    fingerprint_sha256: str = ""
    subject: str = ""
    issuer: str = ""
    not_after: str = ""
    self_signed: bool = False

    @property
    def short_fingerprint(self) -> str:
        """
        PT-PT: Os primeiros e os últimos grupos, para caber num cabeçalho.
               Nunca para comparar — comparar é sempre com a completa.
        EN-UK: First and last groups, to fit in a header. Never for comparing —
               comparing is always against the full one.
        """
        if not self.fingerprint_sha256:
            return "--"
        partes = self.fingerprint_sha256.split(":")
        if len(partes) <= 6:
            return self.fingerprint_sha256
        return ":".join(partes[:3]) + " ... " + ":".join(partes[-3:])


@dataclass(frozen=True)
class TrustResult:
    """
    PT-PT: A decisão sobre o certificado, e o que dizer a quem está a ver.
    EN-UK: The decision about the certificate, and what to tell whoever is
           looking.
    """

    decision: TrustDecision
    certificate: CertificateInfo
    message: str = ""

    @property
    def may_connect(self) -> bool:
        """
        PT-PT: Se se pode prosseguir sem perguntar nada.
        EN-UK: Whether the connection may proceed without asking anything.
        """
        return self.decision in (TrustDecision.VALID_CHAIN, TrustDecision.PINNED_MATCH)

    @property
    def needs_decision(self) -> bool:
        """
        PT-PT: Se é preciso alguém olhar para a impressão digital e decidir.
        EN-UK: Whether somebody needs to look at the fingerprint and decide.
        """
        return self.decision in (
            TrustDecision.UNKNOWN_CERTIFICATE,
            TrustDecision.FINGERPRINT_CHANGED,
        )


def fingerprint_of(der_bytes: bytes) -> str:
    """
    PT-PT: A impressão digital SHA-256 no formato em que o vSphere a mostra —
           grupos de dois dígitos hexadecimais separados por dois pontos, em
           maiúsculas. O formato importa: é para ser comparada à vista com o que
           está no ecrã do servidor, e dois formatos diferentes obrigam a
           traduzir de cabeça, que é onde se erra.

    EN-UK: The SHA-256 fingerprint in the format vSphere displays — colon-
           separated uppercase hex pairs. The format matters: it is meant to be
           compared by eye against the server's screen, and two different
           formats force a mental translation, which is where mistakes happen.

    >>> fingerprint_of(b"")[:5]
    'E3:B0'
    """
    digest = hashlib.sha256(der_bytes).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def _fetch_der(host: str, port: int, timeout: float) -> bytes:
    """
    PT-PT: Os bytes do certificado apresentado, sem o validar.

           Há dois sítios que precisam dos mesmos bytes: `fetch_certificate`,
           para mostrar a impressão digital a quem decide, e `_build_context`,
           para a impor no aperto de mão.

    EN-UK: The bytes of the presented certificate, without validating it. Two
           places need the same bytes: `fetch_certificate`, to show the
           fingerprint to whoever decides, and `_build_context`, to enforce it
           in the handshake.
    """
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    # PT-PT: auditor: ignorar -- o CERT_NONE aqui e deliberado e esta isolado.
    #        Esta ligacao existe **so** para ir buscar o certificado que vai ser
    #        comparado com a impressao digital fixada; nao passa por ela dado
    #        nenhum. A verificacao a serio esta em _build_context(), que entrega
    #        este certificado ao OpenSSL como unica ancora, com CERT_REQUIRED.
    #        Trocar isto por CERT_REQUIRED nao aumenta a seguranca: impede
    #        simplesmente que o certificado seja obtido.
    # EN-UK: auditor: ignorar -- the CERT_NONE here is deliberate and isolated.
    #        This connection exists **only** to fetch the certificate that will
    #        be compared against the pinned fingerprint; no data passes over it.
    #        The real verification is in _build_context(), which hands this
    #        certificate to OpenSSL as the sole anchor with CERT_REQUIRED.
    #        Changing this to CERT_REQUIRED would not add security: it would
    #        merely prevent the certificate from being fetched at all.
    contexto.verify_mode = ssl.CERT_NONE

    with (
        socket.create_connection((host, port), timeout=timeout) as bruto,
        contexto.wrap_socket(bruto, server_hostname=host) as seguro,
    ):
        return seguro.getpeercert(binary_form=True) or b""


# PT-PT: Os atributos de nome que aparecem nos certificados de ESXi e vCenter.
# EN-UK: The name attributes found in ESXi and vCenter certificates.
_NAME_OIDS = {
    bytes.fromhex("550403"): "CN",
    bytes.fromhex("55040a"): "O",
    bytes.fromhex("55040b"): "OU",
    bytes.fromhex("550406"): "C",
    bytes.fromhex("550407"): "L",
    bytes.fromhex("550408"): "ST",
    bytes.fromhex("0992268993f22c640119"): "DC",
    bytes.fromhex("2a864886f70d010901"): "E",
}


def _tlv(dados: bytes, posicao: int) -> tuple[int, int, int]:
    """PT-PT: Uma etiqueta DER: (tipo, início, fim do valor). / EN-UK: One DER TLV."""
    etiqueta = dados[posicao]
    tamanho = dados[posicao + 1]
    inicio = posicao + 2
    if tamanho & 0x80:
        octetos = tamanho & 0x7F
        tamanho = int.from_bytes(dados[inicio : inicio + octetos], "big")
        inicio += octetos
    fim = inicio + tamanho
    if fim > len(dados):
        raise ValueError("DER truncado")
    return etiqueta, inicio, fim


def _children(dados: bytes, inicio: int, fim: int) -> list[tuple[int, int, int]]:
    filhos = []
    while inicio < fim:
        etiqueta, a, b = _tlv(dados, inicio)
        filhos.append((etiqueta, a, b))
        inicio = b
    return filhos


def _name(dados: bytes, inicio: int, fim: int) -> str:
    partes = []
    for _, a, b in _children(dados, inicio, fim):  # cada SET
        for _, c, d in _children(dados, a, b):  # cada SEQUENCE {OID, valor}
            campos = _children(dados, c, d)
            if len(campos) != 2:
                continue
            (_, oa, ob), (tipo, va, vb) = campos
            valor = dados[va:vb]
            texto = valor.decode("utf-16-be" if tipo == 0x1E else "utf-8", errors="replace")
            partes.append(f"{_NAME_OIDS.get(dados[oa:ob], 'OID')}={texto}")
    return ", ".join(partes)


def describe_der(der: bytes) -> tuple[str, str, str]:
    """
    PT-PT: O sujeito, o emissor e a validade de um certificado, lidos do DER.

           **A correcção da 2.0.** A 1.0 pedia estes campos ao `getpeercert()`,
           que só os devolve quando o certificado foi *validado* — e o
           certificado que interessa mostrar é precisamente o que não valida.
           O diálogo saía sempre com os três campos vazios. Agora lêem-se do
           próprio certificado, só para mostrar: quem decide continua a ser a
           impressão digital.

    EN-UK: Subject, issuer and expiry, read from the DER. **The 2.0 fix**: 1.0
           asked `getpeercert()`, which only returns them for a *validated*
           certificate — and the one worth showing is precisely the one that
           does not validate, so the dialog always showed three blanks. Display
           only: the fingerprint still decides.
    """
    try:
        _, a, b = _tlv(der, 0)
        _, ta, tb = _children(der, a, b)[0]
        campos = _children(der, ta, tb)
        if campos and campos[0][0] == 0xA0:
            campos = campos[1:]
        # PT-PT: série, algoritmo, emissor, validade, sujeito.
        # EN-UK: serial, algorithm, issuer, validity, subject.
        _, _, emissor, validade, sujeito = campos[:5]
        fim_validade = _children(der, validade[1], validade[2])[1]
        bruto = der[fim_validade[1] : fim_validade[2]].decode("ascii")
        if fim_validade[0] == 0x17:  # UTCTime, AAMMDD
            ano = int(bruto[:2])
            bruto = ("19" if ano >= 50 else "20") + bruto
        validade_texto = f"{bruto[:4]}-{bruto[4:6]}-{bruto[6:8]} {bruto[8:10]}:{bruto[10:12]} UTC"
        return _name(der, sujeito[1], sujeito[2]), _name(der, emissor[1], emissor[2]), validade_texto
    except (IndexError, ValueError, UnicodeDecodeError):
        return "", "", ""


def fetch_certificate(host: str, port: int = DEFAULT_PORT, timeout: float = 10.0) -> CertificateInfo:
    """
    PT-PT: Vai buscar o certificado sem o validar, só para o poder mostrar.

           Isto usa um contexto sem verificação de propósito, e é o único sítio
           do programa onde isso acontece — **não** é por aqui que passam
           credenciais nenhumas. O objectivo é obter os bytes do certificado
           para calcular a impressão digital que a pessoa vai comparar. A
           autenticação faz-se depois, noutra ligação, já com a decisão tomada.

    EN-UK: Fetches the certificate without validating it, purely to be able to
           show it. This uses an unverified context on purpose, and it is the
           only place in the program that does — **no credentials travel here**.
           Authentication happens afterwards, on another connection, with the
           decision already made.
    """
    der = _fetch_der(host, port, timeout)
    if not der:
        return CertificateInfo()
    sujeito, emissor, validade = describe_der(der)
    return CertificateInfo(
        fingerprint_sha256=fingerprint_of(der),
        subject=sujeito,
        issuer=emissor,
        not_after=validade,
        self_signed=bool(sujeito) and sujeito == emissor,
    )


def evaluate_trust(
    host: str,
    port: int = DEFAULT_PORT,
    pinned_fingerprint: str = "",
    timeout: float = 10.0,
) -> TrustResult:
    """
    PT-PT: Decide se se pode ligar, e porquê.

           A ordem das perguntas é a ordem em que elas importam:

           1. A cadeia valida? Então acabou, e nem sequer se olha para a
              impressão digital guardada.
           2. Não valida. Já tínhamos uma impressão digital guardada?
              - Igual: prossegue-se. É o servidor de sempre.
              - **Diferente: pára.** Ou alguém regenerou o certificado, ou não
                se está a falar com o servidor de sempre. As duas hipóteses
                merecem que alguém olhe.
           3. Nunca vimos este servidor: mostra-se a impressão digital e
              espera-se por uma decisão.

    EN-UK: Decides whether the connection may proceed, and why. Chain first — if
           it validates, the pinned fingerprint is not even consulted. Then the
           pin: a match proceeds, a **mismatch stops**, because either somebody
           regenerated the certificate or this is not the same server, and both
           deserve a human look. A server never seen before gets its fingerprint
           shown and waits for a decision.
    """
    try:
        certificado = fetch_certificate(host, port, timeout)
    except OSError as erro:
        return TrustResult(
            decision=TrustDecision.UNREACHABLE,
            certificate=CertificateInfo(),
            message=f"Não foi possível chegar a {host}:{port} — {erro}",
        )

    if _chain_validates(host, port, timeout):
        return TrustResult(
            decision=TrustDecision.VALID_CHAIN,
            certificate=certificado,
            message="Certificado validado por uma autoridade em que esta máquina confia.",
        )

    guardada = (pinned_fingerprint or "").strip().upper()
    actual = certificado.fingerprint_sha256

    if guardada and actual:
        if guardada == actual:
            return TrustResult(
                decision=TrustDecision.PINNED_MATCH,
                certificate=certificado,
                message="Impressão digital igual à que foi aceite anteriormente.",
            )
        return TrustResult(
            decision=TrustDecision.FINGERPRINT_CHANGED,
            certificate=certificado,
            message=(
                "A IMPRESSÃO DIGITAL DO CERTIFICADO MUDOU.\n"
                f"  Aceite antes: {guardada}\n"
                f"  Agora:        {actual}\n"
                "Isto acontece quando o certificado é regenerado — mas também acontece "
                "quando não se está a falar com o servidor de sempre. Confirme na consola "
                "do servidor antes de aceitar."
            ),
        )

    return TrustResult(
        decision=TrustDecision.UNKNOWN_CERTIFICATE,
        certificate=certificado,
        message=(
            "Certificado que esta máquina não consegue validar — o que é o normal num "
            "ESXi ou vCenter com o certificado de fábrica.\n"
            f"  Impressão digital SHA-256: {actual}\n"
            "Compare-a com a que o servidor mostra antes de aceitar."
        ),
    )


def _chain_validates(host: str, port: int, timeout: float) -> bool:
    """
    PT-PT: Se o certificado passa a validação normal, com as autoridades da
           máquina. Uma excepção aqui é uma resposta — "não valida" — e não um
           erro a propagar.
    EN-UK: Whether the certificate passes normal validation against the
           machine's trust store. An exception here is an answer — "it does not
           validate" — not an error to propagate.
    """
    contexto = ssl.create_default_context()
    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as bruto,
            contexto.wrap_socket(bruto, server_hostname=host),
        ):
            return True
    except ssl.SSLError:
        return False
    except OSError:
        return False


# ---------------------------------------------------------------------------
# PT-PT: A sessão.
# EN-UK: The session.
# ---------------------------------------------------------------------------


class VSphereConnectionError(RuntimeError):
    """
    PT-PT: Falha ao ligar, com a causa já traduzida para linguagem humana.
    EN-UK: Connection failure, with the cause already translated into human
           language.
    """


@dataclass
class Endpoint:
    """
    PT-PT: Onde ligar. Sem senha: a senha entra na chamada e não fica em lado
           nenhum que se possa serializar por engano.
    EN-UK: Where to connect. No password field: the password goes in as a call
           argument and never sits anywhere that could be serialised by mistake.
    """

    host: str
    username: str
    port: int = DEFAULT_PORT
    fingerprint: str = ""


class Session:
    """
    PT-PT: Uma sessão aberta contra um vCenter ou um ESXi.

           Guarda o `ServiceInstance` do pyVmomi e sabe resolver um identificador
           de objecto (o `moid`, que os modelos guardam) de volta para o objecto
           vivo. É essa a ponte entre a parte testável e a parte que fala com o
           servidor.

           Distingue vCenter de ESXi pelo `apiType`, e isso muda o que a
           aplicação pode oferecer: um ESXi sozinho não tem clusters, não tem
           DRS, e — se estiver com a licença gratuita — não aceita **nenhuma**
           operação de escrita pela API, por muito que o utilizador seja
           administrador. Isso é detectado e dito, porque o erro que o servidor
           devolve nesse caso (`RestrictedVersion`) não diz nada a quem o vê
           pela primeira vez.

    EN-UK: An open session against a vCenter or an ESXi host. It holds pyVmomi's
           `ServiceInstance` and can resolve a stored `moid` back to the live
           object — the bridge between the testable half and the half that talks
           to the server.

           It tells vCenter from ESXi by `apiType`, which changes what can be
           offered: a standalone ESXi has no clusters, no DRS, and — on the free
           licence — accepts **no** write operation through the API at all,
           however administrative the user is. That is detected and stated,
           because the server's own error (`RestrictedVersion`) means nothing to
           somebody seeing it for the first time.
    """

    def __init__(
        self,
        service_instance: object,
        endpoint: Endpoint,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.si = service_instance
        self.endpoint = endpoint
        # PT-PT: O contexto com que a sessão foi aberta — o que já tem a
        #        impressão digital aceite. A exportação reutiliza-o para os
        #        discos quando eles vêm do mesmo servidor.
        # EN-UK: The context the session was opened with — the one already
        #        carrying the accepted fingerprint. Export reuses it for the
        #        disks when they come from the same server.
        self.ssl_context = ssl_context or ssl.create_default_context()
        self._content = None

    # -- PT-PT: Identidade do servidor. / EN-UK: Server identity. -----------

    @property
    def content(self) -> object:
        if self._content is None:
            self._content = self.si.RetrieveContent()  # type: ignore[attr-defined]
        return self._content

    @property
    def about(self) -> object:
        return self.content.about  # type: ignore[attr-defined]

    @property
    def is_vcenter(self) -> bool:
        """
        PT-PT: `VirtualCenter` contra `HostAgent`. É o que decide se há clusters
               para percorrer ou se o inventário é um anfitrião só.
        EN-UK: `VirtualCenter` against `HostAgent`. It decides whether there are
               clusters to walk or the inventory is a single host.
        """
        return getattr(self.about, "apiType", "") == "VirtualCenter"

    @property
    def product(self) -> str:
        nome = getattr(self.about, "fullName", "")
        return str(nome)

    def read_only_reason(self) -> str:
        """
        PT-PT: Porque é que este servidor não vai aceitar escritas — se for o
               caso.

               O caso que interessa é o ESXi com a licença gratuita. A API fica
               em leitura, e uma aplicação que ofereça botões de ligar e
               desligar sem dizer isto parece avariada quando eles falham todos.
               Mais vale dizê-lo no cabeçalho, uma vez.

               Devolve texto vazio quando não há impedimento conhecido.

        EN-UK: Why this server will not accept writes — if that is the case. The
               case that matters is a free-licensed ESXi, where the API goes
               read-only: an application offering power buttons without saying
               so looks broken when they all fail. Empty string when there is no
               known impediment.
        """
        licenciamento = getattr(self.content, "licenseManager", None)
        if licenciamento is None:
            return ""
        try:
            licencas = list(getattr(licenciamento, "licenses", []) or [])
        except Exception:  # noqa: BLE001
            return ""
        for licenca in licencas:
            nome = str(getattr(licenca, "editionKey", "")) + str(getattr(licenca, "name", ""))
            if "esxFree" in nome or "Free" in nome:
                return (
                    "Este anfitrião está com a licença gratuita do ESXi. Nessa licença a API "
                    "do vSphere é só de leitura: ligar, desligar, snapshots e manutenção vão "
                    "ser recusados pelo servidor, mesmo com credenciais de administrador. "
                    "A monitorização funciona toda."
                )
        return ""

    # -- PT-PT: Do identificador para o objecto. / EN-UK: Id to object. ------

    def _by_moid(self, kind: str, moid: str) -> object:
        """
        PT-PT: Reconstrói a referência a partir do tipo e do identificador.

               É assim e não por procura no inventário porque a procura seria
               uma travessia inteira por cada botão carregado. O identificador
               é estável enquanto o objecto existir.

        EN-UK: Rebuilds the reference from type and id, rather than searching the
               inventory — a search would be a full traversal per button press.
               The id is stable for as long as the object exists.
        """
        from pyVmomi import vim  # noqa: PLC0415

        tipos = {
            "VirtualMachine": vim.VirtualMachine,
            "HostSystem": vim.HostSystem,
            "Datastore": vim.Datastore,
        }
        if kind not in tipos:
            raise VSphereConnectionError(f"Tipo de objecto desconhecido: {kind}")
        referencia = tipos[kind](moid)
        referencia._stub = self.si._stub  # type: ignore[attr-defined]
        return referencia

    def vm_by_moid(self, moid: str) -> object:
        return self._by_moid("VirtualMachine", moid)

    def host_by_moid(self, moid: str) -> object:
        return self._by_moid("HostSystem", moid)

    def snapshot_by_id(self, vm_moid: str, snapshot_id: int) -> object:
        """
        PT-PT: Encontra o snapshot pela árvore da máquina.

               Um snapshot não tem `moid` próprio — vive dentro da máquina e
               identifica-se por um número dentro dela. Percorre-se a árvore,
               que é pequena por natureza.

        EN-UK: Finds the snapshot through the machine's tree. A snapshot has no
               `moid` of its own: it lives inside the machine and is identified
               by a number within it. The tree is walked, and it is small by
               nature.
        """
        maquina = self.vm_by_moid(vm_moid)
        raiz = getattr(getattr(maquina, "snapshot", None), "rootSnapshotList", None)
        if not raiz:
            raise VSphereConnectionError("Esta máquina já não tem snapshots.")

        def procurar(nos: object) -> object | None:
            for no in nos:  # type: ignore[union-attr]
                if getattr(no, "id", None) == snapshot_id:
                    return no.snapshot
                achado = procurar(getattr(no, "childSnapshotList", []) or [])
                if achado is not None:
                    return achado
            return None

        encontrado = procurar(raiz)
        if encontrado is None:
            raise VSphereConnectionError(
                "O snapshot já não existe. Actualize o inventário — pode ter sido apagado "
                "entretanto, aqui ou noutra consola."
            )
        return encontrado

    def cookie_header(self) -> str:
        """
        PT-PT: O cookie da sessão, no formato do cabeçalho `Cookie`.

               O pyVmomi guarda-o como veio no `Set-Cookie` — com `Path`,
               `HttpOnly` e companhia. Para o enviar só interessa o primeiro par
               `nome=valor`; o resto são atributos para o cliente, não para o
               servidor.

        EN-UK: The session cookie, shaped for the `Cookie` header. pyVmomi keeps
               it as it arrived in `Set-Cookie`, attributes and all; only the
               first `name=value` pair is sent back.

        >>> class _S: cookie = 'vmware_soap_session="52a"; Path=/; HttpOnly; Secure;'
        >>> class _I: _stub = _S()
        >>> Session(_I(), Endpoint("h", "u")).cookie_header()
        'vmware_soap_session="52a"'
        """
        bruto = str(getattr(getattr(self.si, "_stub", None), "cookie", "") or "")
        return bruto.split(";", 1)[0].strip()

    def close(self) -> None:
        """PT-PT: Fecha a sessão no servidor. / EN-UK: Closes the server session."""
        try:
            from pyVim.connect import Disconnect  # noqa: PLC0415

            Disconnect(self.si)
        except Exception as erro:  # noqa: BLE001
            logger.debug("Falha ao fechar a sessão: %s", erro)


def connect(
    endpoint: Endpoint,
    password: str,
    trusted_fingerprint: str = "",
    timeout: float = 30.0,
) -> Session:
    """
    PT-PT: Abre a sessão, com o certificado já decidido.

           O `trusted_fingerprint` é obrigatório na prática: ou o certificado
           valida sozinho, ou tem de vir aqui a impressão digital que alguém
           aceitou. Não há caminho por aqui que ligue sem uma coisa nem outra —
           que é o ponto todo deste módulo.

           As excepções do pyVmomi são traduzidas. `InvalidLogin` chega como
           "vim.fault.InvalidLogin" e não ajuda ninguém; o que ajuda é "as
           credenciais foram recusadas", e a nota de que o vCenter bloqueia a
           conta ao fim de algumas tentativas.

    EN-UK: Opens the session with the certificate question already settled.
           Either the chain validates on its own, or an accepted fingerprint has
           to be passed in — there is no path through here that connects without
           one or the other, which is the entire point of this module.

           pyVmomi's exceptions are translated: "vim.fault.InvalidLogin" helps
           nobody, "the credentials were refused" does — along with the note
           that vCenter locks the account after a few tries.
    """
    try:
        from pyVim.connect import SmartConnect  # noqa: PLC0415
        from pyVmomi import vim  # noqa: PLC0415
    except ImportError as erro:  # pragma: no cover - ambiente sem dependência
        raise VSphereConnectionError(
            "O pyVmomi não está instalado. Sem ele não há ligação nenhuma ao vSphere:\n"
            "    pip install -r requirements.txt"
        ) from erro

    contexto = _build_context(endpoint, trusted_fingerprint, timeout)

    try:
        instancia = SmartConnect(
            host=endpoint.host,
            user=endpoint.username,
            pwd=password,
            port=endpoint.port,
            sslContext=contexto,
            connectionPoolTimeout=int(timeout),
        )
    except vim.fault.InvalidLogin as erro:
        raise VSphereConnectionError(
            "Credenciais recusadas pelo servidor.\n"
            "Confirme o utilizador — no vCenter costuma incluir o domínio, como "
            "administrator@vsphere.local; num ESXi é normalmente root.\n"
            "Atenção: algumas tentativas falhadas seguidas bloqueiam a conta."
        ) from erro
    except vim.fault.NoPermission as erro:
        raise VSphereConnectionError(
            "As credenciais estão certas mas a conta não tem permissões para ler o "
            "inventário."
        ) from erro
    except ssl.SSLCertVerificationError as erro:
        raise VSphereConnectionError(
            f"O certificado do servidor não foi aceite: {erro}.\n"
            "Verifique a impressão digital antes de continuar."
        ) from erro
    except (TimeoutError, OSError) as erro:
        raise VSphereConnectionError(
            f"Não foi possível chegar a {endpoint.host}:{endpoint.port} — {erro}.\n"
            "Confirme o endereço, a porta 443 e se a rede de gestão está acessível daqui."
        ) from erro
    except Exception as erro:  # noqa: BLE001
        raise VSphereConnectionError(f"Falha ao ligar: {erro}") from erro

    if instancia is None:
        raise VSphereConnectionError("O servidor aceitou a ligação mas não devolveu uma sessão.")

    return Session(instancia, endpoint, contexto)


def _build_context(
    endpoint: Endpoint, trusted_fingerprint: str, timeout: float = 10.0
) -> ssl.SSLContext:
    """
    PT-PT: O contexto TLS para a ligação autenticada — a que leva a senha.

           **O que estava errado.** A impressão digital era comparada em
           `evaluate_trust`, que abre uma ligação para ir buscar o certificado.
           Depois `connect` abria **outra** ligação, e era nessa que a senha
           seguia — com `CERT_NONE`, isto é, aceitando qualquer certificado.
           Entre uma ligação e a outra não se voltava a verificar nada. Quem
           estivesse no meio deixava passar a primeira, apresentava o
           certificado que quisesse na segunda, e recebia a senha. A janela é
           pequena mas o módulo inteiro existe para a fechar.

           **O que se faz agora.** A impressão digital passa a ser imposta
           durante o aperto de mão, pelo OpenSSL, e não por nós antes dele: o
           certificado que corresponde à impressão digital aceite é entregue
           como única âncora de confiança (`cadata`), com `CERT_REQUIRED`. Se o
           servidor apresentar outro certificado, o aperto de mão falha e a
           senha não chega a sair. Já não há intervalo entre verificar e usar.

           `check_hostname` continua desligado de propósito: os certificados de
           fábrica do ESXi raramente têm o nome certo, e quem autentica aqui é a
           impressão digital, não o nome.

    EN-UK: The TLS context for the authenticated connection — the one carrying
           the password.

           **What was wrong.** The fingerprint was compared in `evaluate_trust`,
           which opens a connection to fetch the certificate. `connect` then
           opened **another** connection, and that is the one the password
           travelled on — with `CERT_NONE`, accepting any certificate at all.
           Nothing was re-checked in between. Anyone in the middle could let the
           first connection through, present whatever certificate they liked on
           the second, and collect the password. The window is small, but
           closing it is the entire reason this module exists.

           **What happens now.** The pin is enforced during the handshake, by
           OpenSSL, rather than by us beforehand: the certificate matching the
           accepted fingerprint is handed over as the only trust anchor
           (`cadata`), with `CERT_REQUIRED`. If the server presents a different
           certificate the handshake fails and the password never leaves. There
           is no longer a gap between checking and using.

           `check_hostname` stays off deliberately: factory ESXi certificates
           rarely carry the right name, and what authenticates here is the
           fingerprint, not the name.
    """
    if not trusted_fingerprint:
        return ssl.create_default_context()

    esperada = trusted_fingerprint.strip().upper()

    try:
        der = _fetch_der(endpoint.host, endpoint.port, timeout)
    except OSError as erro:
        raise VSphereConnectionError(
            f"Não foi possível chegar a {endpoint.host}:{endpoint.port} — {erro}."
        ) from erro

    if not der:
        raise VSphereConnectionError(
            f"{endpoint.host} não apresentou certificado nenhum."
        )

    actual = fingerprint_of(der)
    if actual != esperada:
        raise VSphereConnectionError(
            "A IMPRESSÃO DIGITAL DO CERTIFICADO MUDOU ENTRETANTO.\n"
            f"  Aceite antes: {esperada}\n"
            f"  Agora:        {actual}\n"
            "A ligação foi interrompida antes de enviar credenciais."
        )

    logger.info(
        "A ligar a %s com a impressão digital aceite %s, imposta no aperto de mão",
        endpoint.host,
        esperada[:17],
    )
    return _anchored_context(der)


def _anchored_context(der: bytes) -> ssl.SSLContext:
    """
    PT-PT: Um contexto TLS que só aceita este certificado exacto.

           **A correcção da 2.0.** Na 1.0 o certificado aceite era carregado
           como âncora, mas sem `VERIFY_X509_PARTIAL_CHAIN`. Com isso o OpenSSL
           insiste em subir a cadeia até uma raiz auto-assinada. Num ESXi com o
           certificado de fábrica não se notava, porque esse certificado é a sua
           própria raiz. Num ESXi gerido por um vCenter o certificado é emitido
           pela VMCA (a autoridade interna do vCenter), não é auto-assinado, e o
           aperto de mão falhava sempre — mesmo depois de alguém ter comparado e
           aceite a impressão digital. Com a flag, o certificado aceite basta
           por si: é exactamente o que "fixar a impressão digital" quer dizer.

    EN-UK: A TLS context that accepts this exact certificate and nothing else.

           **The 2.0 fix.** In 1.0 the accepted certificate was loaded as the
           anchor without `VERIFY_X509_PARTIAL_CHAIN`, so OpenSSL insisted on
           climbing to a self-signed root. A factory ESXi certificate is its own
           root, so nobody noticed. A vCenter-managed ESXi carries a certificate
           issued by the VMCA, which is not self-signed, and the handshake always
           failed — even after the fingerprint had been compared and accepted.
           With the flag, the accepted certificate suffices on its own, which is
           exactly what pinning means.
    """
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_REQUIRED
    contexto.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    # PT-PT: O próprio certificado aceite é a âncora. Nada mais é aceite.
    # EN-UK: The accepted certificate is itself the anchor. Nothing else passes.
    contexto.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(der))
    return contexto


def sha1_fingerprint_of(der_bytes: bytes) -> str:
    """
    PT-PT: A impressão digital SHA-1, no mesmo formato da SHA-256.

           Só existe por uma razão: é o formato em que o vSphere anuncia, na
           concessão de exportação (`HttpNfcLeaseDeviceUrl.sslThumbprint`), o
           certificado do anfitrião de onde os discos vão ser descarregados.
           Não é usada para decidir confiança em nada que a pessoa veja — só
           para confirmar que o anfitrião de transferência é aquele que o
           próprio servidor autenticado disse que era.

    EN-UK: The SHA-1 fingerprint, in the same format as the SHA-256 one. It
           exists for one reason: it is the format vSphere uses, in the export
           lease, to announce the certificate of the host the disks will be
           downloaded from. It decides no trust shown to a person — it only
           confirms the transfer host is the one the authenticated server said.

    >>> sha1_fingerprint_of(b"")[:5]
    'DA:39'
    """
    digest = hashlib.sha1(der_bytes).hexdigest().upper()  # noqa: S324 - formato imposto pelo vSphere
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def transfer_context(
    session: Session,
    host: str,
    port: int = DEFAULT_PORT,
    sha1_thumbprint: str = "",
    timeout: float = 10.0,
) -> ssl.SSLContext:
    """
    PT-PT: O contexto TLS para descarregar os discos de uma exportação.

           A sessão no servidor serve de cookie, por isso este pedido leva
           credenciais e merece a mesma desconfiança que a ligação principal:

           1. **O mesmo servidor** a que a sessão está ligada (é o caso de uma
              ligação directa ao ESXi): reutiliza-se o contexto da sessão, com
              a impressão digital que alguém aceitou.
           2. **Outro anfitrião** (exportar através do vCenter: os discos vêm do
              ESXi onde a máquina está). O vCenter anuncia a impressão digital
              SHA-1 desse anfitrião na concessão, e essa resposta veio pela
              ligação já autenticada. Compara-se o certificado apresentado com
              ela e só depois se envia o cookie.
           3. **Outro anfitrião sem impressão digital anunciada**: só passa se a
              cadeia validar com as autoridades desta máquina. Se não validar,
              pára — e a mensagem diz o que fazer.

    EN-UK: The TLS context for downloading an export's disks. The server
           session travels as a cookie, so this request carries credentials and
           deserves the same distrust as the main connection: the same server
           reuses the session's pinned context; another host (exporting through
           vCenter) is checked against the SHA-1 thumbprint vCenter announced in
           the lease over the already-authenticated connection; another host
           with no announced thumbprint passes only if its chain validates.
    """
    if host.strip().casefold() == session.endpoint.host.strip().casefold():
        return session.ssl_context

    esperada = (sha1_thumbprint or "").strip().upper()
    if esperada:
        try:
            der = _fetch_der(host, port, timeout)
        except OSError as erro:
            raise VSphereConnectionError(
                f"Não foi possível chegar ao anfitrião de transferência {host}:{port} — {erro}.\n"
                "Os discos vêm directamente do ESXi onde a máquina está: este computador "
                "tem de resolver o nome dele e chegar-lhe pela porta 443."
            ) from erro
        actual = sha1_fingerprint_of(der)
        if actual != esperada:
            raise VSphereConnectionError(
                f"O certificado de {host} não é o que o vCenter anunciou para esta "
                "transferência.\n"
                f"  Anunciado: {esperada}\n"
                f"  Recebido:  {actual}\n"
                "A transferência foi interrompida antes de enviar a sessão."
            )
        return _anchored_context(der)

    if _chain_validates(host, port, timeout):
        return ssl.create_default_context()

    raise VSphereConnectionError(
        f"O certificado de {host} não valida neste computador e o servidor não anunciou "
        "a impressão digital dele.\n"
        "Duas saídas: instalar neste computador a autoridade de certificação do vCenter "
        "(https://<vcenter>/certs/download.zip), ou ligar directamente ao ESXi e "
        "exportar a partir daí."
    )
