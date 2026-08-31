#!/usr/bin/env python3
"""Single source of truth for the run-time skill freeze enumeration.

This module owns the ONLY rule that decides which skill files are frozen into
``controller/skill-freeze-manifest.sha256`` at run init time
(init_migration.py, the generator side) and which files are re-hashed at every
gate entry (validate_gate.py / audit_delivery.py, the verification side).

Historical defect (SKILLBUG-01, fixed in skill 2.1.2): the generator side
enumerated with a bare ``path.is_file()`` while the verification side skipped
``__pycache__``/``*.pyc``, so any run whose skill trees contained byte-code
caches was self-violating at every gate. Both sides MUST now import the
enumeration from this module; re-implementing the walk on either side is
prohibited. The shared exclusions are:

1. any path with a ``__pycache__`` component (interpreter artifact);
2. any ``*.pyc`` suffix (interpreter artifact);
3. symbolic links (never hashed, never trusted);
4. non-files (directories are traversed, not hashed).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


FROZEN_SKILL_NAMES = (
    "android-harmony-migration-controller",
    "android-migration-inventory",
    "harmonyos-migration-scaffold",
    "harmonyos-feature-implementation",
)
FROZEN_SKILL_DIRS = ("scripts", "references", "assets", "evals", "security")
FROZEN_SKILL_ROOT_FILES = ("SKILL.md", "manifest.json")


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def enumerate_frozen_skill_files(skills_root: Path) -> dict[str, Path]:
    """Enumerate every frozen skill file as ``{skill_name>/<relative>: Path}``.

    Shared by the manifest generator and the verifier so both sides always
    agree on the file set. Missing skill directories or missing frozen
    sub-directories are skipped silently (a skill may not ship every
    directory); byte-code caches and symlinks are never collected.
    """
    root = Path(skills_root)
    files: dict[str, Path] = {}
    for skill_name in FROZEN_SKILL_NAMES:
        skill_root = root / skill_name
        for dir_name in FROZEN_SKILL_DIRS:
            base = skill_root / dir_name
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if "__pycache__" in path.parts:
                    continue
                if path.suffix == ".pyc":
                    continue
                if path.is_symlink():
                    continue
                if path.is_file():
                    files[f"{skill_name}/{path.relative_to(skill_root).as_posix()}"] = path
        for file_name in FROZEN_SKILL_ROOT_FILES:
            target = skill_root / file_name
            if target.is_symlink():
                continue
            if target.is_file():
                files[f"{skill_name}/{file_name}"] = target
    return files


def build_manifest_text(skills_root: Path) -> tuple[str, str]:
    """Build the sha256sum-style freeze manifest; return ``(text, digest)``.

    Thin wrapper over :func:`enumerate_frozen_skill_files` used by the
    generator side (init_migration.py).
    """
    lines = [
        f"{sha256_of_file(path)}  {key}"
        for key, path in sorted(enumerate_frozen_skill_files(skills_root).items())
    ]
    manifest_text = "\n".join(lines) + "\n"
    manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    return manifest_text, manifest_digest


def current_hashes(skills_root: Path) -> dict[str, str]:
    """Hash the live skill trees with the shared enumeration rule.

    Thin wrapper over :func:`enumerate_frozen_skill_files` used by the
    verification side (validate_gate.py via ``_skill_freeze_current_hashes``).
    """
    return {
        key: sha256_of_file(path)
        for key, path in enumerate_frozen_skill_files(skills_root).items()
    }