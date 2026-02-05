#!/usr/bin/env python
"""
一键安装依赖脚本
使用 uv 管理 Python 依赖，npm 管理前端依赖
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.absolute()
FRONTEND_DIR = ROOT_DIR / "frontend"

# 颜色输出 (Windows 支持)
if sys.platform == "win32":
    os.system("")  # 启用 ANSI 转义序列


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_step(msg: str) -> None:
    print(f"\n{Colors.BLUE}{Colors.BOLD}[步骤]{Colors.RESET} {msg}")


def print_success(msg: str) -> None:
    print(f"{Colors.GREEN}  ✓ {msg}{Colors.RESET}")


def print_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}  ! {msg}{Colors.RESET}")


def print_error(msg: str) -> None:
    print(f"{Colors.RED}  ✗ {msg}{Colors.RESET}")


def run_cmd(cmd: str, cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    """执行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True
        )
        if check and result.returncode != 0:
            print_error(f"命令执行失败: {cmd}")
            if result.stderr:
                print(f"    {result.stderr[:500]}")
        return result
    except Exception as e:
        print_error(f"执行异常: {e}")
        return None


def check_command(cmd: str) -> bool:
    """检查命令是否可用"""
    return shutil.which(cmd) is not None


def install_uv() -> bool:
    """安装 uv 包管理器"""
    print_step("检查 uv 包管理器")

    if check_command("uv"):
        result = run_cmd("uv --version", check=False)
        if result and result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"uv 已安装 ({version})")
            return True

    print_warning("uv 未安装，正在安装...")

    if sys.platform == "win32":
        # Windows: 使用 PowerShell 安装
        cmd = 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    else:
        # Unix: 使用 curl 安装
        cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"

    result = run_cmd(cmd, check=False)

    # 安装后可能需要刷新 PATH
    if sys.platform == "win32":
        # 添加常见的 uv 安装路径到环境变量
        uv_paths = [
            Path.home() / ".cargo" / "bin",
            Path.home() / ".local" / "bin",
            Path(os.environ.get("LOCALAPPDATA", "")) / "uv",
        ]
        for p in uv_paths:
            if p.exists():
                os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")

    # 验证安装
    if check_command("uv"):
        print_success("uv 安装成功")
        return True
    else:
        print_error("uv 安装失败，请手动安装: https://docs.astral.sh/uv/")
        return False


def install_python_deps() -> bool:
    """使用 uv 安装 Python 依赖到虚拟环境"""
    print_step("安装 Python 依赖")

    requirements_file = ROOT_DIR / "requirements.txt"
    if not requirements_file.exists():
        print_error(f"requirements.txt 不存在: {requirements_file}")
        return False

    # 创建虚拟环境 (如果不存在)
    venv_dir = ROOT_DIR / ".venv"
    if not venv_dir.exists():
        print_warning("创建虚拟环境...")

        # 优先使用 uv 创建虚拟环境
        if check_command("uv"):
            result = run_cmd("uv venv", cwd=ROOT_DIR, check=False)
        else:
            # 回退到 python -m venv
            result = run_cmd(f"{sys.executable} -m venv .venv", cwd=ROOT_DIR, check=False)

        if result and result.returncode == 0:
            print_success("虚拟环境已创建")
        else:
            print_error("虚拟环境创建失败")
            return False

    # 获取虚拟环境 Python 路径
    if sys.platform == "win32":
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        python_path = venv_dir / "bin" / "python"

    if not python_path.exists():
        print_error(f"虚拟环境 Python 不存在: {python_path}")
        return False

    print_success(f"使用虚拟环境: {venv_dir}")

    # 使用 uv pip 安装依赖
    print_warning("正在安装 Python 依赖...")

    if check_command("uv"):
        cmd = f"uv pip install -r requirements.txt --python \"{python_path}\""
        result = run_cmd(cmd, cwd=ROOT_DIR, check=False)

        if result and result.returncode == 0:
            print_success("Python 依赖安装成功 (uv)")
            return True
        else:
            print_warning("uv 安装失败，尝试使用 pip...")

    # 回退到虚拟环境中的 pip
    cmd = f"\"{python_path}\" -m pip install -r requirements.txt"
    result = run_cmd(cmd, cwd=ROOT_DIR, check=False)

    if result and result.returncode == 0:
        print_success("Python 依赖安装成功 (pip)")
        return True

    print_error("Python 依赖安装失败")
    return False


