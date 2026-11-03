#!/usr/bin/env python3
"""
PT-PT: O arranque.

       A primeira coisa que acontece é a verificação da assinatura
       (`branding.verify`). Depois decide-se entre a interface gráfica e o modo
       de texto, com uma regra que vale a pena dizer: **se a janela não puder
       abrir, cai-se no modo de texto em vez de rebentar.** Um servidor sem
       ambiente gráfico, uma sessão SSH, um Python sem Tkinter — em qualquer
       desses casos há uma resposta útil a dar.

       O modo de texto pede a senha com `getpass`, que não a mostra e não a
       deixa no histórico da shell. **Não há opção `--senha`**, e a ausência é
       deliberada: um argumento de linha de comandos fica visível no `ps` para
       qualquer utilizador da máquina e fica escrito no `~/.bash_history`. Para
       automação existe a variável `VFC_PASSWORD`, que também não é perfeita mas
       não fica na lista de processos — e a documentação diz o que ela é.

EN-UK: The startup. The signature is verified first (`branding.verify`). Then
       it chooses between the graphical interface and text mode, under one
       rule: **if the window cannot open, it falls back to text rather than
       failing** — a server with no desktop, an SSH session, a Python without
       Tkinter all still get a useful answer.

       Text mode asks for the password with `getpass`. **There is no `--senha`
       option**, deliberately: a command-line argument is visible in `ps` and
       lands in the shell history. For automation there is `VFC_PASSWORD`,
       which is not perfect either but stays out of the process list.

Created by Redfox using Claude
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from . import __version__, branding, cli, config, logging_setup, platform_support


def build_parser() -> argparse.ArgumentParser:
    """PT-PT: Os argumentos. / EN-UK: The arguments."""
    analisador = argparse.ArgumentParser(
        prog="vfc",
        description=(
            "VMware Fleet Console — estado, manutenção e exportação de vCenter e ESXi. "
            "Sem argumentos, abre a interface gráfica."
        ),
        epilog=(
            "Códigos de saída: 0 sem nada a apontar, 1 há avisos, 2 há problemas críticos, "
            "3 não foi possível ligar, 4 a assinatura da aplicação foi alterada. "
            f"{branding.CREDIT}."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analisador.add_argument("--versao", action="version", version=f"VMware Fleet Console {__version__}")
    analisador.add_argument(
        "--diagnostico",
        action="store_true",
        help="o que esta máquina tem e o que lhe falta para correr a aplicação",
    )
    analisador.add_argument(
        "--texto",
        action="store_true",
        help="modo de texto, sem janela — para sessões SSH, servidores sem ambiente gráfico e automação",
    )
    analisador.add_argument("--servidor", default="", help="endereço do vCenter ou do anfitrião ESXi")
    analisador.add_argument("--utilizador", default="", help="nome de utilizador")
    analisador.add_argument("--porta", type=int, default=0, help="porta (por omissão 443)")
    analisador.add_argument(
        "--seccao",
        choices=["tudo", "estado", "anfitrioes", "maquinas", "datastores", "snapshots"],
        default="tudo",
        help="o que mostrar em modo de texto",
    )
    analisador.add_argument("--json", action="store_true", help="saída em JSON, para automação")
    analisador.add_argument("--detalhado", action="store_true", help="registo detalhado no ficheiro")
    return analisador


def main(argv: list[str] | None = None) -> int:
    """PT-PT: O ponto de entrada. / EN-UK: The entry point."""
    try:
        branding.verify()
    except branding.BrandingTamperedError as erro:
        _report_without_console(str(erro))
        return cli.EXIT_TAMPERED

    argumentos = build_parser().parse_args(argv)

    ficheiro = logging_setup.setup(verbose=argumentos.detalhado)
    definicoes = config.load_settings()

    if argumentos.diagnostico:
        cli.write(platform_support.diagnostic_report())
        if ficheiro:
            cli.write(f"\nRegisto em: {ficheiro}")
        return cli.EXIT_OK

    em_falta = platform_support.missing_essentials()
    if em_falta:
        cli.write("Falta o que é essencial para correr:\n", sys.stderr)
        for requisito in em_falta:
            cli.write(str(requisito), sys.stderr)
        cli.write("\nCorra 'python -m vfc --diagnostico' para o relatório completo.", sys.stderr)
        return cli.EXIT_UNREACHABLE

    if argumentos.texto or argumentos.json or argumentos.servidor:
        return _modo_texto(argumentos, definicoes)

    if not platform_support.gui_available():
        cli.write(
            "A interface gráfica não está disponível nesta máquina (sem Tkinter ou sem ambiente "
            "gráfico).\nA usar o modo de texto. Para o relatório de diagnóstico: "
            "python -m vfc --diagnostico\n",
            sys.stderr,
        )
        return _modo_texto(argumentos, definicoes)

    from . import gui  # noqa: PLC0415

    return gui.run(definicoes)


def _report_without_console(texto: str) -> None:
    """
    PT-PT: Escreve o erro na consola — ou, arrancado sem consola (`pythonw`,
           que é como o lançador de Windows abre a janela), mostra-o numa caixa
           de diálogo. Sem isto, a aplicação fechava-se sem dizer nada.
    EN-UK: Writes the error to the console — or, started with no console
           (`pythonw`, how the Windows launcher opens the window), shows it in a
           dialog box. Without this the application would close silently.
    """
    if sys.stderr is not None:
        cli.write(texto, sys.stderr)
        return
    try:
        import tkinter  # noqa: PLC0415
        from tkinter import messagebox  # noqa: PLC0415

        raiz = tkinter.Tk()
        raiz.withdraw()
        messagebox.showerror(branding.APP_NAME, texto, parent=raiz)
        raiz.destroy()
    except Exception:  # noqa: BLE001
        pass


def _modo_texto(argumentos: argparse.Namespace, definicoes: config.Settings) -> int:
    """
    PT-PT: Liga, lê e escreve. Sem interface, sem estado, sem operações.

           **O modo de texto não escreve nada no vSphere.** Não há aqui um
           `--desligar-maquina`, e não é esquecimento: uma operação destrutiva
           sem confirmação escrita fica a um `Ctrl-R` no histórico de distância
           da próxima vez que alguém a repetir sem pensar. As operações — e a
           exportação, que pode encerrar máquinas — vivem na janela, onde há um
           sítio para confirmar.

    EN-UK: Connects, reads, writes out. **Text mode writes nothing to vSphere.**
           There is no `--power-off-vm` here, and that is not an oversight: a
           destructive operation with no written confirmation sits one `Ctrl-R`
           away in the history from the next time somebody repeats it without
           thinking. Operations live in the interface, where there is a place to
           confirm.
    """
    from . import collect, connection, health  # noqa: PLC0415

    anfitriao = argumentos.servidor or (definicoes.servers[0].host if definicoes.servers else "")
    if not anfitriao:
        cli.write("Falta o servidor: use --servidor endereco", sys.stderr)
        return cli.EXIT_UNREACHABLE

    guardado = definicoes.server_for(anfitriao)
    utilizador = argumentos.utilizador or (guardado.username if guardado else "")
    if not utilizador:
        cli.write("Falta o utilizador: use --utilizador nome", sys.stderr)
        return cli.EXIT_UNREACHABLE

    porta = argumentos.porta or (guardado.port if guardado else connection.DEFAULT_PORT)

    confianca = connection.evaluate_trust(
        anfitriao,
        port=porta,
        pinned_fingerprint=guardado.fingerprint if guardado else "",
        timeout=float(definicoes.connect_timeout),
    )
    if confianca.decision is connection.TrustDecision.UNREACHABLE:
        cli.write(confianca.message, sys.stderr)
        return cli.EXIT_UNREACHABLE

    if confianca.needs_decision:
        # PT-PT: Em modo de texto não se aceita um certificado por omissão. Um
        #        script que corra sem ninguém a olhar não é sítio para decidir
        #        em quem se confia — aceita-se uma vez na janela, e a partir
        #        daí o script tem a impressão digital guardada e corre sozinho.
        # EN-UK: Text mode never accepts a certificate by default. A script
        #        running with nobody watching is no place to decide who to
        #        trust — accept it once in the interface, and from then on the
        #        script has the fingerprint stored and runs on its own.
        cli.write(confianca.message, sys.stderr)
        cli.write(
            "\nO certificado deste servidor ainda não foi aceite. Abra a janela uma vez "
            "(python -m vfc), compare a impressão digital e aceite-a. A partir daí o modo de "
            "texto liga sozinho.",
            sys.stderr,
        )
        return cli.EXIT_UNREACHABLE

    senha = os.environ.get("VFC_PASSWORD", "")
    if not senha:
        try:
            senha = getpass.getpass(f"Senha de {utilizador} em {anfitriao}: ")
        except (EOFError, KeyboardInterrupt):
            cli.write("", sys.stderr)
            return cli.EXIT_UNREACHABLE
    if not senha:
        cli.write("Sem senha, não há ligação.", sys.stderr)
        return cli.EXIT_UNREACHABLE

    alvo = connection.Endpoint(host=anfitriao, username=utilizador, port=porta)
    impressao = confianca.certificate.fingerprint_sha256 if confianca.decision is connection.TrustDecision.PINNED_MATCH else ""

    try:
        sessao = connection.connect(alvo, senha, impressao, timeout=float(definicoes.connect_timeout))
    except connection.VSphereConnectionError as erro:
        cli.write(str(erro), sys.stderr)
        return cli.EXIT_UNREACHABLE
    finally:
        senha = ""

    try:
        parque = collect.collect_fleet(sessao)
        achados = health.evaluate(parque, definicoes.thresholds())  # type: ignore[arg-type]

        if argumentos.json:
            cli.write(cli.render_json(parque, achados))
        else:
            seccoes = {
                "tudo": lambda: cli.render_report(parque, achados),
                "estado": lambda: cli.render_summary(parque, achados)
                + "\n\n"
                + cli.render_findings(achados),
                "anfitrioes": lambda: cli.render_hosts(parque),
                "maquinas": lambda: cli.render_vms(parque),
                "datastores": lambda: cli.render_datastores(parque),
                "snapshots": lambda: cli.render_snapshots(parque),
            }
            cli.write(seccoes[argumentos.seccao]())

        # PT-PT: Guarda o endereço e o utilizador para a próxima. Nunca a senha.
        # EN-UK: Stores the address and username for next time. Never the password.
        definicoes.remember(
            config.Server(
                label=guardado.label if guardado else anfitriao,
                host=anfitriao,
                username=utilizador,
                port=porta,
                fingerprint=guardado.fingerprint if guardado else "",
            )
        )
        config.save_settings(definicoes)

        return cli.exit_code_for(achados)
    finally:
        sessao.close()


if __name__ == "__main__":
    sys.exit(main())
