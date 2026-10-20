import json
import zipfile
from pathlib import Path

import pytest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from mclauncher.optifine import OptiFineCompatibility, OptiFineInstaller, UnsupportedOptiFine, inspect_optifine_jar
from mclauncher.app import LauncherWindow


def _jar(path: Path, version: str = "1.20.1_HD_U_I6") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("net/optifine/Config.class", b"class")
        archive.writestr("META-INF/MANIFEST.MF", f"Implementation-Version: {version}\n")
    return path


def _base(root: Path, game: str = "1.20.1") -> None:
    version_root = root / "versions" / game
    version_root.mkdir(parents=True)
    (version_root / f"{game}.json").write_text(json.dumps({"id": game}), encoding="utf-8")
    (version_root / f"{game}.jar").write_bytes(b"minecraft")


def test_local_jar_is_prepared_as_verified_standalone_profile(tmp_path):
    root = tmp_path / "minecraft"
    _base(root)
    jar = _jar(tmp_path / "OptiFine_1.20.1_HD_U_I6.jar")
    installer = OptiFineInstaller({("1.20.1", "1.20.1_HD_U_I6"): OptiFineCompatibility("1.20.1", "1.20.1_HD_U_I6")})
    instance = {"minecraft_version": "1.20.1"}

    result = installer.prepare(instance, root, jar)

    assert result["loader"] == "vanilla"
    assert instance["launch_version"] == "1.20.1-OptiFine-1.20.1_HD_U_I6"
    assert (root / "versions" / instance["launch_version"] / f"{instance['launch_version']}.jar").is_file()


def test_forge_requires_exact_published_pair(tmp_path):
    root = tmp_path / "minecraft"
    jar = _jar(tmp_path / "OptiFine_1.20.1_HD_U_I6.jar")
    installer = OptiFineInstaller({("1.20.1", "1.20.1_HD_U_I6"): {"forge_version": "47.2.0"}})
    instance = {"minecraft_version": "1.20.1", "loader": "forge", "loader_version": "47.3.0"}

    with pytest.raises(UnsupportedOptiFine, match="not verified"):
        installer.prepare(instance, root, jar)


def test_unknown_loader_is_rejected_without_touching_instance(tmp_path):
    jar = _jar(tmp_path / "OptiFine_1.20.1_HD_U_I6.jar")
    installer = OptiFineInstaller({("1.20.1", "1.20.1_HD_U_I6"): {}})
    instance = {"minecraft_version": "1.20.1", "loader": "fabric"}

    with pytest.raises(UnsupportedOptiFine, match="only supported"):
        installer.prepare(instance, tmp_path / "minecraft", jar)
    assert not (tmp_path / "minecraft").exists()


def test_malformed_local_jar_is_rejected(tmp_path):
    path = tmp_path / "not-optifine.jar"
    path.write_bytes(b"no")
    with pytest.raises(ValueError, match="could not be read"):
        inspect_optifine_jar(path)


def test_default_exact_official_optifine_pair_is_available(tmp_path):
    jar = _jar(tmp_path / "OptiFine_1.21.11_HD_U_J9.jar", "1.21.11_HD_U_J9")
    instance = {"minecraft_version": "1.21.11"}
    root = tmp_path / "minecraft"
    _base(root, "1.21.11")
    result = OptiFineInstaller().prepare(instance, root, jar)
    assert result["optifine_version"] == "1.21.11_HD_U_J9"


def test_window_prepares_selected_local_optifine_and_reports_failure(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    jar = _jar(tmp_path / "OptiFine_1.20.1_HD_U_I6.jar")

    class Installer:
        def prepare(self, instance, directory, selected, on_progress=None):
            assert selected == jar
            return {"optifine_version": "1.20.1_HD_U_I6", "launch_version": "1.20.1-OptiFine"}

    class Player:
        @staticmethod
        def is_ready(instance, directory):
            return True

    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(jar), "OptiFine jars (*.jar)"),
    )
    window = LauncherWindow(data_root=tmp_path / "data", optifine_installer=Installer(), player=Player())
    window.instance_name_input.setText("OptiFine test")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance.update({"minecraft_version": "1.20.1", "version": "1.20.1", "ready": True})
    window._install_local_optifine()
    application.processEvents()
    assert instance["ready"] is True
    assert instance["optifine_version"] == "1.20.1_HD_U_I6"
    window.close()


def test_window_keeps_incompatible_optifine_failed_and_retryable(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    jar = _jar(tmp_path / "OptiFine_1.20.1_HD_U_I6.jar")

    class Installer:
        def prepare(self, *args, **kwargs):
            raise UnsupportedOptiFine("OptiFine is not verified for Forge 47.3.0")

    monkeypatch.setattr(
        "mclauncher.app.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(jar), "OptiFine jars (*.jar)"),
    )
    window = LauncherWindow(data_root=tmp_path / "data", optifine_installer=Installer())
    window.instance_name_input.setText("Forge test")
    window.create_instance_button.click()
    instance = window.state["instances"][0]
    instance.update({"minecraft_version": "1.20.1", "loader": "forge", "loader_version": "47.3.0"})
    window._install_local_optifine()
    application.processEvents()
    assert instance["ready"] is False
    assert instance["install_state"] == "failed"
    assert "not verified" in instance["install_error"]
    window.close()
