from unittest import mock

from standup import cli


def test_ctrl_c_exits_quietly_instead_of_dumping_a_traceback(capsys):
    """uvicorn's Server.capture_signals() re-raises the captured signal after a clean shutdown
    so a wrapping shell sees the real exit status - which otherwise surfaces here as
    KeyboardInterrupt and Python prints a raw traceback for it. A user pressing Ctrl+C isn't
    a crash and shouldn't look like one."""
    with (
        mock.patch("standup.cli.uvicorn.run", side_effect=KeyboardInterrupt),
        mock.patch("sys.argv", ["standup", "--no-browser"]),
    ):
        cli.main()  # must not raise

    assert "Standup stopped." in capsys.readouterr().out
