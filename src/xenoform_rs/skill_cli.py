import argparse
import os
from pathlib import Path

_SKILL_NAME = "xenoform-rs"
_DEFAULT_PATH = ".agents"


def _source_dir() -> Path:
    """The bundled skill directory, shipped inside this package."""
    return Path(__file__).parent / "skill"


def _target_path(root: str) -> Path:
    return Path(root) / "skills" / _SKILL_NAME


def _is_ours(target: Path, source: Path) -> bool:
    if not target.is_symlink():
        return False
    try:
        return target.resolve() == source.resolve()
    except OSError:
        return False


def _link_target(source: Path, target: Path) -> str:
    """A relative link target, or an absolute one if there is no relative path (different windows drives)."""
    try:
        return os.path.relpath(source.resolve(), target.parent.resolve())
    except ValueError:
        return str(source.resolve())


def _install(root: str) -> int:
    source = _source_dir()
    target = _target_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_symlink():
        if _is_ours(target, source):
            print(f"already installed and up to date: {target}")
            return 0
        print(f"refusing to overwrite existing symlink not managed by {_SKILL_NAME}-skill: {target}")
        return 1
    if target.exists():
        print(f"refusing to overwrite existing file or directory: {target}")
        return 1

    target.symlink_to(_link_target(source, target), target_is_directory=True)
    print(f"installed: {target} -> {source}")
    return 0


def _remove(root: str) -> int:
    source = _source_dir()
    target = _target_path(root)

    if not target.exists() and not target.is_symlink():
        print(f"not installed: {target}")
        return 0
    if not _is_ours(target, source):
        print(f"refusing to remove {target}: not a symlink managed by {_SKILL_NAME}-skill")
        return 1

    target.unlink()
    print(f"removed: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `xenoform-rs-skill` console script."""
    parser = argparse.ArgumentParser(
        prog="xenoform-rs-skill",
        description=f"Install or remove the '{_SKILL_NAME}' agent skill as a symlink into a project.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--install",
        nargs="?",
        const=_DEFAULT_PATH,
        metavar="PATH",
        help=f"Symlink the skill into PATH/skills/{_SKILL_NAME} (default PATH: {_DEFAULT_PATH}).",
    )
    group.add_argument(
        "--remove",
        nargs="?",
        const=_DEFAULT_PATH,
        metavar="PATH",
        help=f"Remove the symlink from PATH/skills/{_SKILL_NAME} (default PATH: {_DEFAULT_PATH}).",
    )
    args = parser.parse_args(argv)

    if args.install is not None:
        return _install(args.install)
    return _remove(args.remove)


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover - console script entry point
