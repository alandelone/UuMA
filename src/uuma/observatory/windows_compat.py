"""Windows-specific asyncio compatibility and resilience patches."""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("uuma.observatory.windows_compat")


def patch_proactor_accept_windows() -> None:
    """Patch asyncio BaseProactorEventLoop._start_serving on Windows.

    Prevents transient client disconnects (WinError 64 ERROR_NETNAME_DELETED,
    WinError 121 ERROR_SEM_TIMEOUT, WinError 1236 ERROR_CONNECTION_ABORTED,
    WinError 10054 WSAECONNRESET) from terminating the accept loop and
    permanently closing the listening socket.
    """
    if sys.platform != "win32":
        return

    try:
        from asyncio.proactor_events import BaseProactorEventLoop, exceptions, trsock

        if getattr(BaseProactorEventLoop, "_uuma_resilient_accept", False):
            return

        def robust_start_serving(
            self,
            protocol_factory,
            sock,
            sslcontext=None,
            server=None,
            backlog=100,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
        ):
            def loop(f=None):
                try:
                    if f is not None:
                        conn, addr = f.result()
                        if self._debug:
                            logger.debug("%r got a new connection from %r: %r", server, addr, conn)
                        protocol = protocol_factory()
                        if sslcontext is not None:
                            self._make_ssl_transport(
                                conn,
                                protocol,
                                sslcontext,
                                server_side=True,
                                extra={"peername": addr},
                                server=server,
                                ssl_handshake_timeout=ssl_handshake_timeout,
                                ssl_shutdown_timeout=ssl_shutdown_timeout,
                            )
                        else:
                            self._make_socket_transport(
                                conn, protocol, extra={"peername": addr}, server=server
                            )
                    if self.is_closed():
                        return
                    f = self._proactor.accept(sock)
                except OSError as exc:
                    winerror = getattr(exc, "winerror", None)
                    # WinError 64: ERROR_NETNAME_DELETED
                    # WinError 121: ERROR_SEM_TIMEOUT
                    # WinError 1236: ERROR_CONNECTION_ABORTED
                    # WinError 10054: WSAECONNRESET
                    if winerror in (64, 121, 1236, 10054) and sock.fileno() != -1 and not self.is_closed():
                        logger.warning(
                            "Transient client reset during accept (WinError %s); kept server socket alive",
                            winerror,
                        )
                        try:
                            f = self._proactor.accept(sock)
                            self._accept_futures[sock.fileno()] = f
                            f.add_done_callback(loop)
                            return
                        except Exception:
                            pass

                    if sock.fileno() != -1:
                        self.call_exception_handler(
                            {
                                "message": "Accept failed on a socket",
                                "exception": exc,
                                "socket": trsock.TransportSocket(sock),
                            }
                        )
                        sock.close()
                    elif self._debug:
                        logger.debug("Accept failed on socket %r", sock, exc_info=True)
                except exceptions.CancelledError:
                    sock.close()
                else:
                    self._accept_futures[sock.fileno()] = f
                    f.add_done_callback(loop)

            self.call_soon(loop)

        BaseProactorEventLoop._start_serving = robust_start_serving
        BaseProactorEventLoop._uuma_resilient_accept = True
        logger.info("Applied Windows proactor accept resilience patch")
    except Exception as exc:
        logger.warning("Could not apply Windows proactor accept resilience patch: %s", exc)
