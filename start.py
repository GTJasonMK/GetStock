#!/usr/bin/env python
"""
一键启动脚本
同时启动 Python FastAPI 后端和 Next.js 前端
"""

import os
import sys
import signal
import subprocess
import time
import socket
import atexit
import errno
from pathlib import Path
from typing import List, Optional

# 项目根目录
ROOT_DIR = Path(__file__).parent.absolute()
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR = ROOT_DIR / ".venv"

# 端口配置（支持环境变量覆盖）
# - 用户环境常见 3000 被其他 Next/React 项目占用，因此默认前端端口改为 3001
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8001"))
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "3001"))

# 子进程列表
processes: List[subprocess.Popen] = []


def check_venv_import(python_path: Path, module_name: str) -> bool:
    """检查虚拟环境中是否可导入指定模块（用于启动前的友好提示）"""
    try:
        result = subprocess.run(
            [str(python_path), "-c", f"import {module_name}"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_venv_python() -> Optional[Path]:
    """获取虚拟环境中的 Python 路径"""
    if not VENV_DIR.exists():
        return None

    if sys.platform == "win32":
        python_path = VENV_DIR / "Scripts" / "python.exe"
    else:
        python_path = VENV_DIR / "bin" / "python"

    if python_path.exists():
        return python_path
    return None


def get_venv_uvicorn() -> Optional[Path]:
    """获取虚拟环境中的 uvicorn 路径"""
    if not VENV_DIR.exists():
        return None

    if sys.platform == "win32":
        uvicorn_path = VENV_DIR / "Scripts" / "uvicorn.exe"
    else:
        uvicorn_path = VENV_DIR / "bin" / "uvicorn"

    if uvicorn_path.exists():
        return uvicorn_path
    return None


def check_port(port: int) -> bool:
    """检查端口是否可用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Windows 上默认的端口复用语义可能导致“端口被占用但 bind 仍然成功”的误判；
        # 这里尽量模拟 Node 的独占绑定行为，避免 Next.js 启动后报 EADDRINUSE。
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            s.bind(("127.0.0.1", port))
            return True
        except socket.error:
            return False


def check_port_for_nextjs(port: int) -> bool:
    """检查端口是否可用于 Next.js（Node 默认绑定 :::port）"""
    # 优先按 Node/Next.js 的默认行为：绑定到 IPv6 wildcard（::）
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s6:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                try:
                    s6.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
                except Exception:
                    pass
            # 尽量模拟 Node 的 dual-stack 行为（避免“IPv6 可用但 IPv4 冲突”误判）
            try:
                s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except Exception:
                pass
            s6.bind(("::", port, 0, 0))
        # 同时验证 IPv4 wildcard，避免“IPv6 可用但 IPv4 冲突”导致 Next 启动失败
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s4:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                try:
                    s4.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
                except Exception:
                    pass
            s4.bind(("0.0.0.0", port))
        return True
    except OSError as e:
        # 若系统不支持 IPv6，则退回 IPv4 检查（至少保证 localhost 可用）
        ipv6_unsupported_errnos = {
            getattr(errno, "EAFNOSUPPORT", -1),
            getattr(errno, "EADDRNOTAVAIL", -1),
            getattr(errno, "EPROTONOSUPPORT", -1),
            # Windows Winsock 常见 errno（可能不会映射到 errno.* 常量）
            10047,  # WSAEAFNOSUPPORT
            10049,  # WSAEADDRNOTAVAIL
            10043,  # WSAEPROTONOSUPPORT
        }
        if e.errno in ipv6_unsupported_errnos:
            return check_port(port)
        return False


def find_available_port(preferred_port: int, max_tries: int = 50) -> Optional[int]:
    """从 preferred_port 开始向上寻找可用端口"""
    for port in range(preferred_port, preferred_port + max_tries):
        if check_port(port):
            return port
    return None


def find_available_nextjs_port(preferred_port: int, max_tries: int = 50) -> Optional[int]:
    """从 preferred_port 开始向上寻找可用于 Next.js 的端口"""
    for port in range(preferred_port, preferred_port + max_tries):
        if check_port_for_nextjs(port):
            return port
    return None


def kill_process_on_port(port: int) -> None:
    """终止占用指定端口的进程 (仅Windows)"""
    if sys.platform == "win32":
        try:
            # 查找占用端口的PID
            result = subprocess.run(
                f"netstat -ano | findstr :{port}",
                shell=True,
                capture_output=True,
                text=True
            )
            for line in result.stdout.strip().split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                    print(f"  已终止占用端口 {port} 的进程 (PID: {pid})")
        except Exception:
            pass


def cleanup() -> None:
    """清理所有子进程"""
    print("\n正在关闭服务...")

    for proc in processes:
        if proc.poll() is None:  # 进程仍在运行
            try:
                if sys.platform == "win32":
                    # Windows: 使用 taskkill 终止进程树
                    subprocess.run(
                        f"taskkill /F /T /PID {proc.pid}",
                        shell=True,
                        capture_output=True
                    )
                else:
                    # Unix: 发送 SIGTERM 信号
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    processes.clear()
    print("所有服务已关闭")


def signal_handler(signum, frame) -> None:
    """信号处理器"""
    cleanup()
    sys.exit(0)


def start_backend() -> Optional[subprocess.Popen]:
    """启动 FastAPI 后端 (使用虚拟环境)"""
    print(f"启动 FastAPI 后端 (端口 {BACKEND_PORT})...")

    # 检查虚拟环境
    venv_python = get_venv_python()
    venv_uvicorn = get_venv_uvicorn()

    if not venv_python:
        print("  错误: 虚拟环境不存在或 Python 未安装")
        print(f"  请先运行: python install.py")
        return None

    if not venv_uvicorn:
        print("  错误: uvicorn 未安装在虚拟环境中")
        print(f"  请先运行: python install.py")
        return None

    print(f"  使用虚拟环境: {VENV_DIR}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # 启动前预检查：缺少 filelock 时不再阻断启动，而是自动禁用 scheduler（避免多进程重复执行任务）
    if not check_venv_import(venv_python, "filelock"):
        print("  警告: 缺少依赖 filelock（用于多进程调度器选主，避免重复执行）")
        print("  已自动禁用定时任务调度器（ENABLE_SCHEDULER=false）。如需启用请先运行: python install.py")
        env["ENABLE_SCHEDULER"] = "false"

    if not check_port(BACKEND_PORT):
        print(f"  警告: 端口 {BACKEND_PORT} 已被占用")
        kill_process_on_port(BACKEND_PORT)
        time.sleep(1)

    # 使用虚拟环境中的 uvicorn
    cmd = [
        str(venv_uvicorn),
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", str(BACKEND_PORT),
        "--reload"
    ]

    try:
        popen_kwargs = {
            "cwd": str(ROOT_DIR),
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["preexec_fn"] = os.setsid

        proc = subprocess.Popen(cmd, **popen_kwargs)
        processes.append(proc)
        print(f"  后端已启动 (PID: {proc.pid})")
        return proc
    except Exception as e:
        print(f"  启动后端失败: {e}")
        return None


def start_frontend() -> Optional[subprocess.Popen]:
    """启动 Next.js 前端"""
    global FRONTEND_PORT

    if not FRONTEND_DIR.exists():
        print(f"  错误: 前端目录不存在 ({FRONTEND_DIR})")
        return None

    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("  正在安装前端依赖...")
        subprocess.run(
            "npm install",
            cwd=str(FRONTEND_DIR),
            shell=True
        )

    if not check_port_for_nextjs(FRONTEND_PORT):
        candidate = find_available_nextjs_port(FRONTEND_PORT + 1, max_tries=50)
        if not candidate:
            print(f"  错误: 端口 {FRONTEND_PORT} 已被占用，且无法找到可用端口")
            return None

        print(f"  警告: 端口 {FRONTEND_PORT} 已被占用，将自动切换到 {candidate}")
        FRONTEND_PORT = candidate

    print(f"启动 Next.js 前端 (端口 {FRONTEND_PORT})...")

    env = os.environ.copy()

    # Windows 使用 cmd /c 来运行 npm
    if sys.platform == "win32":
        cmd = f"npm run dev -- --port {FRONTEND_PORT}"
        proc = subprocess.Popen(
            cmd,
            cwd=str(FRONTEND_DIR),
            env=env,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        cmd = ["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT)]
        proc = subprocess.Popen(
            cmd,
            cwd=str(FRONTEND_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid
        )

    processes.append(proc)
    print(f"  前端已启动 (PID: {proc.pid})")
    return proc


def stream_output(proc: subprocess.Popen, prefix: str) -> None:
    """流式输出进程日志"""
    if proc.stdout:
        for line in iter(proc.stdout.readline, b''):
            if line:
                try:
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        print(f"[{prefix}] {text}")
                except Exception:
                    pass


def main() -> None:
    """主函数"""
    print("=" * 50)
    print("Stock Recon - 一键启动")
    print("=" * 50)
    print()

    # 注册退出处理
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal_handler)

    # 启动服务
    backend_proc = start_backend()
    if not backend_proc:
        print("后端启动失败，退出")
        sys.exit(1)

    # 等待后端启动
    time.sleep(2)

    frontend_proc = start_frontend()
    if not frontend_proc:
        print("前端启动失败，退出")
        cleanup()
        sys.exit(1)

    print()
    print("=" * 50)
    print("服务已启动:")
    print(f"  后端 API:  http://localhost:{BACKEND_PORT}")
    print(f"  API 文档:  http://localhost:{BACKEND_PORT}/docs")
    print(f"  前端页面:  http://localhost:{FRONTEND_PORT}")
    print()
    print("按 Ctrl+C 停止所有服务")
    print("=" * 50)
    print()

    # 并行输出日志
    import threading

    def output_backend():
        stream_output(backend_proc, "后端")

    def output_frontend():
        stream_output(frontend_proc, "前端")

    backend_thread = threading.Thread(target=output_backend, daemon=True)
    frontend_thread = threading.Thread(target=output_frontend, daemon=True)

    backend_thread.start()
    frontend_thread.start()

    # 等待进程结束或用户中断
    try:
        while True:
            # 检查进程状态
            if backend_proc.poll() is not None:
                print("\n后端进程已退出")
                break
            if frontend_proc.poll() is not None:
                print("\n前端进程已退出")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
