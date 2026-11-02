"""The AI-client demos pass the safety settings through to the spawned MCP server.

No network and no orders: the "server" is replaced by a probe that prints the
SafetySettings it ends up with, launched with the bridge's own parameters.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import subprocess
import sys
from types import ModuleType

import conftest as conf
import pytest
from mcp.client.stdio import get_default_environment

BRIDGE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "examples"
    / "mcp"
    / "ai_client"
    / "_mcp_bridge.py"
)

PROBE = (
    "import json; from younit.mcp_server.safety import SafetySettings as S; s = S(); "
    "print(json.dumps([s.readonly, s.max_order_value_egp, s.max_daily_orders]))"
)

DEMO_VARS = (
    "TRADING_ID",
    "API_KEY",
    "EFG_LOG_LEVEL",
    "EFG_SIMULATION",
    "EFG_MCP_READONLY",
    "EFG_MCP_MAX_ORDER_VALUE_EGP",
    "EFG_MCP_MAX_DAILY_ORDERS",
    "OPENAI_API_KEY",
)


@pytest.fixture
def bridge() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_mcp_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def clean_demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in DEMO_VARS:
        monkeypatch.delenv(name, raising=False)


ROOT_ENV_EXAMPLE = BRIDGE_PATH.parents[3] / ".env.example"
AI_CLIENT_ENV_EXAMPLE = BRIDGE_PATH.parent / ".env.example"


class TestEnvExample:
    @pytest.mark.parametrize("path", [ROOT_ENV_EXAMPLE, AI_CLIENT_ENV_EXAMPLE])
    def test_both_files_have_the_limits_commented_out_and_no_simulation(
        self, path: pathlib.Path
    ) -> None:
        lines = path.read_text(encoding="utf-8").splitlines()
        for name in ("EFG_MCP_MAX_ORDER_VALUE_EGP", "EFG_MCP_MAX_DAILY_ORDERS"):
            assert any(line.startswith(f"# {name}=") for line in lines), name
            assert not any(line.startswith(f"{name}=") for line in lines), name
        assert "EFG_SIMULATION" not in "\n".join(lines)

    def test_root_file_documents_readonly_as_a_commented_line(self) -> None:
        lines = ROOT_ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        assert "# EFG_MCP_READONLY=true" in lines
        assert not any(line.startswith("EFG_MCP_READONLY=") for line in lines)

    def test_ai_client_file_does_not_mention_readonly_setting(self) -> None:
        # The demos decide read-only vs trading with READ_ONLY in _mcp_bridge.py.
        text = AI_CLIENT_ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "EFG_MCP_READONLY" not in text


class TestBuildServerEnv:
    def test_forwards_set_variables(self, bridge: ModuleType) -> None:
        source = {
            "TRADING_ID": conf.FAKE_TRADING_ID,
            "API_KEY": conf.FAKE_API_KEY,
            "EFG_LOG_LEVEL": "WARNING",
            "EFG_MCP_MAX_ORDER_VALUE_EGP": "250",
            "EFG_MCP_MAX_DAILY_ORDERS": "5",
        }
        env = bridge.build_server_env(source)
        assert env == {**source, "EFG_MCP_READONLY": "true"}

    def test_unset_and_empty_variables_are_not_forwarded(self, bridge: ModuleType) -> None:
        env = bridge.build_server_env({"EFG_MCP_MAX_DAILY_ORDERS": "  ", "EFG_LOG_LEVEL": ""})
        assert env == {"EFG_MCP_READONLY": "true"}

    @pytest.mark.parametrize("value", ["false", "FALSE", "true", "0", "no", ""])
    def test_readonly_in_the_environment_never_changes_the_result(
        self, bridge: ModuleType, value: str
    ) -> None:
        env = bridge.build_server_env({"EFG_MCP_READONLY": value})
        assert env["EFG_MCP_READONLY"] == "true"  # READ_ONLY is True

    @pytest.mark.parametrize("value", ["true", "false", "0", ""])
    def test_readonly_in_the_environment_never_changes_the_result_when_trading(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setattr(bridge, "READ_ONLY", False)
        env = bridge.build_server_env({"EFG_MCP_READONLY": value})
        assert env["EFG_MCP_READONLY"] == "false"

    def test_other_variables_are_not_forwarded(self, bridge: ModuleType) -> None:
        env = bridge.build_server_env({"OPENAI_API_KEY": "unrelated", "EFG_DEBUG": "true"})
        assert set(env) == {"EFG_MCP_READONLY"}

    def test_proxy_settings_are_forwarded(self, bridge: ModuleType) -> None:
        env = bridge.build_server_env({"HTTPS_PROXY": "http://proxy.test:8080"})
        assert env["HTTPS_PROXY"] == "http://proxy.test:8080"

    def test_server_runs_in_the_ai_client_directory(self, bridge: ModuleType) -> None:
        assert pathlib.Path(bridge.server_parameters().cwd) == BRIDGE_PATH.parent


class TestSimulationCheck:
    MESSAGE = (
        "EFG_SIMULATION is temporarily disabled in this version while simulation mode "
        "is being verified. Remove EFG_SIMULATION to continue."
    )

    @staticmethod
    def _connect(bridge: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[object]:
        """Run connect_to_server with a stub in place of the real server launch."""
        started: list[object] = []

        def fake_stdio_client(params: object, errlog: object = None) -> None:
            started.append(params)
            raise RuntimeError("stop before spawning anything")

        monkeypatch.setattr(bridge, "stdio_client", fake_stdio_client)

        async def attempt() -> None:
            async with bridge.connect_to_server():
                pass

        with pytest.raises(RuntimeError, match="stop before spawning"):
            asyncio.run(attempt())
        return started

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on", " true ", "x"])
    def test_simulation_requested_exits_without_starting_the_server(
        self,
        bridge: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        value: str,
    ) -> None:
        monkeypatch.setenv("EFG_SIMULATION", value)
        started: list[object] = []
        monkeypatch.setattr(bridge, "stdio_client", lambda *a, **k: started.append(a))

        async def attempt() -> None:
            async with bridge.connect_to_server():
                pass

        with pytest.raises(SystemExit) as exc_info:
            asyncio.run(attempt())
        assert exc_info.value.code == 1
        assert started == []
        captured = capsys.readouterr()
        assert captured.err.strip() == self.MESSAGE
        assert captured.out == ""

    def test_message_matches_the_sdk(self, bridge: ModuleType) -> None:
        from younit.config import Settings

        with pytest.raises(Exception, match="EFG_SIMULATION") as exc_info:
            Settings(trading_id=conf.FAKE_TRADING_ID, api_key=conf.FAKE_API_KEY, simulation=True)
        assert exc_info.value.message == bridge.SIMULATION_DISABLED_MESSAGE == self.MESSAGE

    @pytest.mark.parametrize("value", [None, "", "false", "FALSE", " False ", "0", "no", "NO"])
    def test_unset_or_off_values_start_normally(
        self,
        bridge: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        value: str | None,
    ) -> None:
        if value is not None:
            monkeypatch.setenv("EFG_SIMULATION", value)
        assert len(self._connect(bridge, monkeypatch)) == 1
        assert self.MESSAGE not in capsys.readouterr().err

    def test_set_value_is_forwarded_to_the_server(self, bridge: ModuleType) -> None:
        env = bridge.build_server_env({"EFG_SIMULATION": "false"})
        assert env["EFG_SIMULATION"] == "false"

    def test_unset_value_is_not_forwarded(self, bridge: ModuleType) -> None:
        assert "EFG_SIMULATION" not in bridge.build_server_env({})
        assert "EFG_SIMULATION" not in bridge.build_server_env({"EFG_SIMULATION": ""})


class TestReadOnlySwitch:
    def test_default_is_read_only(self, bridge: ModuleType) -> None:
        assert bridge.READ_ONLY is True
        assert bridge.build_server_env({})["EFG_MCP_READONLY"] == "true"

    def test_false_gives_the_server_readonly_false(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bridge, "READ_ONLY", False)
        assert bridge.build_server_env({})["EFG_MCP_READONLY"] == "false"
        assert bridge.server_parameters().env["EFG_MCP_READONLY"] == "false"

    def test_constant_is_documented_right_after_the_imports(self) -> None:
        source = BRIDGE_PATH.read_text(encoding="utf-8")
        assert (
            "from mcp.client.stdio import stdio_client\n\n"
            "# Safety switch for all AI client demos.\n"
            "# True  = the AI can only read (quotes, portfolio, history...).\n"
            "# False = the AI can place, amend and cancel REAL orders on your account.\n"
            "READ_ONLY = True\n"
        ) in source

    def test_no_warning_when_read_only(
        self, bridge: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bridge.warn_if_trading_enabled()
        captured = capsys.readouterr()
        assert captured.out == "" and captured.err == ""

    def test_warning_is_printed_when_not_read_only(
        self,
        bridge: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(bridge, "READ_ONLY", False)
        bridge.warn_if_trading_enabled()
        assert capsys.readouterr().err.strip() == (
            "WARNING: READ_ONLY is False in _mcp_bridge.py. The AI can place, amend and cancel "
            "REAL orders on your account. The per-order value cap (EFG_MCP_MAX_ORDER_VALUE_EGP) "
            "and the daily limit (EFG_MCP_MAX_DAILY_ORDERS) still apply."
        )

    @pytest.mark.parametrize(("read_only", "warned"), [(True, False), (False, True)])
    def test_warning_comes_before_connecting(
        self,
        bridge: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        read_only: bool,
        warned: bool,
    ) -> None:
        monkeypatch.setattr(bridge, "READ_ONLY", read_only)
        seen_at_connect: list[str] = []

        def fake_stdio_client(params: object, errlog: object = None) -> None:
            seen_at_connect.append(capsys.readouterr().err)  # what was printed so far
            raise RuntimeError("stop before spawning anything")

        monkeypatch.setattr(bridge, "stdio_client", fake_stdio_client)

        async def attempt() -> None:
            async with bridge.connect_to_server():
                pass

        with pytest.raises(RuntimeError, match="stop before spawning"):
            asyncio.run(attempt())
        assert len(seen_at_connect) == 1
        assert ("READ_ONLY is False" in seen_at_connect[0]) is warned

    def test_system_prompt_note_follows_the_switch(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert "read-only" in bridge.mode_note_for_system_prompt()
        monkeypatch.setattr(bridge, "READ_ONLY", False)
        note = bridge.mode_note_for_system_prompt()
        assert "read-only" not in note and "REAL account" in note


class TestSettingsReachTheServer:
    def _server_safety_settings(
        self, bridge: ModuleType, cwd: pathlib.Path | None = None
    ) -> list[object]:
        params = bridge.server_parameters()
        result = subprocess.run(  # noqa: S603 - fixed argv: this interpreter running a constant probe
            [sys.executable, "-c", PROBE],
            env={**get_default_environment(), **params.env},
            cwd=cwd or params.cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return json.loads(result.stdout)

    def test_values_set_in_the_environment_reach_safety_settings(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "250")
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "5")
        readonly, max_value, max_daily = self._server_safety_settings(bridge)
        assert (readonly, max_value, max_daily) == (True, 250, 5)

    def test_zero_disables_limits_in_the_server(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "0")
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "0")
        _, max_value, max_daily = self._server_safety_settings(bridge)
        assert (max_value, max_daily) == (0, 0)

    def test_server_stays_readonly_even_if_the_caller_asks_for_writes(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", "false")
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "250")
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "5")
        readonly, _, _ = self._server_safety_settings(bridge)
        assert readonly is True

    def test_dotenv_readonly_never_overrides_the_switch(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        # A .env in the server's working directory says "false"; READ_ONLY=True wins.
        (tmp_path / ".env").write_text("EFG_MCP_READONLY=false\n", encoding="utf-8")
        assert self._server_safety_settings(bridge, cwd=tmp_path)[0] is True

        # ...and the other way round: .env says "true", READ_ONLY=False wins.
        (tmp_path / ".env").write_text("EFG_MCP_READONLY=true\n", encoding="utf-8")
        monkeypatch.setattr(bridge, "READ_ONLY", False)
        assert self._server_safety_settings(bridge, cwd=tmp_path)[0] is False

    def test_switch_false_reaches_safety_settings(
        self, bridge: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bridge, "READ_ONLY", False)
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "250")
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "5")
        assert self._server_safety_settings(bridge) == [False, 250, 5]
