#!/usr/bin/env python3
"""
PT-PT: O trabalho em segundo plano, e a ponte de volta para a janela.

       Duas regras, e a razão de cada uma:

       **Uma thread só para o vSphere.** Todas as chamadas ao servidor —
       recolher o inventário, ligar uma máquina, exportar — passam por uma
       única thread, uma de cada vez. O `pyVmomi` partilha uma ligação por
       sessão, e duas chamadas ao mesmo tempo pela mesma sessão são a receita
       para uma resposta trocada. Em fila, a pior coisa que pode acontecer é
       esperar.

       **O Tk só se mexe na thread dele.** O Tk não é seguro entre threads: um
       widget alterado de outra thread rebenta, às vezes só uma vez por semana.
       O que vem do trabalho em segundo plano vai para uma fila, e a janela
       esvazia-a de 50 em 50 ms, na sua própria thread.

EN-UK: Background work, and the bridge back to the window. **One thread for
       vSphere**: every server call goes through a single thread, one at a
       time — pyVmomi shares one connection per session, and two concurrent
       calls on it are a recipe for crossed replies. **Tk only moves on its own
       thread**: results go into a queue the window drains every 50 ms.

Created by Redfox using Claude
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger(__name__)

POLL_MS = 50


class Worker:
    """
    PT-PT: Executa funções em segundo plano e entrega o resultado à janela.
    EN-UK: Runs functions in the background and hands results to the window.
    """

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._fila: queue.Queue[tuple[Callable[..., None], tuple[object, ...]]] = queue.Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vsphere")
        self._pendentes = 0
        self._parado = False
        self._root.after(POLL_MS, self._drain)

    @property
    def busy(self) -> bool:
        """PT-PT: Se há trabalho em curso ou em fila. / EN-UK: Whether work is running or queued."""
        return self._pendentes > 0

    def submit(
        self,
        function: Callable[[], object],
        on_done: Callable[[object], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        """
        PT-PT: Põe `function` na fila. `on_done` e `on_error` correm depois na
               thread da janela. Sem `on_error`, a falha fica no registo.
        EN-UK: Queues `function`. `on_done` and `on_error` later run on the
               window's thread. Without `on_error`, the failure is logged.
        """
        if self._parado:
            return
        self._pendentes += 1
        futuro = self._executor.submit(function)
        futuro.add_done_callback(lambda f: self._fila.put((self._finish, (f, on_done, on_error))))

    def post(self, callback: Callable[..., None], *args: object) -> None:
        """
        PT-PT: Chamado de dentro do trabalho em segundo plano: agenda `callback`
               para correr na thread da janela. É por aqui que chega o progresso
               da exportação.
        EN-UK: Called from inside background work: schedules `callback` on the
               window's thread. Export progress arrives this way.
        """
        self._fila.put((callback, args))

    def stop(self) -> None:
        """PT-PT: Pára de aceitar trabalho. / EN-UK: Stops accepting work."""
        self._parado = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _finish(
        self,
        futuro: Future,
        on_done: Callable[[object], None] | None,
        on_error: Callable[[BaseException], None] | None,
    ) -> None:
        self._pendentes -= 1
        erro = futuro.exception() if not futuro.cancelled() else None
        if futuro.cancelled():
            return
        if erro is not None:
            if on_error is not None:
                on_error(erro)
            else:
                logger.error("Trabalho em segundo plano falhou: %s", erro, exc_info=erro)
            return
        if on_done is not None:
            on_done(futuro.result())

    def _drain(self) -> None:
        try:
            while True:
                callback, args = self._fila.get_nowait()
                try:
                    callback(*args)
                except Exception:  # noqa: BLE001
                    logger.exception("Falha ao actualizar a janela")
        except queue.Empty:
            pass
        if not self._parado:
            try:
                self._root.after(POLL_MS, self._drain)
            except tk.TclError:
                # PT-PT: A janela já foi fechada. / EN-UK: The window is gone.
                self._parado = True
