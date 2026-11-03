#!/usr/bin/env bash
# ===========================================================================
# PT-PT: Modo de texto da VMware Fleet Console em Linux.
#
#        O mesmo diagnostico, sem janela. Para servidores e sessoes SSH sem
#        ambiente grafico, e para automacao: o codigo de saida diz o estado do
#        parque sem ninguem ler nada. As operacoes e a exportacao so existem na
#        janela.
#
#            ./cli.sh --servidor vcenter.empresa.local --utilizador admin@vsphere.local
#            ./cli.sh --json --seccao estado
#
#        Codigos de saida: 0 tudo bem, 1 avisos, 2 criticos, 3 nao ligou,
#        4 a assinatura da aplicacao foi alterada.
#
#        Para correr sem ninguem a olhar, ponha a senha em VFC_PASSWORD. Nao ha
#        opcao de linha de comandos para ela de proposito: um argumento fica
#        visivel no `ps` para qualquer utilizador da maquina.
#
# EN-UK: VMware Fleet Console text mode on Linux. The same diagnosis without a
#        window, for headless servers, SSH sessions and automation. Exit codes:
#        0 well, 1 warnings, 2 critical, 3 could not connect, 4 signature altered.
#
#        To run unattended, put the password in VFC_PASSWORD. There is
#        deliberately no command-line option for it: an argument is visible in
#        `ps` to every user on the machine.
#
# Created by Redfox using Claude
# ===========================================================================

set -euo pipefail

PROJECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECTO"

if [ ! -x ".venv/bin/python" ]; then
    printf "Ambiente ainda nao preparado. Corra ./executar.sh uma vez primeiro.\n" >&2
    exit 3
fi

export PYTHONPATH="$PROJECTO/src"
exec .venv/bin/python -m vfc --texto "$@"
