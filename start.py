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
import platform
import json
import shutil
from pathlib import Path
from typing import List, Optional
import urllib.request

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
cleanup_done = False

def _env_truthy(name: str, default: bool = True) -> bool:
    """读取环境变量布尔值。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    v = str(raw).strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


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


def get_next_swc_candidates() -> List[str]:
    """根据当前平台返回可接受的 Next SWC 包目录名（不含 @next/ 前缀）。"""
    system = sys.platform
    machine = (platform.machine() or "").lower()

    if system == "win32":
        if machine in {"amd64", "x86_64", "x64"}:
            return ["swc-win32-x64-msvc"]
        if machine in {"arm64", "aarch64"}:
            return ["swc-win32-arm64-msvc"]
        if machine in {"x86", "i386", "i686"}:
            return ["swc-win32-ia32-msvc"]
        return []

    if system == "linux":
        if machine in {"amd64", "x86_64", "x64"}:
            return ["swc-linux-x64-gnu", "swc-linux-x64-musl"]
        if machine in {"arm64", "aarch64"}:
            return ["swc-linux-arm64-gnu", "swc-linux-arm64-musl"]
        if machine in {"armv7l", "arm"}:
            return ["swc-linux-arm-gnueabihf"]
        return []

    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return ["swc-darwin-arm64"]
        if machine in {"x86_64", "amd64", "x64"}:
            return ["swc-darwin-x64"]
        return []

    return []


def _read_json(path: Path) -> Optional[dict]:
    """读取 JSON 文件，失败时返回 None。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_version(raw: str) -> str:
    """将 package.json 中的版本约束归一化为具体版本字符串。"""
    s = (raw or "").strip()
    while s and s[0] in "^~<>=":
        s = s[1:].strip()
    return s.split(" ")[0].strip()


def get_expected_next_version() -> Optional[str]:
    """优先从已安装 next 读取版本，回退到 frontend/package.json。"""
    installed_pkg = _read_json(FRONTEND_DIR / "node_modules" / "next" / "package.json")
    if isinstance(installed_pkg, dict):
        version = str(installed_pkg.get("version", "") or "").strip()
        if version:
            return version

    frontend_pkg = _read_json(FRONTEND_DIR / "package.json")
    if not isinstance(frontend_pkg, dict):
        return None

    deps = frontend_pkg.get("dependencies")
    if not isinstance(deps, dict):
        return None

    next_raw = deps.get("next")
    if not isinstance(next_raw, str):
        return None

    normalized = _normalize_version(next_raw)
    return normalized or None


def get_expected_next_swc_version(swc_dir_name: str) -> Optional[str]:
    """
    从已安装的 next/package.json 的 optionalDependencies 中读取 SWC 包的期望版本。

    说明：
    - Next 的 swc 包版本不一定与 next 自身版本相同（例如 next@14.2.35 可能依赖 swc@14.2.33）；
      因此这里以 optionalDependencies 为准，避免误判“缺少/版本不匹配”。
    """
    swc_name = (swc_dir_name or "").strip()
    if not swc_name:
        return None

    installed_next = _read_json(FRONTEND_DIR / "node_modules" / "next" / "package.json")
    if not isinstance(installed_next, dict):
        return None

    optional_deps = installed_next.get("optionalDependencies")
    if not isinstance(optional_deps, dict):
        return None

    raw = optional_deps.get(f"@next/{swc_name}")
    if not isinstance(raw, str):
        return None

    normalized = _normalize_version(raw)
    return normalized or None


def has_platform_swc_package() -> bool:
    """检查 node_modules 是否包含当前平台可用且版本匹配的 @next/swc 包。"""
    candidates = get_next_swc_candidates()
    if not candidates:
        return True

    base = FRONTEND_DIR / "node_modules" / "@next"

    for name in candidates:
        pkg_json = base / name / "package.json"
        if not pkg_json.exists():
            continue

        swc_pkg = _read_json(pkg_json)
        if not isinstance(swc_pkg, dict):
            continue

        swc_version = str(swc_pkg.get("version", "") or "").strip()
        expected_swc_version = get_expected_next_swc_version(name)

        # 无法确定期望版本时，只要包存在即可（避免误判阻断启动）。
        if not expected_swc_version:
            return True

        if not swc_version or swc_version == expected_swc_version:
            return True

    return False


