from pathlib import Path


def test_deb_builder_stages_minecraft_launcher_lib_version_metadata() -> None:
    script = Path(__file__).parents[1] / "packaging" / "build-deb.sh"

    contents = script.read_text()

    assert "minecraft_launcher_lib/version.txt" in contents
    assert "/usr/lib/mclauncher/minecraft_launcher_lib/version.txt" in contents
