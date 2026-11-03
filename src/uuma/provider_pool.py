"""Node-local Antigravity accounts with isolated credentials and exclusive account leases.

This operator CLI is deliberately separate from Agent tools. It never imports an existing
workstation credential, changes a machine-wide login, or replays an interrupted prompt.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

# Pinned agy1.4.4 actually opens this filename (confirmed by native openat trace).
# Keep the other filename as a discovery fallback for previously saved authorization.
TOKEN_NAMES = ("antigravity-oauth-token", "jetski-standalone-oauth-token")
ACCOUNT_ID = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")


class PoolError(RuntimeError):
    pass


@contextlib.contextmanager
def file_lock(path: Path, *, blocking: bool = True):
    """Kernel-owned Linux lock; process death releases it without stale lease recovery."""
    if sys.platform != "linux":
        raise PoolError("The production account pool requires Linux")
    import fcntl

    if path.is_symlink():
        raise PoolError("Pool lock cannot be a symlink")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield fd
    finally:
        os.close(fd)


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        temporary.unlink(missing_ok=True)


class AccountPool:
    def __init__(self, root: Path):
        expanded = root.expanduser().absolute()
        if expanded.is_symlink() or expanded.resolve() != expanded:
            raise PoolError("Pool root must be a real absolute directory")
        self.root = expanded
        self.index = self.root / "pool.json"

    def initialize(self, command: Path) -> None:
        command = command.resolve(strict=True)
        if not command.is_file() or not os.access(command, os.X_OK):
            raise PoolError("Provider command must be an executable file")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.root.chmod(0o700)
        atomic_json(self.index, {
            "schema_version": 1, "command": str(command),
            "command_sha256": hashlib.sha256(command.read_bytes()).hexdigest(),
            "accounts": [], "verification": None,
        })

    def _read(self) -> dict:
        if self.index.is_symlink() or not self.index.is_file():
            raise PoolError("Pool is not initialized")
        data = json.loads(self.index.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise PoolError("Unsupported account pool schema")
        return data

    def _account(self, data: dict, account_id: str) -> dict:
        if not ACCOUNT_ID.fullmatch(account_id):
            raise PoolError("Invalid account ID")
        for account in data["accounts"]:
            if account["id"] == account_id:
                return account
        raise PoolError("Account ID is not registered")

    def home(self, account_id: str) -> Path:
        if not ACCOUNT_ID.fullmatch(account_id):
            raise PoolError("Invalid account ID")
        path = self.root / "accounts" / account_id / "home"
        if path.resolve() != path:
            raise PoolError("Account directories cannot contain symlinks")
        return path

    def token(self, account_id: str) -> Path | None:
        home = self.home(account_id)
        for name in TOKEN_NAMES:
            candidate = home / ".gemini" / "antigravity-cli" / name
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(home):
                raise PoolError("Account credential cannot be an external link")
            if candidate.is_file() and candidate.stat().st_size > 10:
                return candidate
        return None

    def add(self, account_id: str, *, label: str, priority: int = 100) -> None:
        if not ACCOUNT_ID.fullmatch(account_id):
            raise PoolError("Use a lowercase account ID such as account-01")
        if not label.strip() or len(label) > 120:
            raise PoolError("Account label must contain 1 to 120 characters")
        with file_lock(self.root / "metadata.lock"):
            data = self._read()
            if any(account["id"] == account_id for account in data["accounts"]):
                raise PoolError("Account already exists; use login to authorize it")
            home = self.home(account_id)
            home.mkdir(parents=True, mode=0o700, exist_ok=False)
            # mkdir's parents can otherwise inherit a permissive process umask.
            for directory in [home.parent.parent, home.parent, home]:
                directory.chmod(0o700)
            (home.parent / "login-workspace").mkdir(mode=0o700)
            data["accounts"].append({
                "id": account_id, "label": label, "priority": priority,
                "enabled": True, "authorized": False, "cooldown_until": 0,
                "last_selected": 0,
            })
            atomic_json(self.index, data)

    def configure(self, account_id: str, *, enabled=None, priority=None) -> None:
        with file_lock(self.root / "metadata.lock"):
            data = self._read()
            account = self._account(data, account_id)
            if enabled is not None:
                account["enabled"] = bool(enabled)
            if priority is not None:
                account["priority"] = int(priority)
            atomic_json(self.index, data)

    def _command(self, data: dict) -> str:
        path = Path(data["command"])
        if (path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != data["command_sha256"]):
            raise PoolError("Provider command changed; create a reviewed release before using it")
        return str(path)

    def environment(self, account_id: str) -> dict[str, str]:
        home = self.home(account_id)
        environment = {
            key: value for key, value in os.environ.items()
            if not any(word in key.upper() for word in (
                "API_KEY", "ACCESS_TOKEN", "REFRESH_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS",
                "GEMINI_API", "ANTHROPIC_AUTH", "DBUS_SESSION_BUS_ADDRESS",
            ))
        }
        environment.update({
            "HOME": str(home), "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "ANTIGRAVITY_CONFIG_DIR": str(home / ".gemini" / "antigravity-cli"),
            "AGY_CLI_DISABLE_AUTO_UPDATE": "1",
            # Force Linux's shared keyring to fail closed, then use the account's own
            # native CLI token file. An unset DBUS address can discover a shared bus.
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(home / ".no-session-bus"),
        })
        timestamp_file = home / ".gemini" / "antigravity-cli" / "last_check.timestamp"
        if timestamp_file.parent.is_dir():
            try:
                timestamp_file.touch(exist_ok=True)
                os.utime(timestamp_file, (time.time() + 86400 * 365, time.time() + 86400 * 365))
            except OSError:
                pass
        return environment

    def status(self) -> dict:
        data = self._read()
        accounts = []
        for account in data["accounts"]:
            present = self.token(account["id"]) is not None
            busy = False
            try:
                with file_lock(self.home(account["id"]).parent / "lease.lock", blocking=False):
                    pass
            except BlockingIOError:
                busy = True
            accounts.append({
                "id": account["id"], "label": account["label"],
                "priority": account["priority"], "enabled": account["enabled"],
                "status": "NEEDS_LOGIN" if not present or not account["authorized"] else (
                    "DISABLED" if not account["enabled"] else
                    "COOLDOWN" if account["cooldown_until"] > time.time() else
                    "BUSY" if busy else "READY"
                ),
                "busy": busy,
                "cooldown_until": account["cooldown_until"],
            })
        return {"accounts": accounts, "verification": data["verification"]}

    def authentication_token(self) -> Path | None:
        """Provider startup probe only; this does not reserve an account for execution."""
        for account in self._eligible(self._read()):
            if token := self.token(account["id"]):
                return token
        return None

    def _eligible(self, data: dict) -> list[dict]:
        return sorted([
            account for account in data["accounts"]
            if account["enabled"] and account["authorized"]
            and account["cooldown_until"] <= time.time()
        ], key=lambda account: (account["priority"], account["last_selected"], account["id"]))

    @contextlib.contextmanager
    def lease(self, *, wait_timeout: float = 0.0, poll_interval: float = 0.5):
        deadline = time.monotonic() + max(0.0, wait_timeout)
        with contextlib.ExitStack() as locks:
            while True:
                with file_lock(self.root / "metadata.lock"):
                    data = self._read()
                    eligible = self._eligible(data)
                    selected = None
                    for account in eligible:
                        if not self.token(account["id"]):
                            continue
                        try:
                            descriptor = locks.enter_context(file_lock(
                                self.home(account["id"]).parent / "lease.lock", blocking=False
                            ))
                        except BlockingIOError:
                            continue
                        selected = account
                        selected["last_selected"] = time.time()
                        atomic_json(self.index, data)
                        break

                    if selected is not None:
                        command = self._command(data)
                        break

                    # Fail fast if no accounts are registered and enabled at all
                    if not any(a.get("enabled", False) for a in data.get("accounts", [])):
                        raise PoolError("No authorized account is ready; accounts may be busy or cooling down")

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolError("No authorized account is ready; accounts may be busy or cooling down")

                time.sleep(min(poll_interval, remaining))

            yield selected, command, descriptor

    def login(self, account_id: str, *, verify_once: bool = False) -> int:
        """Official CLI owns OAuth. Empty interactive login makes no model request here."""
        data = self._read()
        self._account(data, account_id)
        with file_lock(self.home(account_id).parent / "lease.lock", blocking=False) as descriptor:
            command = self._command(data)
            if self.token(account_id):
                raise PoolError("Saved credential exists; use check instead of replacing it")
            if verify_once:
                with file_lock(self.root / "metadata.lock"):
                    data = self._read()
                    if data["verification"] is not None:
                        raise PoolError("The one model verification has already been attempted")
                    data["verification"] = {
                        "account_id": account_id, "status": "STARTED", "at": time.time(),
                    }
                    atomic_json(self.index, data)
            args = ["-p", "Reply OK.", "--print-timeout", "5m"] if verify_once else []
            previous_umask = os.umask(0o077)
            try:
                code = subprocess.run(
                    [command, *args], env=self.environment(account_id),
                    cwd=self.home(account_id).parent / "login-workspace", check=False,
                    pass_fds=(descriptor,),
                ).returncode
            finally:
                os.umask(previous_umask)
                self._reap_lease_holders(self.home(account_id).parent / "lease.lock")
            authorized = self._check(account_id, descriptor)
            if verify_once:
                with file_lock(self.root / "metadata.lock"):
                    data = self._read()
                    data["verification"]["status"] = (
                        "SUCCEEDED" if code == 0 and authorized else "FAILED_OR_UNCONFIRMED"
                    )
                    atomic_json(self.index, data)
            return 0 if authorized else (code or 1)

    def check(self, account_id: str) -> bool:
        with file_lock(self.home(account_id).parent / "lease.lock", blocking=False) as descriptor:
            return self._check(account_id, descriptor)

    def _check(self, account_id: str, descriptor: int) -> bool:
        data = self._read()
        self._account(data, account_id)
        token = self.token(account_id)
        authorized = False
        if token:
            token.chmod(0o600)
            try:
                result = subprocess.run(
                    [self._command(data), "models"], env=self.environment(account_id),
                    cwd=self.home(account_id).parent / "login-workspace",
                    capture_output=True, timeout=45, check=False,
                    pass_fds=(descriptor,),
                )
                authorized = result.returncode == 0 and bool(result.stdout.strip())
            except subprocess.TimeoutExpired:
                pass
            finally:
                self._reap_lease_holders(self.home(account_id).parent / "lease.lock")
        with file_lock(self.root / "metadata.lock"):
            data = self._read()
            self._account(data, account_id)["authorized"] = authorized
            atomic_json(self.index, data)
        return authorized

    def _reap_lease_holders(self, lock_path: Path) -> None:
        """Terminate any orphaned processes that inherited the lease lock descriptor.

        Third-party binaries (such as agy) may spawn background daemon processes
        (such as --bg-updater) that inherit open file descriptors across fork/exec.
        When the primary inference process exits, any surviving background process
        holding the lock descriptor keeps the kernel flock active indefinitely,
        preventing subsequent leases on this account.
        """
        if sys.platform != "linux":
            return
        resolved = lock_path.resolve()
        current_pid = os.getpid()
        proc_path = Path("/proc")
        if not proc_path.is_dir():
            return
        for entry in proc_path.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid == current_pid:
                continue
            try:
                fd_dir = entry / "fd"
                if not fd_dir.is_dir():
                    continue
                for fd_link in fd_dir.iterdir():
                    try:
                        if fd_link.resolve() == resolved:
                            os.kill(pid, signal.SIGKILL)
                            break
                    except (OSError, FileNotFoundError):
                        pass
            except (PermissionError, FileNotFoundError):
                pass

    def run(self, arguments: list[str], *, wait_timeout: float | None = None) -> int:
        # Authentication belongs to the operator. Agent calls cannot open login automatically.
        if not arguments or any(arg in {"--continue", "-c", "--conversation"} for arg in arguments):
            raise PoolError("Pool execution requires a fresh provider turn or metadata command")
        if wait_timeout is None:
            wait_timeout = float(os.getenv("UUMA_AGY_POOL_LEASE_TIMEOUT", "60.0"))
        timeout = float(os.getenv("UUMA_AGY_POOL_EXECUTION_TIMEOUT", "900"))
        if not 0 < timeout <= 3600:
            raise PoolError("Provider execution timeout must be finite and at most 3600 seconds")
        guard = Path(__file__).with_name("provider_guard.py" if __package__ else
                                         "uuma_provider_guard.py")
        if not guard.is_file():
            raise PoolError("Pinned provider process supervisor is missing")
        with self.lease(wait_timeout=wait_timeout) as (account, command, descriptor):
            # Only the guardian inherits the lease. The lifetime pipe's sole writer belongs to
            # this wrapper: even SIGKILL closes it and triggers descendant cleanup in the guardian.
            lifetime_read, lifetime_write = os.pipe()
            process = None
            reader = None
            errors = bytearray()

            def forward_errors():
                assert process.stderr is not None
                while chunk := process.stderr.read1(4096):
                    errors.extend(chunk)
                    del errors[:-65536]
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()

            try:
                process = subprocess.Popen(
                    [sys.executable, str(guard), "--lease-fd", str(descriptor),
                     "--lifetime-fd", str(lifetime_read), "--timeout", str(timeout),
                     "--", command, *arguments],
                    env=self.environment(account["id"]), stderr=subprocess.PIPE,
                    pass_fds=(descriptor, lifetime_read), start_new_session=True,
                )
                os.close(lifetime_read)
                lifetime_read = None
                reader = threading.Thread(target=forward_errors, daemon=True)
                reader.start()
                code = process.wait()
            finally:
                os.close(lifetime_write)
                if lifetime_read is not None:
                    os.close(lifetime_read)
                if process is not None:
                    # EOF asks the guardian to kill and reap its descendants before releasing
                    # the lease. Do not kill the guardian and release a still-live account.
                    process.wait()
                    if reader is not None:
                        reader.join(timeout=5)
                    process.stderr.close()
            # Only explicit provider quota codes cool an account. Never replay this turn:
            # a failed response may follow an already performed external action.
            quota_error = re.search(
                rb'RESOURCE_EXHAUSTED|"(?:status|code)"\s*:\s*429\b|HTTP\s+429\b', errors
            )
            if code and quota_error:
                cooldown_seconds = int(os.getenv("UUMA_AGY_POOL_COOLDOWN_SECONDS", "60"))
                with file_lock(self.root / "metadata.lock"):
                    data = self._read()
                    self._account(data, account["id"])["cooldown_until"] = time.time() + cooldown_seconds
                    atomic_json(self.index, data)
            return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="action", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--command", type=Path, required=True)
    add = commands.add_parser("add")
    add.add_argument("account_id")
    add.add_argument("--label", required=True)
    add.add_argument("--priority", type=int, default=100)
    commands.add_parser("status")
    for action in ["login", "check", "enable", "disable", "prefer"]:
        command = commands.add_parser(action)
        command.add_argument("account_id")
        if action == "login":
            command.add_argument("--verify-once", action="store_true")
        if action == "prefer":
            command.add_argument("--priority", type=int, required=True)
    run = commands.add_parser("run")
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        pool = AccountPool(args.root)
        if args.action == "init":
            pool.initialize(args.command)
        elif args.action == "add":
            pool.add(args.account_id, label=args.label, priority=args.priority)
        elif args.action == "status":
            print(json.dumps(pool.status(), ensure_ascii=False, indent=2))
        elif args.action == "login":
            return pool.login(args.account_id, verify_once=args.verify_once)
        elif args.action == "check":
            ok = pool.check(args.account_id)
            print(json.dumps({"account_id": args.account_id, "authorized": ok}))
            return 0 if ok else 1
        elif args.action == "run":
            argv = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            return pool.run(argv)
        else:
            pool.configure(
                args.account_id,
                enabled={"enable": True, "disable": False}.get(args.action),
                priority=getattr(args, "priority", None),
            )
        return 0
    except (PoolError, BlockingIOError) as exc:
        print(f"Account pool: {exc}", file=sys.stderr)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