def _has_command(name: str) -> bool:
    """检查命令是否可用（PATH + PATHEXT）。"""
    try:
        return shutil.which(name) is not None
    except Exception:
        return False


def _get_windows_cmd_exe() -> str:
    """尽量定位 cmd.exe，避免极端环境下 shell=True 抛 WinError 2。"""
    comspec = os.environ.get("COMSPEC")
    if comspec:
        try:
            p = Path(comspec)
            if p.exists():
                return str(p)
        except Exception:
            pass

    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    for candidate in (
        Path(system_root) / "System32" / "cmd.exe",
        Path(system_root) / "Sysnative" / "cmd.exe",
    ):
        try:
            if candidate.exists():
                return str(candidate)
        except Exception:
            pass

    which_cmd = shutil.which("cmd.exe") or shutil.which("cmd")
    return which_cmd or "cmd.exe"


def _ensure_node_npm_available() -> bool:
    """检查 Node.js/npm 是否可用；不可用时打印友好提示。"""
    # npm 在 Windows 上通常为 npm.cmd；which("npm") 也可能命中 npm.cmd（取决于 PATHEXT）
    has_node = _has_command("node")
    has_npm = _has_command("npm") or (sys.platform == "win32" and _has_command("npm.cmd"))

    if has_node and has_npm:
        return True

    print("  错误: 未检测到可用的 Node.js/npm，无法启动前端。")
    print("  解决方案:")
    print("    1) 安装 Node.js 18+（包含 npm）")
    print("    2) 重新打开命令行后确认命令可用：node -v && npm -v")
    print("    3) 在 frontend 目录执行：npm install")
    if sys.platform == "win32":
        print(r"    4) 或运行：frontend\scripts\repair-deps-win.bat（会清理并重装依赖）")
    return False


def kill_process_on_port(port: int) -> None:
    """终止占用指定端口的进程 (仅Windows)"""
    if sys.platform == "win32":
        windows_cmd = _get_windows_cmd_exe()
        try:
            # 查找占用端口的PID
            result = subprocess.run(
                f"netstat -ano | findstr :{port}",
                shell=True,
                executable=windows_cmd,
                capture_output=True,
                text=True
            )
            for line in result.stdout.strip().split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    subprocess.run(
                        f"taskkill /F /PID {pid}",
                        shell=True,
                        executable=windows_cmd,
                        capture_output=True,
                    )
                    print(f"  已终止占用端口 {port} 的进程 (PID: {pid})")
        except Exception:
            pass


