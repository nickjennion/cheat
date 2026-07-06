from cheat_core import build_command_list, DNAC_COMMANDS


def test_build_command_list_off_is_base():
    assert build_command_list(False) == DNAC_COMMANDS
    assert "show logging" not in build_command_list(False)


def test_build_command_list_on_adds_logging_and_clock():
    cmds = build_command_list(True)
    assert cmds[: len(DNAC_COMMANDS)] == DNAC_COMMANDS
    assert cmds[-2:] == ["show logging", "show clock"]
