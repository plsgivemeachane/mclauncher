import shutil
import subprocess
from pathlib import Path

import pytest

from mclauncher.installer import MinecraftPlayer, offline_session_agent_path

AGENT = Path(__file__).parents[1] / "src" / "mclauncher" / "assets" / "offline-session-agent.jar"

# Stands in for the game: asks for the session host the agent configured and
# reports a server join the way authlib does.
PROBE = """
import java.net.*;
public class Probe {
    public static void main(String[] args) throws Exception {
        String host = System.getProperty("minecraft.api.session.host");
        System.out.println("services=" + System.getProperty("minecraft.api.services.host"));
        System.out.println("host=" + host);
        HttpURLConnection c = (HttpURLConnection) new URL(host + "/session/minecraft/join").openConnection();
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/json");
        c.getOutputStream().write("{\\"accessToken\\":\\"\\"}".getBytes("UTF-8"));
        System.out.println("join=" + c.getResponseCode());
    }
}
"""


def test_agent_jar_is_bundled():
    assert AGENT.is_file()
    assert offline_session_agent_path() == AGENT


def test_build_command_loads_agent(tmp_path, monkeypatch):
    import minecraft_launcher_lib

    minecraft_directory = tmp_path / "minecraft"
    version_root = minecraft_directory / "versions" / "1.20.4"
    version_root.mkdir(parents=True)
    (version_root / "1.20.4.json").write_text("{}", encoding="utf-8")
    (version_root / "1.20.4.jar").write_bytes(b"jar")
    executable = tmp_path / "java"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    captured = {}
    monkeypatch.setattr(minecraft_launcher_lib.runtime, "get_version_runtime_information",
                        lambda *_: {"name": "managed-java"})
    monkeypatch.setattr(minecraft_launcher_lib.runtime, "get_executable_path", lambda *_: str(executable))
    monkeypatch.setattr(minecraft_launcher_lib.command, "get_minecraft_command",
                        lambda _v, _d, options: captured.setdefault("options", options) and ["java"])

    MinecraftPlayer().build_command({"version": "1.20.4"}, minecraft_directory, "Alex", "uuid")

    assert captured["options"]["jvmArguments"] == [f"-javaagent:{AGENT}"]
    assert captured["options"]["token"] == ""


@pytest.mark.skipif(not (shutil.which("java") and shutil.which("javac")), reason="needs a JDK")
@pytest.mark.parametrize("jvm_flags", [
    [],
    # Forge 1.20.x adds this flag; it makes the default loopback ::1.
    ["-Djava.net.preferIPv6Addresses=system"],
    ["-Djava.net.preferIPv6Addresses=true"],
], ids=["default", "forge-ipv6-system", "ipv6-true"])
def test_agent_accepts_join_and_lets_game_exit(tmp_path, jvm_flags):
    (tmp_path / "Probe.java").write_text(PROBE, encoding="utf-8")
    subprocess.run(["javac", "Probe.java"], cwd=tmp_path, check=True)

    # The timeout also proves the relay's threads do not keep the JVM alive.
    result = subprocess.run(
        ["java", *jvm_flags, f"-javaagent:{AGENT}", "-cp", ".", "Probe"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "host=http://127.0.0.1:" in result.stdout
    assert "services=http://127.0.0.1:" in result.stdout
    assert result.stdout.split("services=")[1].split()[0].endswith("/services")
    assert "join=204" in result.stdout


# Stands in for authlib's startup key fetch: GET <services host>/publickeys.
KEYS_PROBE = """
import java.io.*;
import java.net.*;
public class KeysProbe {
    public static void main(String[] args) throws Exception {
        String host = System.getProperty("minecraft.api.services.host");
        HttpURLConnection c = (HttpURLConnection) new URL(host + "/publickeys").openConnection();
        System.out.println("status=" + c.getResponseCode());
        BufferedReader in = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"));
        StringBuilder body = new StringBuilder();
        for (String line; (line = in.readLine()) != null;) body.append(line);
        System.out.println("body=" + body);
    }
}
"""


@pytest.mark.skipif(not (shutil.which("java") and shutil.which("javac")), reason="needs a JDK")
def test_agent_serves_bundled_public_keys_when_services_unreachable(tmp_path):
    """A failed key fetch leaves signed chat unverifiable and gets the player kicked."""
    (tmp_path / "KeysProbe.java").write_text(KEYS_PROBE, encoding="utf-8")
    subprocess.run(["javac", "KeysProbe.java"], cwd=tmp_path, check=True)

    result = subprocess.run(
        ["java", "-Dmclauncher.agent.servicesUpstream=http://127.0.0.1:1",
         f"-javaagent:{AGENT}", "-cp", ".", "KeysProbe"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "status=200" in result.stdout
    assert "profilePropertyKeys" in result.stdout
    assert "playerCertificateKeys" in result.stdout
    assert "using bundled keys" in result.stderr