def cleanup() -> None:
    """清理所有子进程"""
    global cleanup_done
    if cleanup_done:
        return
    cleanup_done = True

    print("\n正在关闭服务...")

    for proc in processes:
        if proc.poll() is None:  # 进程仍在运行
            try:
                if sys.platform == "win32":
                    # Windows: 使用 taskkill 终止进程树
                    windows_cmd = _get_windows_cmd_exe()
                    subprocess.run(
                        f"taskkill /F /T /PID {proc.pid}",
                        shell=True,
                        executable=windows_cmd,
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


def _wait_for_backend_http(proc: subprocess.Popen, port: int, timeout_seconds: int = 20) -> bool:
    """等待后端 HTTP 可访问（避免后端启动失败却继续启动前端）。"""
    url = f"http://127.0.0.1:{port}/api/v1/settings/version"
    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if int(getattr(resp, "status", 0) or 0) == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _read_process_output(proc: subprocess.Popen, max_chars: int = 8000) -> str:
    """读取子进程输出（用于启动失败时打印关键信息）。"""
    try:
        out, _ = proc.communicate(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            out, _ = proc.communicate(timeout=2)
        except Exception:
            return ""

    if out is None:
        return ""
    if isinstance(out, bytes):
        text = out.decode("utf-8", errors="replace")
    else:
        text = str(out)
    text = text.strip()
    if max_chars > 0 and len(text) > max_chars:
        return text[-max_chars:]
    return text


def start_backend(*, reload: bool = True) -> Optional[subprocess.Popen]:
    """启动 FastAPI 后端 (使用虚拟环境)"""
    print(f"启动 FastAPI 后端 (端口 {BACKEND_PORT})...")

    # 检查虚拟环境
    venv_python = get_venv_python()

    if not venv_python:
        print("  错误: 虚拟环境不存在或 Python 未安装")
        print(f"  请先运行: python install.py")
        return None

    # Windows 上 uvicorn.exe 的 launcher 偶发出现 “Failed to canonicalize script path”，
    # 这里统一改为 `python -m uvicorn`，绕过 exe launcher，兼容性更好。
    if not check_venv_import(venv_python, "uvicorn"):
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

    # 使用虚拟环境中的 uvicorn（通过 python -m）
    cmd = [
        str(venv_python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", str(BACKEND_PORT),
    ]
    if reload:
        cmd.append("--reload")

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

    if not _ensure_node_npm_available():
        return None
    windows_cmd = _get_windows_cmd_exe() if sys.platform == "win32" else None

    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print("  正在安装前端依赖...")
        try:
            if sys.platform == "win32":
                install_result = subprocess.run(
                    "npm install",
                    cwd=str(FRONTEND_DIR),
                    shell=True,
                    executable=windows_cmd,
                )
            else:
                install_result = subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR))
        except (FileNotFoundError, OSError) as e:
            # 极少数环境下（PATH/PATHEXT/COMSPEC 异常）可能直接抛 WinError 2/193 等，避免 traceback
            print(f"  错误: 无法执行 npm 安装依赖（{e}）")
            print("  请安装 Node.js 18+ 并确保 npm 在 PATH 中，然后重试。")
            return None
        if install_result.returncode != 0:
            print("  错误: 前端依赖安装失败，请手动执行 `cd frontend && npm install`")
            return None
    elif not has_platform_swc_package():
        print("  检测到当前平台缺少可用的 Next SWC 二进制，正在尝试修复依赖...")
        try:
            if sys.platform == "win32":
                install_result = subprocess.run(
                    "npm install",
                    cwd=str(FRONTEND_DIR),
                    shell=True,
                    executable=windows_cmd,
                )
            else:
                install_result = subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR))
        except (FileNotFoundError, OSError) as e:
            print(f"  错误: 无法执行 npm 修复依赖（{e}）")
            print("  请安装 Node.js 18+ 并确保 npm 在 PATH 中，然后重试。")
            return None
        if install_result.returncode != 0:
            print("  错误: 缺少当前平台 SWC 依赖，且自动修复失败")
            print("  请在 frontend 目录执行: npm install")
            return None
        if not has_platform_swc_package():
            print("  错误: 依赖修复后仍缺少当前平台 SWC 包")
            if sys.platform == "win32":
                print(r"  建议清理并重装：rmdir /s /q frontend\node_modules && cd frontend && npm install")
                print(r"  或直接运行：frontend\scripts\repair-deps-win.bat")
            else:
                print("  请清理 node_modules 后重新安装：rm -rf frontend/node_modules && cd frontend && npm install")
            return None

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
            executable=windows_cmd,
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


