import pytest

from netpilot_mcp.session_manager import SessionManager


def test_internal_to_netmiko_mapping():
    sm = SessionManager()
    assert sm._internal_to_netmiko("cisco_ios", "ssh") == "cisco_ios"
    assert sm._internal_to_netmiko("cisco_ios", "telnet") == "cisco_ios_telnet"
    assert sm._internal_to_netmiko("huawei_vrp", "ssh") == "huawei"
    assert sm._internal_to_netmiko("h3c_comware", "telnet") == "hp_comware_telnet"
    assert sm._internal_to_netmiko("unknown", "ssh") == "generic"


def test_netmiko_to_internal_mapping():
    sm = SessionManager()
    assert sm._netmiko_to_internal("cisco_ios") == "cisco_ios"
    assert sm._netmiko_to_internal("cisco_ios_telnet") == "cisco_ios"
    assert sm._netmiko_to_internal("huawei") == "huawei_vrp"
    assert sm._netmiko_to_internal("hp_comware_telnet") == "h3c_comware"
    assert sm._netmiko_to_internal("ruijie_os") == "ruijie_rgos"
    assert sm._netmiko_to_internal("something_else") == "generic"


@pytest.mark.asyncio
async def test_telnet_disabled_by_policy(monkeypatch):
    monkeypatch.setenv("NETPILOT_ALLOW_TELNET", "false")
    sm = SessionManager()
    with pytest.raises(PermissionError):
        await sm.create_session(
            host="127.0.0.1",
            port=23,
            protocol="telnet",
            username="x",
            password="x",
            device_type="cisco_ios",
            timeout=1000,
        )
