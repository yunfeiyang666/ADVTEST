"""
尝试在 Neo4j 未监听时自动拉起 Docker 容器（Windows / Linux 通用 docker CLI）。

环境变量：
  NEO4J_DOCKER_NAMES   逗号分隔的候选容器名，默认 neo4j,advtest-neo4j,nuscenes-neo4j
  VQA_SKIP_NEO4J_DOCKER  为 true 时跳过 docker，仅检测端口
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from typing import Iterable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _parse_bolt(uri: str) -> tuple[str, int]:
    u = urlparse(uri.replace("bolt+s://", "bolt://").replace("neo4j://", "bolt://"))
    host = u.hostname or "127.0.0.1"
    port = int(u.port or 7687)
    return host, port


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_start(names: Iterable[str]) -> bool:
    exe = shutil_which("docker")
    if not exe:
        logger.warning("未找到 docker 命令，无法自动启动 Neo4j 容器")
        return False
    for name in names:
        name = name.strip()
        if not name:
            continue
        try:
            r = subprocess.run(
                [exe, "start", name],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0:
                logger.info("已执行: docker start %s", name)
                return True
            logger.debug("docker start %s -> %s %s", name, r.returncode, r.stderr[:200])
        except Exception as exc:
            logger.debug("docker start %s failed: %s", name, exc)
    return False


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def ensure_neo4j_listening(
    bolt_uri: str,
    *,
    wait_sec: float = 90.0,
    poll: float = 1.5,
) -> bool:
    """
    若 bolt 端口不可连，尝试 `docker start` 候选容器名，再轮询直至超时。
    """
    host, port = _parse_bolt(bolt_uri)
    if _port_open(host, port):
        logger.info("Neo4j 已在 %s:%s 监听", host, port)
        return True

    if os.getenv("VQA_SKIP_NEO4J_DOCKER", "").lower() in ("1", "true", "yes"):
        logger.error("Neo4j 未在 %s:%s 监听，且已设置 VQA_SKIP_NEO4J_DOCKER", host, port)
        return False

    raw = os.getenv("NEO4J_DOCKER_NAMES", "neo4j,advtest-neo4j,nuscenes-neo4j")
    names = [x.strip() for x in raw.split(",") if x.strip()]
    _docker_start(names)

    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if _port_open(host, port, timeout=3.0):
            logger.info("Neo4j 已就绪 %s:%s", host, port)
            return True
        time.sleep(poll)

    logger.error(
        "等待 Neo4j 超时（%s 秒内 %s:%s 仍不可连）。请手动启动数据库或检查 Docker 容器名（NEO4J_DOCKER_NAMES）。",
        int(wait_sec),
        host,
        port,
    )
    return False