def stream_output(proc: subprocess.Popen, prefix: str, tail: Optional["list[str]"] = None) -> None:
    """流式输出进程日志（可选记录最近日志用于诊断/自愈）。"""
    if proc.stdout:
        for line in iter(proc.stdout.readline, b''):
            if line:
                try:
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        if tail is not None:
                            # 尽量不在这里做复杂结构：仅保存最近日志行（由调用方控制长度）
                            tail.append(text)
                            if len(tail) > 200:
                                del tail[: len(tail) - 200]
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
    # Windows 上 uvicorn --reload（watchfiles）偶发 “Failed to canonicalize script path” 直接退出；
    # 因此这里默认关闭热重载，避免“一键启动即退出”。如需开启可显式设置 BACKEND_RELOAD=true。
    backend_reload_default = sys.platform != "win32"
    backend_reload = _env_truthy("BACKEND_RELOAD", backend_reload_default)
    backend_proc = start_backend(reload=backend_reload)
    if not backend_proc:
        print("后端启动失败，退出")
        sys.exit(1)

    # 等待后端可访问（Windows 上 reload/launcher 偶发异常时自动降级到非 reload）
    ready = _wait_for_backend_http(backend_proc, BACKEND_PORT, timeout_seconds=20)
    if not ready and backend_proc.poll() is not None:
        out = _read_process_output(backend_proc)
        if "Failed to canonicalize script path" in out:
            print("  警告: 后端热重载启动失败（Windows 常见问题），将自动关闭 --reload 重试。")
            try:
                processes.remove(backend_proc)
            except Exception:
                pass
            backend_proc = start_backend(reload=False)
            if not backend_proc:
                print("后端启动失败，退出")
                sys.exit(1)
            ready = _wait_for_backend_http(backend_proc, BACKEND_PORT, timeout_seconds=20)
            if not ready and backend_proc.poll() is not None:
                out = _read_process_output(backend_proc)
        if not ready:
            if backend_proc.poll() is not None:
                if out:
                    print("[后端] 启动失败输出（末尾截断）:")
                    for line in out.splitlines()[-50:]:
                        print(f"[后端] {line}")
                print("后端启动失败，退出")
                sys.exit(1)
            else:
                print("  警告: 后端启动耗时较长，前端将继续启动；若页面无法访问请稍后重试或手动重启。")
    elif not ready:
        print("  警告: 后端启动耗时较长，前端将继续启动；若页面无法访问请稍后重试或手动重启。")

    frontend_proc = start_frontend()
    if not frontend_proc:
        print()
        print("=" * 50)
        print("前端启动失败（后端仍在运行）")
        print(f"  后端 API:  http://localhost:{BACKEND_PORT}")
        print(f"  API 文档:  http://localhost:{BACKEND_PORT}/docs")
        print()
        print("你可以手动启动前端：")
        print(f"  cd frontend && npm install && npm run dev -- --port {FRONTEND_PORT}")
        if sys.platform == "win32":
            print(r"  或运行：frontend\scripts\repair-deps-win.bat")
        print()
        print("按 Ctrl+C 停止后端服务")
        print("=" * 50)
        print()

        import threading

        backend_tail: List[str] = []
        backend_thread = threading.Thread(target=stream_output, args=(backend_proc, "后端", backend_tail), daemon=True)
        backend_thread.start()

        try:
            while True:
                if backend_proc.poll() is not None:
                    print("\n后端进程已退出")
                    tail_lines = backend_tail[-30:]
                    if tail_lines:
                        print("[后端] 最近日志（末尾截断）:")
                        for line in tail_lines:
                            print(f"[后端] {line}")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            cleanup()
        return

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

    backend_tail: List[str] = []
    frontend_tail: List[str] = []

    backend_thread = threading.Thread(target=stream_output, args=(backend_proc, "后端", backend_tail), daemon=True)
    frontend_thread = threading.Thread(target=stream_output, args=(frontend_proc, "前端", frontend_tail), daemon=True)

    backend_thread.start()
    frontend_thread.start()

    # 等待进程结束或用户中断
    try:
        backend_restart_attempts = 0
        while True:
            # 检查进程状态
            if backend_proc.poll() is not None:
                # 给日志线程一点时间把最后几行刷出来
                time.sleep(0.2)

                # Windows: uvicorn --reload/watchfiles 偶发 “Failed to canonicalize script path”
                # 该问题可能在启动后才触发；这里做一次自动自愈：关闭 reload 重启后端。
                if (
                    sys.platform == "win32"
                    and backend_restart_attempts < 1
                    and any("Failed to canonicalize script path" in line for line in backend_tail[-50:])
                ):
                    backend_restart_attempts += 1
                    print("\n后端因热重载异常退出，正在自动重启（关闭 --reload）...")
                    try:
                        processes.remove(backend_proc)
                    except Exception:
                        pass

                    backend_proc = start_backend(reload=False)
                    if not backend_proc:
                        print("后端重启失败，退出")
                        break

                    backend_tail.clear()
                    backend_thread = threading.Thread(
                        target=stream_output,
                        args=(backend_proc, "后端", backend_tail),
                        daemon=True,
                    )
                    backend_thread.start()

                    ready = _wait_for_backend_http(backend_proc, BACKEND_PORT, timeout_seconds=20)
                    if not ready:
                        print("后端重启后仍不可用，退出")
                        break

                    print("后端已重启")
                    continue

                print("\n后端进程已退出")
                # 输出最近日志末尾，便于定位（避免窗口一闪而过只看到“退出”）
                tail_lines = backend_tail[-30:]
                if tail_lines:
                    print("[后端] 最近日志（末尾截断）:")
                    for line in tail_lines:
                        print(f"[后端] {line}")
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
