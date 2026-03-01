from netpilot_mcp.utils.structured_output import StructuredOutputParser


def test_parse_show_ip_interface_brief():
    raw = """Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     10.0.0.1        YES manual up                    up
GigabitEthernet0/1     unassigned      YES unset  administratively down down
"""
    result = StructuredOutputParser.parse("show ip interface brief", raw, device_type="cisco_ios")
    assert result.status == "ok"
    assert result.data["count"] >= 1
    # NTC 命中时优先使用 ntc_templates，否则回退手写 parser
    assert result.parser in {"show_ip_interface_brief", "ntc_templates.cisco_ios"}


def test_parse_show_version():
    raw = """RT01 uptime is 2 weeks, 3 days
Cisco IOS Software, C800 Software (C800-UNIVERSALK9-M), Version 15.4(3)M3, RELEASE SOFTWARE (fc2)
Processor board ID FTX1234ABC
cisco C800 (MPC8300) processor (revision 1.0) with 236544K/25600K bytes of memory.
"""
    result = StructuredOutputParser.parse("show version", raw, device_type="cisco_ios")
    assert result.status == "ok"
    if result.parser == "version":
        assert result.data["hostname"] == "RT01"
        assert result.data["serial_number"] == "FTX1234ABC"
    else:
        assert result.parser == "ntc_templates.cisco_ios"


def test_parse_unsupported():
    raw = "some custom output"
    result = StructuredOutputParser.parse("show inventory", raw, device_type="cisco_ios")
    assert result.status == "unsupported"
    assert result.data is None
