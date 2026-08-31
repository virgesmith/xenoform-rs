from pathlib import Path

import pytest

from xenoform_rs import skill_cli


def test_install_creates_symlink(tmp_path: Path) -> None:
    assert skill_cli.main(["--install", str(tmp_path)]) == 0

    target = tmp_path / "skills" / "xenoform-rs"
    assert target.is_symlink()
    assert target.resolve() == skill_cli._source_dir().resolve()


def test_install_default_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert skill_cli.main(["--install"]) == 0

    target = tmp_path / ".agents" / "skills" / "xenoform-rs"
    assert target.is_symlink()


def test_install_across_windows_drives(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # os.path.relpath raises when the installed package and the target project are on different drives
    def raise_valueerror(*_args: object, **_kwargs: object) -> str:
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(skill_cli.os.path, "relpath", raise_valueerror)
    assert skill_cli.main(["--install", str(tmp_path)]) == 0

    target = tmp_path / "skills" / "xenoform-rs"
    assert target.is_symlink()
    assert target.resolve() == skill_cli._source_dir().resolve()


def test_is_ours_ignores_unresolvable_symlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "link"
    target.symlink_to(tmp_path, target_is_directory=True)

    def raise_oserror(*_args: object, **_kwargs: object) -> Path:
        raise OSError("cannot resolve")

    monkeypatch.setattr(Path, "resolve", raise_oserror)
    assert not skill_cli._is_ours(target, skill_cli._source_dir())


def test_install_idempotent(tmp_path: Path) -> None:
    assert skill_cli.main(["--install", str(tmp_path)]) == 0
    assert skill_cli.main(["--install", str(tmp_path)]) == 0

    target = tmp_path / "skills" / "xenoform-rs"
    assert target.is_symlink()


def test_install_refuses_existing_directory(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "xenoform-rs"
    target.mkdir(parents=True)
    (target / "keepme.txt").write_text("do not delete")

    assert skill_cli.main(["--install", str(tmp_path)]) == 1
    assert not target.is_symlink()
    assert (target / "keepme.txt").read_text() == "do not delete"


def test_install_refuses_foreign_symlink(tmp_path: Path) -> None:
    foreign = tmp_path / "elsewhere"
    foreign.mkdir()
    target = tmp_path / "skills" / "xenoform-rs"
    target.parent.mkdir(parents=True)
    target.symlink_to(foreign, target_is_directory=True)

    assert skill_cli.main(["--install", str(tmp_path)]) == 1
    assert target.resolve() == foreign.resolve()


def test_remove_deletes_owned_symlink(tmp_path: Path) -> None:
    skill_cli.main(["--install", str(tmp_path)])
    target = tmp_path / "skills" / "xenoform-rs"
    assert target.is_symlink()

    assert skill_cli.main(["--remove", str(tmp_path)]) == 0
    assert not target.exists()
    assert not target.is_symlink()


def test_remove_missing_is_noop(tmp_path: Path) -> None:
    assert skill_cli.main(["--remove", str(tmp_path)]) == 0


def test_remove_refuses_foreign_directory(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "xenoform-rs"
    target.mkdir(parents=True)
    (target / "keepme.txt").write_text("do not delete")

    assert skill_cli.main(["--remove", str(tmp_path)]) == 1
    assert (target / "keepme.txt").read_text() == "do not delete"


def test_remove_default_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    skill_cli.main(["--install"])
    target = tmp_path / ".agents" / "skills" / "xenoform-rs"
    assert target.is_symlink()

    assert skill_cli.main(["--remove"]) == 0
    assert not target.exists()


def test_mutually_exclusive_args_required() -> None:
    with pytest.raises(SystemExit):
        skill_cli.main([])
    with pytest.raises(SystemExit):
        skill_cli.main(["--install", ".", "--remove", "."])