def install_frontend_deps() -> bool:
    """安装前端依赖"""
    print_step("安装前端依赖 (Node.js)")

    if not FRONTEND_DIR.exists():
        print_warning(f"前端目录不存在: {FRONTEND_DIR}")
        return True  # 不视为错误

    package_json = FRONTEND_DIR / "package.json"
    if not package_json.exists():
        print_warning("package.json 不存在，跳过前端依赖安装")
        return True

    # 检查 npm
    if not check_command("npm"):
        print_error("npm 未安装，请先安装 Node.js")
        return False

    # 检查 node_modules
    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        print_success("前端依赖已安装")
        return True

    print_warning("正在安装前端依赖...")

    # 使用 PowerShell 执行 npm (Windows 兼容性更好)
    if sys.platform == "win32":
        cmd = f'powershell -Command "cd \'{FRONTEND_DIR}\'; npm install"'
    else:
        cmd = "npm install"

    result = run_cmd(cmd, cwd=FRONTEND_DIR, check=False)

    if result and result.returncode == 0:
        print_success("前端依赖安装成功")
        return True
    else:
        print_error("前端依赖安装失败")
        return False


def install_playwright() -> bool:
    """安装 Playwright 浏览器 (可选，使用虚拟环境)"""
    print_step("安装 Playwright 浏览器 (可选)")

    # 获取虚拟环境 Python
    venv_dir = ROOT_DIR / ".venv"
    if sys.platform == "win32":
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        python_path = venv_dir / "bin" / "python"

    if not python_path.exists():
        print_warning("虚拟环境不存在，跳过 Playwright 浏览器安装")
        return True

    # 检查 playwright 是否已安装
    result = run_cmd(f"\"{python_path}\" -c \"import playwright\"", check=False)
    if result and result.returncode != 0:
        print_warning("Playwright 未安装，跳过浏览器安装")
        return True

    print_warning("正在安装 Playwright 浏览器...")
    result = run_cmd(f"\"{python_path}\" -m playwright install chromium", check=False)

    if result and result.returncode == 0:
        print_success("Playwright 浏览器安装成功")
        return True
    else:
        print_warning("Playwright 浏览器安装失败 (非必需)")
        return True


def create_env_file() -> None:
    """创建 .env 文件 (如果不存在)"""
    print_step("检查环境配置")

    env_file = ROOT_DIR / ".env"
    env_example = ROOT_DIR / ".env.example"

    if env_file.exists():
        print_success(".env 文件已存在")
        return

    if env_example.exists():
        shutil.copy(env_example, env_file)
        print_success("已从 .env.example 创建 .env 文件")
        print_warning("请编辑 .env 文件配置必要的环境变量")
    else:
        print_warning(".env.example 不存在，跳过")


def main() -> None:
    """主函数"""
    print(f"{Colors.BOLD}")
    print("=" * 50)
    print("Stock Recon - 一键安装依赖")
    print("=" * 50)
    print(f"{Colors.RESET}")

    success = True

    # 1. 安装 uv
    if not install_uv():
        print_warning("继续使用 pip 安装...")

    # 2. 安装 Python 依赖
    if not install_python_deps():
        success = False

    # 3. 安装前端依赖
    if not install_frontend_deps():
        success = False

    # 4. 安装 Playwright (可选)
    install_playwright()

    # 5. 创建 .env 文件
    create_env_file()

    # 完成
    print()
    print("=" * 50)
    if success:
        print(f"{Colors.GREEN}{Colors.BOLD}依赖安装完成!{Colors.RESET}")
        print()
        print("启动方式:")
        print(f"  python start.py")
        print(f"  或双击 start.bat")
    else:
        print(f"{Colors.RED}{Colors.BOLD}部分依赖安装失败，请检查上方错误信息{Colors.RESET}")
    print("=" * 50)


if __name__ == "__main__":
    main()
