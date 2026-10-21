#!/usr/bin/env python3
"""Verify a receipt-bound Windows Axx backend speaks MCP over stdio.

This probe deliberately calls only initialize and tools/list. It never invokes
an Axx tool, reads Codex credentials, or submits a model/account request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any


EXPECTED_MCP = "1.30.0"
EXPECTED_TOOLS = {
    "axx_status",
    "axx_list_capabilities",
    "axx_execute_action",
    "axx_get_task",
    "axx_cancel_task",
    "axx_system_telemetry",
    "axx_process_inspect",
}
REQUIRED_RECEIPT_INPUTS = (
    "axx-backend.spec",
    "backend/connect/mcp_server.py",
    "backend/speech/offline_asr.py",
    "resources/asr-model-manifest.json",
    "requirements-axx-connect.txt",
    "requirements-axx-connect-win64.lock.txt",
    "scripts/axx_packaging_guard.py",
    "resources/axx-connect-build-dependencies.json",
)
MAX_STDOUT_LINE = 1_048_576
MAX_STDERR_TAIL = 4096


class ProbeError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_path(value: str) -> str:
    return value.replace("\\", "/").strip("./").casefold()


def find_receipt_input(inputs: dict[str, Any], relative: str) -> tuple[str, str]:
    target = norm_path(relative)
    exact = [(key, value) for key, value in inputs.items() if norm_path(str(key)) == target]
    matches = exact or [
        (key, value)
        for key, value in inputs.items()
        if norm_path(str(key)).endswith("/" + target)
    ]
    if len(matches) != 1:
        raise ProbeError(f"El recibo debe contener una sola entrada para {relative}.")
    key, value = matches[0]
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ProbeError(f"Hash inválido en el recibo para {relative}.")
    return str(key), value.lower()


def verify_source_receipt(source_root: Path, receipt_path: Path) -> dict[str, Any]:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProbeError(f"No se pudo leer el recibo de build ({type(exc).__name__}).") from None
    inputs = receipt.get("inputs")
    if not isinstance(inputs, dict):
        raise ProbeError("El recibo no contiene el inventario de entradas del backend.")
    environment_hash = receipt.get("build_environment_sha256")
    binary_hash = receipt.get("sha256")
    for label, value in (("entorno", environment_hash), ("backend", binary_hash)):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ProbeError(f"El recibo no contiene un SHA-256 válido para {label}.")

    checked: dict[str, str] = {}
    for relative in REQUIRED_RECEIPT_INPUTS:
        _, recorded_hash = find_receipt_input(inputs, relative)
        path = source_root.joinpath(*relative.split("/"))
        if not path.is_file():
            raise ProbeError(f"Falta una entrada requerida del build: {relative}.")
        actual_hash = sha256_file(path)
        if actual_hash != recorded_hash:
            raise ProbeError(f"La fuente cambió después del build: {relative}.")
        checked[relative] = actual_hash

    requirement_lines = (source_root / "requirements-axx-connect.txt").read_text(
        encoding="utf-8-sig"
    ).splitlines()
    if f"mcp=={EXPECTED_MCP}" not in [line.strip() for line in requirement_lines]:
        raise ProbeError(f"El requisito directo no fija mcp=={EXPECTED_MCP}.")
    lock_text = (source_root / "requirements-axx-connect-win64.lock.txt").read_text(
        encoding="utf-8-sig"
    )
    if not re.search(rf"(?im)^mcp=={re.escape(EXPECTED_MCP)}\s*(?:\\)?\s*$", lock_text):
        raise ProbeError(f"El lock de Windows no fija mcp=={EXPECTED_MCP}.")

    try:
        model_manifest = json.loads(
            (source_root / "resources/asr-model-manifest.json").read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError) as exc:
        raise ProbeError(f"No se pudo leer el manifiesto ASR ({type(exc).__name__}).") from None
    model_files = model_manifest.get("files")
    if not isinstance(model_files, list) or not model_files:
        raise ProbeError("El manifiesto ASR no enumera archivos de modelo.")
    for item in model_files:
        name = item.get("name") if isinstance(item, dict) else None
        expected_hash = item.get("sha256") if isinstance(item, dict) else None
        expected_bytes = item.get("bytes") if isinstance(item, dict) else None
        if not isinstance(name, str) or Path(name).name != name:
            raise ProbeError("El manifiesto ASR contiene un nombre de archivo inválido.")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            raise ProbeError(f"Hash inválido en el manifiesto ASR para {name}.")
        model_relative = f"resources/models/faster-whisper-tiny/{name}"
        _, recorded_hash = find_receipt_input(inputs, model_relative)
        model_path = source_root.joinpath(*model_relative.split("/"))
        if not model_path.is_file():
            raise ProbeError(f"Falta un archivo del modelo ASR: {name}.")
        actual_hash = sha256_file(model_path)
        if actual_hash != expected_hash.lower() or actual_hash != recorded_hash:
            raise ProbeError(f"El archivo ASR difiere del manifiesto o del recibo: {name}.")
        if not isinstance(expected_bytes, int) or model_path.stat().st_size != expected_bytes:
            raise ProbeError(f"El tamaño del archivo ASR no coincide: {name}.")
        checked[model_relative] = actual_hash

    return {
        "binary_sha256": binary_hash.lower(),
        "build_environment_sha256": environment_hash.lower(),
        "receipt_sha256": sha256_file(receipt_path),
        "source_inputs_checked": checked,
    }


def child_environment() -> dict[str, str]:
    if os.name != "nt":
        raise ProbeError("Este chequeo debe ejecutarse en Windows.")
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not system_root:
        raise ProbeError("Windows no expone SystemRoot.")
    system32 = str(Path(system_root) / "System32")
    allowed = (
        "SystemRoot",
        "WINDIR",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "APPDATA",
        "TEMP",
        "TMP",
    )
    env = {key: os.environ[key] for key in allowed if os.environ.get(key)}
    env["SystemRoot"] = system_root
    env["WINDIR"] = system_root
    env["PATH"] = system32
    # No Python/Node search paths or Axx bearer overrides are inherited.
    for key in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "AXX_HOST_TOKEN", "AXX_CONNECT_DATA_DIR"):
        env.pop(key, None)
    return env


class StdioCapture:
    def __init__(self, process: subprocess.Popen[bytes]):
        self.lines: queue.Queue[bytes | None] = queue.Queue(maxsize=8)
        self.overflow = threading.Event()
        self.stderr_total = 0
        self.stderr_tail = bytearray()
        self._stderr_lock = threading.Lock()
        self.stdout_thread = threading.Thread(target=self._read_stdout, args=(process.stdout,), daemon=True)
        self.stderr_thread = threading.Thread(target=self._read_stderr, args=(process.stderr,), daemon=True)
        self.stdout_thread.start()
        self.stderr_thread.start()

    def _read_stdout(self, stream: Any) -> None:
        try:
            while True:
                line = stream.readline(MAX_STDOUT_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_STDOUT_LINE:
                    self.overflow.set()
                    break
                try:
                    self.lines.put_nowait(line)
                except queue.Full:
                    self.overflow.set()
                    break
        finally:
            try:
                self.lines.put_nowait(None)
            except queue.Full:
                self.overflow.set()

    def _read_stderr(self, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                with self._stderr_lock:
                    self.stderr_total += len(chunk)
                    self.stderr_tail.extend(chunk)
                    if len(self.stderr_tail) > MAX_STDERR_TAIL:
                        del self.stderr_tail[:-MAX_STDERR_TAIL]
        finally:
            stream.close()

    def stderr_summary(self) -> dict[str, Any]:
        with self._stderr_lock:
            raw = bytes(self.stderr_tail)
            total = self.stderr_total
        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", text)
        for key in ("USERPROFILE", "LOCALAPPDATA", "APPDATA"):
            value = os.environ.get(key)
            if value:
                text = re.sub(re.escape(value), "<USER_PATH>", text, flags=re.IGNORECASE)
        return {"bytes": total, "tail_redacted": text[-1024:]}


def write_message(process: subprocess.Popen[bytes], value: dict[str, Any]) -> None:
    if process.stdin is None:
        raise ProbeError("No se abrió stdin para el servidor MCP.")
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    process.stdin.write(encoded + b"\n")
    process.stdin.flush()


def read_response(
    process: subprocess.Popen[bytes], capture: StdioCapture, expected_id: int, timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        if capture.overflow.is_set():
            raise ProbeError("El servidor excedió el límite de salida MCP.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeError(f"Timeout esperando la respuesta MCP id={expected_id}.")
        try:
            line = capture.lines.get(timeout=min(remaining, 0.2))
        except queue.Empty:
            if process.poll() is not None:
                raise ProbeError(f"El servidor MCP terminó antes de responder (exit={process.returncode}).")
            continue
        if line is None:
            raise ProbeError("El servidor MCP cerró stdout antes de responder.")
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError):
            raise ProbeError("stdout contiene una línea que no es JSON-RPC UTF-8 válido.") from None
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ProbeError("stdout contiene un mensaje que no cumple JSON-RPC 2.0.")
        if message.get("id") != expected_id:
            raise ProbeError("stdout contiene una respuesta o notificación MCP no solicitada.")
        if "error" in message:
            raise ProbeError(f"MCP respondió error para id={expected_id}.")
        result = message.get("result")
        if not isinstance(result, dict):
            raise ProbeError(f"La respuesta MCP id={expected_id} no contiene result.")
        return result


def terminate_owned_tree(process: subprocess.Popen[bytes], env: dict[str, str]) -> None:
    if process.poll() is not None:
        return
    taskkill = Path(env["SystemRoot"]) / "System32" / "taskkill.exe"
    try:
        subprocess.run(
            [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=3,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def run_probe(exe: Path, timeout: float) -> dict[str, Any]:
    env = child_environment()
    process = subprocess.Popen(
        [str(exe), "--mcp-server"],
        cwd=str(exe.parent),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        shell=False,
        bufsize=0,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    capture = StdioCapture(process)
    try:
        write_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "axx-packaging-probe", "version": "1.0.0"},
                },
            },
        )
        initialized = read_response(process, capture, 1, timeout)
        protocol_version = initialized.get("protocolVersion")
        if not isinstance(protocol_version, str) or not protocol_version:
            raise ProbeError("initialize no devolvió protocolVersion.")
        server_info = initialized.get("serverInfo")
        if not isinstance(server_info, dict) or server_info.get("name") != "axx-connect":
            raise ProbeError("initialize no devolvió serverInfo.")
        if not isinstance(initialized.get("capabilities"), dict):
            raise ProbeError("initialize no devolvió capabilities.")

        write_message(
            process,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        write_message(
            process,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        listed = read_response(process, capture, 2, timeout)
        tools = listed.get("tools")
        if not isinstance(tools, list):
            raise ProbeError("tools/list no devolvió una lista tools.")
        if listed.get("nextCursor") is not None:
            raise ProbeError("tools/list quedó paginado; no se acepta un catálogo parcial.")
        names = [item.get("name") for item in tools if isinstance(item, dict)]
        if len(names) != len(tools) or set(names) != EXPECTED_TOOLS or len(names) != len(EXPECTED_TOOLS):
            raise ProbeError("tools/list no coincide con el catálogo Connect esperado de siete herramientas.")
        for item in tools:
            schema = item.get("inputSchema")
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise ProbeError(f"La herramienta {item.get('name')} no incluye inputSchema.")

        if process.stdin is not None:
            process.stdin.close()
        try:
            exit_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            terminate_owned_tree(process, env)
            raise ProbeError("El servidor no cerró tras EOF de stdin.") from None
        capture.stdout_thread.join(timeout=1)
        capture.stderr_thread.join(timeout=1)
        if exit_code != 0:
            raise ProbeError(f"El servidor MCP cerró con exit={exit_code}.")
        if capture.overflow.is_set():
            raise ProbeError("stdout excedió los límites del protocolo MCP.")
        try:
            trailing = capture.lines.get_nowait()
        except queue.Empty:
            trailing = None
        if trailing not in (None, b""):
            raise ProbeError("stdout contiene datos adicionales después de tools/list.")
        return {
            "state": "PASS_MCP_INITIALIZE_AND_LIST_TOOLS_ONLY",
            "protocol_version": protocol_version,
            "server_info": server_info,
            "tool_names": sorted(names),
            "tool_count": len(names),
            "child_path_scope": "Windows System32 only; no Python or Node PATH inherited",
            "tool_calls": 0,
            "account_or_model_requests": 0,
            "stderr": capture.stderr_summary(),
        }
    finally:
        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError:
                pass
        terminate_owned_tree(process, env)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path, help="Ruta al axx-backend.exe del build final")
    parser.add_argument("--source-root", required=True, type=Path, help="Raíz exacta de fuentes compiladas")
    parser.add_argument("--receipt", required=True, type=Path, help="build/backend-build-receipt.json")
    parser.add_argument("--expected-sha256", required=True, help="SHA-256 de backend indicado por build-result.json")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--report", type=Path, help="Ruta opcional para guardar el recibo de esta prueba")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report: dict[str, Any] = {
        "state": "FAIL",
        "probe": "packaged-mcp-stdio",
        "tool_calls": 0,
        "account_or_model_requests": 0,
    }
    try:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256):
            raise ProbeError("--expected-sha256 debe ser un SHA-256 hexadecimal de 64 caracteres.")
        if not 1 <= args.timeout_seconds <= 120:
            raise ProbeError("--timeout-seconds debe estar entre 1 y 120.")
        source_root = args.source_root.resolve(strict=True)
        receipt_path = args.receipt.resolve(strict=True)
        exe = args.exe.resolve(strict=True)
        receipt = verify_source_receipt(source_root, receipt_path)
        actual_hash = sha256_file(exe)
        expected_hash = args.expected_sha256.lower()
        if actual_hash != expected_hash or actual_hash != receipt["binary_sha256"]:
            raise ProbeError("El EXE no coincide con el SHA esperado y el recibo del build.")
        result = run_probe(exe, args.timeout_seconds)
        report.update(result)
        report.update(
            {
                "state": result["state"],
                "exe_sha256": actual_hash,
                "receipt_sha256": receipt["receipt_sha256"],
                "build_environment_sha256": receipt["build_environment_sha256"],
                "source_inputs_checked": receipt["source_inputs_checked"],
            }
        )
    except (ProbeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        report["error"] = str(exc) if isinstance(exc, ProbeError) else type(exc).__name__
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    print(encoded)
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.report.with_suffix(args.report.suffix + ".tmp")
            temporary.write_text(encoded + "\n", encoding="utf-8")
            temporary.replace(args.report)
        except OSError:
            print(json.dumps({"report_write": "failed", "error": "OSError"}), file=sys.stderr)
            return 3
    return 0 if report["state"] == "PASS_MCP_INITIALIZE_AND_LIST_TOOLS_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
