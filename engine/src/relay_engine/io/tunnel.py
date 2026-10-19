"""SSH tunnels to the databases only an SSH server reaches."""

from __future__ import annotations

import base64
import hashlib
import select
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import paramiko

from relay_engine.io.catalog import SourcesError, SshTunnel, explained

_TIMEOUT = 10
_CHUNK = 1 << 16


def _pump(local: socket.socket, channel: paramiko.Channel, stop: threading.Event) -> None:
    with local, channel:
        while not stop.is_set():
            try:
                ready, _, _ = select.select([local, channel], [], [], 0.5)
                for source, sink in ((local, channel), (channel, local)):
                    if source in ready:
                        data = source.recv(_CHUNK)
                        if not data:
                            return
                        sink.sendall(data)
            except OSError:
                return


def _accept(
    listener: socket.socket,
    transport: paramiko.Transport,
    target: tuple[str, int],
    stop: threading.Event,
) -> None:
    while not stop.is_set():
        try:
            local, peer = listener.accept()
        except TimeoutError:
            continue
        except OSError:
            return
        try:
            channel = transport.open_channel("direct-tcpip", target, peer, timeout=_TIMEOUT)
        except (paramiko.SSHException, OSError):
            local.close()
            continue
        threading.Thread(target=_pump, args=(local, channel, stop), daemon=True).start()


class _RefuseUnknown(paramiko.MissingHostKeyPolicy):
    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        raise SourcesError([
            f"SSH server {hostname}: this computer does not know its host key "
            f"({key.get_name()} SHA256:{digest}); check this fingerprint with the server's "
            "administrator, then connect once with ssh from this computer to trust it"
        ])


def _problem(error: BaseException) -> str:
    return explained(str(error)) or type(error).__name__


def _connect(client: paramiko.SSHClient, tunnel: SshTunnel) -> None:
    where = f"SSH server {tunnel.host}:{tunnel.port}"
    given = bool(tunnel.key or tunnel.secret)
    try:
        client.connect(
            tunnel.host, tunnel.port, tunnel.user,
            password=None if tunnel.key else tunnel.secret or None,
            key_filename=tunnel.key or None,
            passphrase=tunnel.secret or None if tunnel.key else None,
            timeout=_TIMEOUT, banner_timeout=_TIMEOUT, auth_timeout=_TIMEOUT,
            allow_agent=not given, look_for_keys=not given,
        )
    except paramiko.BadHostKeyException as error:
        raise SourcesError([
            f"{where}: its host key is not the one this computer knows ({error}); "
            "check with the server's administrator before trusting it"
        ]) from error
    except paramiko.AuthenticationException as error:
        raise SourcesError([
            f"{where}: authentication failed: check the SSH user, the password, "
            "or the private key and its passphrase"
        ]) from error
    except (paramiko.SSHException, OSError) as error:
        raise SourcesError([f"{where}: {_problem(error)}"]) from error


@contextmanager
def forwarded(tunnel: SshTunnel, host: str, port: int) -> Iterator[int]:
    """A local port reaching host:port through the SSH server, open until the block ends."""
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(_RefuseUnknown())
    stop = threading.Event()
    try:
        _connect(client, tunnel)
        transport = client.get_transport()
        assert transport is not None
        try:
            transport.open_channel(
                "direct-tcpip", (host, port), ("127.0.0.1", 0), timeout=_TIMEOUT
            ).close()
        except (paramiko.SSHException, OSError) as error:
            raise SourcesError([
                f"SSH server {tunnel.host}:{tunnel.port} cannot reach {host}:{port}: "
                f"{_problem(error)}; check the database host as the SSH server sees it"
            ]) from error
        with socket.create_server(("127.0.0.1", 0)) as listener:
            listener.settimeout(0.5)
            threading.Thread(
                target=_accept, args=(listener, transport, (host, port), stop), daemon=True
            ).start()
            yield listener.getsockname()[1]
    finally:
        stop.set()
        client.close()
