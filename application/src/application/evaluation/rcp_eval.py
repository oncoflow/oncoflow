"""
Evaluation of the RCP review questions on synthetic RCP records.

A case is a directory containing:
    - fiche_rcp.md   : the RCP form (markdown)
    - annexes/*.md   : annex documents (imaging, pathology, biology reports...)
    - case.json      : {"description", "synthetic", "expected": {...}, "gold": {...}}

`expected` gives, for each question of `src.domain.oncology.rcp_review.RCP_REVIEW_QUESTIONS`,
the boolean fields that must match (null = not scored) and `must_mention`, a list of
groups of keywords: at least one keyword of each group must appear in the answer.
`gold` gives a reference answer for each question, valid against its model.

Usage against a live LLM (e.g. through a Bifrost gateway, see docs/bifrost.md):
    PYTHONPATH=. uv run python -m src.application.evaluation.rcp_eval tests/fixtures/rcp
"""

import json
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from pydantic import BaseModel

from src.domain.oncology.rcp_review import RCP_REVIEW_QUESTIONS

# Keys of the `expected` block that are not model fields
NON_FIELD_KEYS = {"must_mention", "comment"}


def normalize(text: str) -> str:
    """Lowercase and remove accents to compare french medical texts."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class MarkdownRecord:
    """
    Minimal DocumentReader replacement exposing a markdown record to the agent tools
    (`get_mtd_markdown`), without parsing a PDF nor indexing a vector database.
    """

    def __init__(self, name: str, markdown: str) -> None:
        self.document = name
        self.document_path = name
        self.markdown_exporter = [
            Document(page_content=markdown, metadata={"source": name})
        ]


@dataclass
class RCPCase:
    case_id: str
    description: str
    fiche: str
    annexes: dict[str, str] = field(default_factory=dict)
    expected: dict[str, dict[str, Any]] = field(default_factory=dict)
    gold: dict[str, dict[str, Any]] = field(default_factory=dict)
    synthetic: bool = True

    def to_markdown(self) -> str:
        """Whole record: RCP form followed by each annex document."""
        parts = [f"# Fiche RCP\n\n{self.fiche.strip()}"]
        for name, content in self.annexes.items():
            parts.append(f"# Document annexe : {name}\n\n{content.strip()}")
        return "\n\n---\n\n".join(parts) + "\n"

    def to_record(self) -> MarkdownRecord:
        return MarkdownRecord(self.case_id, self.to_markdown())


def load_rcp_case(case_dir: Path) -> RCPCase:
    case_dir = Path(case_dir)
    meta = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    annexes_dir = case_dir / "annexes"
    annexes = (
        {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted(annexes_dir.glob("*.md"))
        }
        if annexes_dir.is_dir()
        else {}
    )
    return RCPCase(
        case_id=case_dir.name,
        description=meta["description"],
        fiche=(case_dir / "fiche_rcp.md").read_text(encoding="utf-8"),
        annexes=annexes,
        expected=meta.get("expected", {}),
        gold=meta.get("gold", {}),
        synthetic=meta.get("synthetic", False),
    )


def load_rcp_cases(root: Path) -> list[RCPCase]:
    return [
        load_rcp_case(d)
        for d in sorted(Path(root).iterdir())
        if d.is_dir() and (d / "case.json").exists()
    ]


@dataclass
class EvalResult:
    case_id: str
    question: str
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def score_answer(
    case_id: str, question: str, answer: BaseModel | dict, expected: dict[str, Any]
) -> EvalResult:
    """
    Compare an answer with the expected labels of a case for one question.
    """
    result = EvalResult(case_id=case_id, question=question)
    values = answer.model_dump(mode="json") if isinstance(answer, BaseModel) else answer

    for key, expected_value in expected.items():
        if key in NON_FIELD_KEYS or expected_value is None:
            continue
        value = values.get(key)
        if isinstance(expected_value, list):
            if value not in expected_value:
                result.errors.append(
                    f"{key}: got {value!r}, expected one of {expected_value!r}"
                )
        elif value != expected_value:
            result.errors.append(f"{key}: got {value!r}, expected {expected_value!r}")

    text = normalize(json.dumps(values, ensure_ascii=False))
    for group in expected.get("must_mention", []):
        if not any(normalize(keyword) in text for keyword in group):
            result.errors.append(f"answer does not mention any of {group!r}")

    return result


def evaluate_case(config: Any, case: RCPCase) -> list[EvalResult]:
    """Ask every scored question of a case to a live LLM and score the answers."""
    from src.domain.oncology.rcp_review import RCPReviewerAgent

    results = []
    for question_key, expected in case.expected.items():
        model = RCP_REVIEW_QUESTIONS[question_key]
        agent = RCPReviewerAgent(
            config=config, mtd=case.to_record(), output_format=model
        )
        try:
            answer = agent.ask(model.question)
        except ValueError as e:
            results.append(EvalResult(case.case_id, question_key, [f"no answer: {e}"]))
            continue
        results.append(score_answer(case.case_id, question_key, answer, expected))
    return results


def main(argv: list[str]) -> int:
    from src.application.config import AppConfig

    root = Path(argv[1]) if len(argv) > 1 else Path("tests/fixtures/rcp")
    config = AppConfig()
    results = [r for case in load_rcp_cases(root) for r in evaluate_case(config, case)]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{status} {r.case_id:<32} {r.question:<28} {'; '.join(r.errors)}")
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} answers passed with model {config.llm.models}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
