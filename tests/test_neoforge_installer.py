from pathlib import Path

from mclauncher.installer import MinecraftInstaller


class _Loader:
    def __init__(self):
        self.calls = []

    def get_loader_versions(self, game, stable_only):
        assert game == "1.21.1"
        assert stable_only is False
        return ["21.1.176"]

    def install(self, game, directory, *, loader_version, callback):
        self.calls.append((game, Path(directory), loader_version, callback))
        callback["setStatus"]("Running installer")
        return "neoforge-21.1.176"


def test_neoforge_requires_exact_game_loader_pair_and_records_launch_profile(monkeypatch, tmp_path):
    loader = _Loader()
    monkeypatch.setattr("mclauncher.installer.mod_loader.get_mod_loader", lambda name: loader)
    monkeypatch.setattr(MinecraftInstaller, "_validate_installation", staticmethod(lambda *_args: None))
    installer = MinecraftInstaller()

    assert installer.resolve_loader("1.21.1", "neoforge", "21.1.176")["loader"] == "neoforge"
    assert installer.resolve_loader("1.21.1", "neoforge", "21.1.175") is None

    instance = {"version": "1.21.1"}
    progress = []
    installer.install_modpack(instance, tmp_path, {"loader": "neoforge", "game_version": "1.21.1", "loader_version": "21.1.176"},
                              lambda *event: progress.append(event))

    assert instance["launch_version"] == "neoforge-21.1.176"
    assert loader.calls[0][:3] == ("1.21.1", tmp_path, "21.1.176")
    assert progress == [("Running installer", -1, -1)]

