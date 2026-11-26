"""Loads the twin-question files and checks they are well formed.

Each file in the questions folder is one subject. Every concept has exactly
two "twin" questions that test the same idea in different words. A student
sees one twin first; if they miss it, the other twin comes back later as the
comeback question.
"""
import json
from pathlib import Path

LETTERS = "ABCDE"


class QuestionError(ValueError):
    pass


class QuestionBank:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.by_id = {}
        self.load()

    def load(self):
        if not self.folder.is_dir():
            raise QuestionError(f"Questions folder not found: {self.folder}")
        for path in sorted(self.folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            subject = data.get("subject") or path.stem
            for concept in data.get("concepts", []):
                self._add_concept(subject, concept, path.name)

    def _add_concept(self, subject, concept, filename):
        cid = concept.get("id")
        twins = concept.get("twins", [])
        if not cid or len(twins) != 2:
            raise QuestionError(f"{filename}: concept {cid!r} needs an id and exactly 2 twins")
        for twin in twins:
            qid = twin.get("id")
            options = twin.get("options", [])
            answer = twin.get("answer")
            hints = twin.get("hints", [])
            where = f"{filename}: question {qid!r}"
            if not qid or qid in self.by_id:
                raise QuestionError(f"{where} has a missing or duplicate id")
            if not 2 <= len(options) <= len(LETTERS):
                raise QuestionError(f"{where} needs 2 to {len(LETTERS)} options")
            if not isinstance(answer, int) or not 0 <= answer < len(options):
                raise QuestionError(f"{where} has an answer index outside its options")
            if len(hints) < 2 or not twin.get("explanation"):
                raise QuestionError(f"{where} needs an explanation and at least 2 hints")
            self.by_id[qid] = {
                "id": qid,
                "subject": subject,
                "concept_id": cid,
                "question": twin["question"],
                "options": options,
                "answer": answer,
                "explanation": twin["explanation"],
                "hints": hints,
            }

    def get(self, qid):
        return self.by_id.get(qid)
