"""Informações do computador (somente leitura), via psutil.

Temperatura só é informada quando o hardware e os drivers a fornecem.
Caso contrário, o LS diz que o dado não está disponível.
"""

from __future__ import annotations

import time
from typing import Any

import psutil

_MB = 1024 * 1024
_GB = 1024 * _MB


def _temperatures() -> dict[str, Any]:
    reader = getattr(psutil, "sensors_temperatures", None)
    if reader is None:
        return {"disponivel": False, "motivo": "sistema não expõe sensores de temperatura"}
    try:
        readings = reader() or {}
    except (OSError, NotImplementedError, AttributeError):
        readings = {}
    values = {
        f"{chip}:{item.label or 'sensor'}": round(item.current, 1)
        for chip, entries in readings.items()
        for item in entries
    }
    if not values:
        return {"disponivel": False, "motivo": "o hardware ou os drivers não fornecem temperatura"}
    return {"disponivel": True, "celsius": values}


def system_status() -> dict[str, Any]:
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disks = []
    for part in psutil.disk_partitions(all=False):
        if not part.fstype or "cdrom" in part.opts.lower():
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        disks.append(
            {
                "unidade": part.mountpoint,
                "total_gb": round(usage.total / _GB, 1),
                "livre_gb": round(usage.free / _GB, 1),
                "uso_percent": usage.percent,
            }
        )
    net = psutil.net_io_counters()
    battery = psutil.sensors_battery()
    return {
        "cpu": {"uso_percent": cpu_percent, "nucleos": psutil.cpu_count(logical=True)},
        "memoria": {
            "total_gb": round(memory.total / _GB, 2),
            "usada_gb": round(memory.used / _GB, 2),
            "uso_percent": memory.percent,
        },
        "discos": disks,
        "rede": {
            "enviado_mb": round(net.bytes_sent / _MB, 1),
            "recebido_mb": round(net.bytes_recv / _MB, 1),
        },
        "bateria": (
            {"percentual": round(battery.percent, 0), "conectada": bool(battery.power_plugged)} if battery else None
        ),
        "temperatura": _temperatures(),
        "processos": len(psutil.pids()),
        "ligado_desde": time.strftime("%d/%m/%Y %H:%M", time.localtime(psutil.boot_time())),
    }


def top_processes(limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            mem = info["memory_info"].rss if info.get("memory_info") else 0
            rows.append({"pid": info["pid"], "nome": info.get("name") or "?", "memoria_mb": round(mem / _MB, 1)})
        except (psutil.Error, KeyError):
            continue
    rows.sort(key=lambda r: r["memoria_mb"], reverse=True)
    return rows[: max(1, min(limit, 50))]


def find_process_pids(name_fragment: str) -> list[int]:
    needle = name_fragment.lower().removesuffix(".exe")
    pids: list[int] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if needle and needle in (proc.info.get("name") or "").lower().removesuffix(".exe"):
                pids.append(proc.info["pid"])
        except psutil.Error:
            continue
    return pids


def network_status() -> dict[str, Any]:
    stats = psutil.net_if_stats()
    interfaces = []
    for name, addresses in psutil.net_if_addrs().items():
        ipv4 = [a.address for a in addresses if a.family.name == "AF_INET"]
        stat = stats.get(name)
        interfaces.append({"nome": name, "ativa": bool(stat and stat.isup), "ipv4": ipv4})
    return {"interfaces": interfaces}
