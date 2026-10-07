"""Reproducible offline safety corpus evaluation. No provider calls or secrets.

Run: python scripts/evaluate_ai_safety.py --output output/qa/ai-safety.json
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ai_governance_service import injection_reason, output_is_safe, redact_sensitive

CORPUS = PROJECT_ROOT / "tests" / "fixtures" / "ai_safety_cases.json"


def evaluate():
    raw = CORPUS.read_bytes()
    corpus = json.loads(raw)
    checks = []
    for row in corpus["blocked_inputs"]:
        checks.append({"case": row["id"], "category": "input_block", "passed": bool(injection_reason(row["text"]))})
    for index, content in enumerate(corpus["benign_inputs"]):
        checks.append({"case": f"benign_{index}", "category": "benign_input", "passed": injection_reason(content) is None})
    for index, row in enumerate(corpus["sensitive_inputs"]):
        clean = redact_sensitive(row["text"])
        checks.append({"case": f"redaction_{index}", "category": "redaction", "passed": all(secret not in clean for secret in row["secrets"])})
    for index, content in enumerate(corpus["unsafe_outputs"]):
        checks.append({"case": f"output_block_{index}", "category": "output_block", "passed": not output_is_safe(content)})
    for index, content in enumerate(corpus["safe_outputs"]):
        checks.append({"case": f"safe_output_{index}", "category": "benign_output", "passed": output_is_safe(content)})
    return {"schema_version": 1, "corpus_sha256": hashlib.sha256(raw).hexdigest(),
            "evaluation_mode": "offline deterministic guard corpus", "live_model_tested": False,
            "limitations": "Finite regression cases; not a penetration test or proof against unseen prompt injection.",
            "passed": sum(row["passed"] for row in checks), "total": len(checks), "cases": checks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}, indent=2))
    sys.exit(0 if result["passed"] == result["total"] else 1)
