"""Tests for the command-line bootstrap."""

from pipeline_dashboard_api_client.cli import main


def test_version_command(capsys: object) -> None:
    """The version command prints the package version."""
    exit_code = main(["version"])

    captured = capsys.readouterr()  # type: ignore[attr-defined]

    assert exit_code == 0
    assert captured.out.strip() == "0.1.0"
    assert captured.err == ""
