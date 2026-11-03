#!/usr/bin/env python3
"""
PT-PT: A assinatura da aplicação, e o selo que a protege.

       **O que isto faz.** O nome da aplicação, o autor e o crédito vivem aqui
       e só aqui. Toda a parte da aplicação que os mostra — a barra de título,
       o rodapé permanente da janela, o "Sobre", o relatório de texto, o
       relatório de cada exportação, o `LEIA-ME.txt` ao lado de cada cópia e a
       primeira linha do registo — vai buscá-los a este módulo.

       Os três valores estão selados: o arranque calcula o SHA-256 deles e
       compara-o com `_SEAL`. Se alguém mudar ou apagar o crédito, a aplicação
       recusa arrancar e diz porquê. A janela principal confirma ainda, depois
       de desenhada, que o rodapé mostra o crédito tal como está aqui.

       **O que isto não faz, dito com honestidade.** Nenhuma assinatura em
       código que corre na máquina de outra pessoa é impossível de remover: o
       Python é texto, e quem apagar o crédito pode apagar também a
       verificação. O que o selo garante é que a remoção não acontece por
       acaso nem às escondidas — obriga a alterar a aplicação de propósito, em
       mais do que um sítio. A protecção que vale num tribunal é a licença MIT,
       que obriga a manter o aviso de autoria em todas as cópias.

EN-UK: The application's signature, and the seal that protects it.

       Name, author and credit live here and only here; everything that shows
       them reads them from this module. The three values are sealed: startup
       hashes them and compares against `_SEAL`, refusing to start if the
       credit was changed or removed. The main window also confirms, once
       drawn, that its footer shows the credit exactly as stored here.

       Honestly stated: no signature in code running on somebody else's
       machine is impossible to remove — Python is text, and whoever deletes
       the credit can delete the check. What the seal guarantees is that
       removal is never accidental or silent. The protection that holds up
       legally is the MIT licence, which requires the copyright notice to be
       kept in all copies.

Created by Redfox using Claude
"""

from __future__ import annotations

import hashlib

APP_NAME = "VMware Fleet Console"
AUTHOR = "Rafael Santos (Redfox)"
CREDIT = "Created by Redfox using Claude"

# PT-PT: SHA-256 de "APP_NAME|AUTHOR|CREDIT". Mudar um dos três sem mudar isto
#        impede o arranque — que é o objectivo.
# EN-UK: SHA-256 of "APP_NAME|AUTHOR|CREDIT". Changing any of the three without
#        changing this stops startup — which is the point.
_SEAL = "19662f0f8d9a4f6320afd77b5b697da8ada9541409c07c30c3a2d7829f579b7a"


class BrandingTamperedError(RuntimeError):
    """
    PT-PT: A assinatura foi alterada.
    EN-UK: The signature was altered.
    """


def seal_of(app_name: str, author: str, credit: str) -> str:
    """
    PT-PT: O selo de três valores.
    EN-UK: The seal of three values.

    >>> seal_of(APP_NAME, AUTHOR, CREDIT) == _SEAL
    True
    """
    return hashlib.sha256("|".join([app_name, author, credit]).encode("utf-8")).hexdigest()


def verify() -> None:
    """
    PT-PT: Confirma que a assinatura está intacta. Chamado no arranque, antes
           de qualquer outra coisa.
    EN-UK: Confirms the signature is intact. Called at startup, before anything
           else.
    """
    if not CREDIT.strip() or seal_of(APP_NAME, AUTHOR, CREDIT) != _SEAL:
        raise BrandingTamperedError(
            "A assinatura desta aplicação foi alterada. A VMware Fleet Console é de "
            "Rafael Santos (Redfox) e é distribuída sob a licença MIT, que obriga a manter "
            "o aviso de autoria em todas as cópias. Reponha a versão original."
        )


def verify_displayed(text: str) -> None:
    """
    PT-PT: Confirma que um texto mostrado ao utilizador contém o crédito. É o
           que a janela principal chama sobre o seu próprio rodapé.
    EN-UK: Confirms text shown to the user contains the credit — what the main
           window calls on its own footer.
    """
    verify()
    if CREDIT not in text:
        raise BrandingTamperedError(
            "O rodapé da janela já não mostra a assinatura da aplicação. Reponha a "
            "versão original."
        )


def window_title(version: str, detail: str = "") -> str:
    """
    PT-PT: O título das janelas.
    EN-UK: The window title.

    >>> window_title("2.0.0")
    'VMware Fleet Console 2.0.0 — Created by Redfox using Claude'
    """
    base = f"{APP_NAME} {version}"
    if detail:
        base += f" · {detail}"
    return f"{base} — {CREDIT}"
