"""Tests for the command-line bootstrap."""

from _pytest.capture import CaptureFixture

from pipeline_dashboard_api_client.cli import main


def test_version_command(capsys: CaptureFixture[str]) -> None:
    """The version command prints the package version."""
    exit_code = main(["version"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "0.1.0"
    assert captured.err == ""
