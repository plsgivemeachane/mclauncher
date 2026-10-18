import subprocess
from pathlib import Path


def test_deb_builder_stages_minecraft_launcher_lib_version_metadata(tmp_path: Path) -> None:
    package_lib = Path(__file__).parents[1] / "packaging" / "stage-minecraft-launcher-lib-metadata.sh"
    build_lib = tmp_path / "venv" / "lib"
    source = build_lib / "python3.12" / "site-packages" / "minecraft_launcher_lib" / "version.txt"
    source.parent.mkdir(parents=True)
    source.write_text("8.0\n")
    rootfs = tmp_path / "rootfs"

    result = subprocess.run(
        ["sh", str(package_lib), str(build_lib), str(rootfs)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    destination = rootfs / "usr" / "lib" / "mclauncher" / "minecraft_launcher_lib" / "version.txt"
    assert destination.read_text() == "8.0\n"


def test_metadata_staging_fails_when_pinned_library_file_is_missing(tmp_path: Path) -> None:
    package_lib = Path(__file__).parents[1] / "packaging" / "stage-minecraft-launcher-lib-metadata.sh"
    build_lib = tmp_path / "venv" / "lib"
    build_lib.mkdir(parents=True)
    rootfs = tmp_path / "rootfs"

    result = subprocess.run(
        ["sh", str(package_lib), str(build_lib), str(rootfs)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "pinned minecraft-launcher-lib build is missing version.txt" in result.stderr
