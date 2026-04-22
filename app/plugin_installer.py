from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlretrieve

from app.plugin_registry import get_plugin_info, remove_plugin_info

PLUGIN_INIT = "# user plugins package\n"


def ensure_user_plugin_dir(base_dir: str | Path) -> Path:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    init_file = base / "__init__.py"
    if not init_file.exists():
        init_file.write_text(PLUGIN_INIT, encoding="utf-8")
    return base


def install_dependencies(requirements_file: Path) -> None:
    if requirements_file.exists():
        subprocess.check_call(["python3", "-m", "pip", "install", "-r", str(requirements_file)])


def _install_from_local_path(src: Path, dst_root: Path) -> Path:
    if src.is_dir():
        dst = dst_root / src.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        install_dependencies(dst / "requirements.txt")
        return dst

    if src.suffix.lower() == ".py":
        dst = dst_root / src.name
        shutil.copy2(src, dst)
        return dst

    if src.suffix.lower() == ".zip":
        extract_dir = dst_root / src.stem
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(extract_dir)
        install_dependencies(extract_dir / "requirements.txt")
        return extract_dir

    raise ValueError("unsupported plugin source, expected directory/.py/.zip")


def install_plugin(source: str | Path, target_dir: str | Path) -> Path:
    dst_root = ensure_user_plugin_dir(target_dir)

    if isinstance(source, str) and urlparse(source).scheme in {"http", "https"}:
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(urlparse(source).path).name or "plugin.py"
            tmp_path = Path(tmpdir) / filename
            urlretrieve(source, tmp_path)
            return _install_from_local_path(tmp_path, dst_root)

    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"plugin source not found: {src}")
    return _install_from_local_path(src, dst_root)


def uninstall_plugin(plugin_name: str, target_dir: str | Path) -> bool:
    dst_root = ensure_user_plugin_dir(target_dir)
    info = get_plugin_info(plugin_name)

    candidates = []
    module_name = info.get("module")
    if module_name:
        candidates.append(dst_root / f"{module_name}.py")
        candidates.append(dst_root / module_name)
    candidates.append(dst_root / f"{plugin_name}.py")
    candidates.append(dst_root / plugin_name)

    removed = False
    for path in candidates:
        if path.is_file():
            path.unlink()
            removed = True
        elif path.is_dir():
            shutil.rmtree(path)
            removed = True

    if removed:
        remove_plugin_info(plugin_name)
    return removed
