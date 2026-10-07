"""Build a reproducible judge ZIP from an explicit source/evidence allowlist.

This packages the synthetic prototype; it neither submits nor deploys anything.
Runtime databases, credentials, private uploads, logs and downloaded binaries
are outside the allowlist. Inspect SUBMISSION_MANIFEST.json before handing over.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    ".dockerignore", ".env.example", ".gitattributes", ".gitignore",
    "AI_ASSISTANT_PROMPTS.txt", "alembic.ini", "compose.yaml", "config.py",
    "DEMO_DATA.txt", "Dockerfile", "README.md", "README_LEGENDARY.md",
    "requirements.txt", "requirements-ml.txt", "requirements-production.txt",
    "run.py", "USER_MANUAL.md", "wsgi.py", "phase_2.md",
}
REQUIRED_FILES = {
    "README.md", "run.py", "config.py", "requirements.txt", "app/__init__.py",
    "docs/JUDGE_FEEDBACK.md", "docs/SUBMISSION_CHECKLIST.md",
    "output/qa/submission/manifest.json", "phase_2.md",
    "scripts/judge_demo.py", "scripts/database_inventory.py",
    "app/ml/cashflow_random_forest.json", "app/ml/cashflow_evaluation.json",
    "app/ml/governance_manifest.json", "output/qa/database-inventory.json",
}
MODEL_FILES = {
    "app/ml/cashflow_random_forest.json", "app/ml/cashflow_evaluation.json",
    "app/ml/governance_manifest.json",
}
REPORT_FILES = {
    "output/pdf/UPAYX_DATABASE_REPORT.pdf", "output/qa/ai-safety.json",
    "output/qa/database-inventory.json",
}
SUBMISSION_REPORTS = {
    "manifest.json", "README.md", "regression-baseline.json", "regression-current.json",
    "postgres-qa.json", "load-sqlite.json", "load-postgres.json", "provider-contract.json",
    "model-evaluation.json", "browser-base.json", "browser-feedback.json", "browser-security.json",
    "ai-safety.json",
    "judge-browser.json", "submission-readiness.json", "database-inventory-tests.json",
}
EXCLUDED_COMPONENTS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".agents", ".codex",
    ".aws", "instance", "tmp", ".tmp", "artifacts", "uploads", "backups",
}


def allowed_file(relative: str) -> bool:
    """Only code, reviewed documentation, known model data and aggregate QA."""
    path = Path(relative)
    if any(part.lower() in EXCLUDED_COMPONENTS for part in path.parts):
        return False
    if any(part.lower().startswith(".env") for part in path.parts) and relative != ".env.example":
        return False
    if relative in ROOT_FILES | MODEL_FILES | REPORT_FILES:
        return True
    suffix = path.suffix.lower()
    if relative.startswith("app/"):
        return suffix in {".py", ".html", ".css", ".js", ".svg"}
    if relative.startswith("migrations/"):
        return suffix in {".py", ".mako"}
    if relative.startswith("docs/"):
        return suffix in {".md", ".yaml", ".yml"}
    if relative.startswith("deploy/"):
        return suffix == ".conf"
    if relative.startswith("scripts/"):
        return suffix == ".py"
    if relative.startswith("tests/"):
        return suffix == ".py" or relative == "tests/fixtures/ai_safety_cases.json"
    if relative.startswith("output/qa/submission/"):
        return path.name in SUBMISSION_REPORTS and len(path.parts) == 4
    return False


def _safe_source(path: Path, root: Path) -> None:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
        raise ValueError(f"Symlink source is not allowed: {path.name}")
    try:
        path.resolve(strict=True).relative_to(root)
    except (ValueError, FileNotFoundError) as exc:
        raise ValueError("Source escaped the project directory.") from exc
    if not path.is_file():
        raise ValueError("Submission source must be a regular file.")


def collect_files(root: Path = ROOT) -> list[tuple[str, bytes]]:
    root = root.resolve(strict=True)
    candidates = [root / name for name in ROOT_FILES if (root / name).exists()]
    for directory in ("app", "migrations", "docs", "deploy", "scripts", "tests", "output"):
        folder = root / directory
        if folder.exists():
            candidates.extend(path for path in folder.rglob("*") if path.is_file() or path.is_symlink())
    collected = {}
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        if not allowed_file(relative):
            continue
        _safe_source(path, root)
        collected[relative] = path.read_bytes()
    missing = REQUIRED_FILES - collected.keys()
    if missing:
        raise ValueError("Required submission files missing: " + ", ".join(sorted(missing)))
    return sorted(collected.items())


def build_submission(output: Path, *, root: Path = ROOT, overwrite: bool = False) -> dict:
    root = root.resolve(strict=True)
    output = output if output.is_absolute() else root / output
    if output.suffix.lower() != ".zip":
        raise ValueError("Submission output must be a .zip file.")
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents if parent != root):
        raise ValueError("Symlink output is not allowed.")
    try:
        output.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError("Submission output must stay inside the project directory.") from exc
    if output.exists() and not overwrite:
        raise ValueError("Output already exists; use --overwrite to replace this ZIP.")
    sources = collect_files(root)
    manifest = {
        "schema_version": 1,
        "purpose": "Judge review of a synthetic prototype; no external submission or deployment",
        "reproducible_archive": True,
        "zip_entry_timestamp": "1980-01-01T00:00:00",
        "source_file_count": len(sources),
        "historical_artifacts": {
            "output/pdf/UPAYX_DATABASE_REPORT.pdf": "Earlier synthetic dataset PDF; not a current schema or security report",
        },
        "excluded": ["credentials", "runtime databases and sidecars", "private uploads", "logs", "downloaded binaries", "environment/cache directories"],
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in sources},
    }
    entries = sources + [("SUBMISSION_MANIFEST.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="submission-", suffix=".partial", dir=output.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(entries):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compresslevel=9)
        temporary_path.replace(output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return {"archive": output.relative_to(root).as_posix(), "source_file_count": len(sources),
            "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "bytes": output.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/submission/UPAYX_SUBMISSION.zip"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        result = build_submission(args.output, overwrite=args.overwrite)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
