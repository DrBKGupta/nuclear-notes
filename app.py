"""Local web dashboard for drafting and publishing nuclear notes."""

from __future__ import annotations

import csv
import html
import hashlib
import json
import os
import re
import tempfile
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
DRAFTS_PATH = BASE_DIR / "drafts.json"
CAPSULE_DIR = BASE_DIR / "capsule"
DEFAULT_CSV_CANDIDATES = (
    BASE_DIR / "question_bank.csv",
    BASE_DIR / "Refinary " / "question_bank.csv",
)
MAX_TEXT_LENGTH = 20_000
MAX_SEARCH_RESULTS = 30
CONFIDENCE_LEVELS = {"Low", "Med", "High"}
FREQUENCY_TAGS = {"Frequently asked", "Seen in PYQs", "Occasional", "Not sure"}
DRAFT_LOCK = threading.RLock()

app = Flask(__name__)


class DataStoreError(Exception):
    """Raised when local JSON data cannot be read or safely written."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_drafts() -> list[dict[str, Any]]:
    if not DRAFTS_PATH.exists():
        return []
    try:
        with DRAFTS_PATH.open("r", encoding="utf-8") as drafts_file:
            data = json.load(drafts_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise DataStoreError(f"Could not read {DRAFTS_PATH.name}: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("drafts"), list):
        raise DataStoreError(f"{DRAFTS_PATH.name} must contain an object with a drafts list.")
    if not all(isinstance(draft, dict) for draft in data["drafts"]):
        raise DataStoreError(f"{DRAFTS_PATH.name} contains an invalid draft entry.")
    return data["drafts"]


def write_drafts(drafts: list[dict[str, Any]]) -> None:
    """Replace the JSON file atomically so interrupted writes do not corrupt it."""
    temporary_path: str | None = None
    try:
        DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=DRAFTS_PATH.parent,
            prefix=".drafts-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump({"drafts": drafts}, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, DRAFTS_PATH)
    except OSError as exc:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise DataStoreError(f"Could not save {DRAFTS_PATH.name}: {exc}") from exc


def csv_path() -> Path:
    configured_path = os.environ.get("QUESTION_BANK_CSV")
    if configured_path:
        candidate = Path(configured_path)
        return candidate if candidate.is_absolute() else BASE_DIR / candidate
    return next((path for path in DEFAULT_CSV_CANDIDATES if path.is_file()), DEFAULT_CSV_CANDIDATES[0])


def search_question_bank(query: str) -> list[dict[str, str]]:
    path = csv_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"Question bank not found at {path}. Set QUESTION_BANK_CSV to its local path."
        )

    normalized_query = query.casefold()
    matches: list[dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                raise ValueError("The question bank CSV has no header row.")
            for row in reader:
                if not any(normalized_query in str(value or "").casefold() for value in row.values()):
                    continue
                matches.append(
                    {
                        "subject": (row.get("subject") or "").strip(),
                        "topic": (row.get("topic") or "").strip(),
                        "question": (row.get("question") or "").strip()[:1500],
                        "exam": (row.get("exam") or "").strip(),
                        "year": (row.get("year") or "").strip(),
                        "session": (row.get("session") or "").strip(),
                        "source_file": (row.get("source_file") or "").strip(),
                        "source_location": (row.get("source_location") or "").strip(),
                        "answer_text": (row.get("answer_text") or "").strip()[:1000],
                        "review_status": (row.get("review_status") or "").strip(),
                    }
                )
                if len(matches) >= MAX_SEARCH_RESULTS:
                    break
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise ValueError(f"Could not search the question bank: {exc}") from exc
    return matches


def validate_draft(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Draft data must be a JSON object.")

    fields = ("subject", "topic")
    cleaned: dict[str, str] = {}
    for field in fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is required.")
        value = value.strip()
        if len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is too long.")
        if field == "subject" and len(value) > 120:
            raise ValueError("Subject must be 120 characters or fewer.")
        if field == "topic" and len(value) > 200:
            raise ValueError("Topic must be 200 characters or fewer.")
        cleaned[field] = value

    for field, alias in (("clinical_stem", "stem"), ("core_concept", "concept")):
        value = payload.get(field, payload.get(alias))
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is required.")
        value = value.strip()
        if len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is too long.")
        cleaned[field] = value

    confidence = payload.get("confidence")
    if not isinstance(confidence, str) or confidence not in CONFIDENCE_LEVELS:
        raise ValueError("Confidence must be Low, Med, or High.")
    frequency = payload.get("frequency", "Not sure")
    if not isinstance(frequency, str) or frequency not in FREQUENCY_TAGS:
        raise ValueError("Choose a valid frequency tag.")
    cleaned["confidence"] = confidence
    cleaned["frequency"] = frequency
    cleaned["source"] = str(payload.get("source") or "").strip()[:500]
    return cleaned


def subject_filename(subject: str) -> str:
    normalized = unicodedata.normalize("NFKD", subject).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    if not slug:
        slug = f"subject-{hashlib.sha256(subject.encode('utf-8')).hexdigest()[:10]}"
    return f"{slug}.md"


def markdown_for_draft(draft: dict[str, Any]) -> str:
    """Create a printable note with a stable marker for safe retry detection."""
    note_id = draft["id"]
    return (
        f"<!-- nuclear-note-id:{note_id} -->\n"
        f"### {markdown_heading(draft['topic'])}\n\n"
        f"**Clinical stem / question**\n\n{as_blockquote(draft['clinical_stem'])}\n\n"
        f"**Core concept / trap**\n\n{as_blockquote(draft['core_concept'])}\n\n"
        f"- **Confidence:** {draft['confidence']}\n"
        f"- **Frequency:** {draft['frequency']}\n"
        f"{format_source(draft.get('source', ''))}"
        f"\n<!-- end nuclear-note-id:{note_id} -->\n"
    )


def markdown_heading(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"([\\`*_{}\[\]()#+.!|<>])", r"\\\1", escaped)
    return " ".join(escaped.splitlines())


def as_blockquote(text: str) -> str:
    escaped = html.escape(text, quote=False)
    return "\n".join(f"> {line}" if line else ">" for line in escaped.splitlines())


def format_source(source: str) -> str:
    return f"- **Source:**\n{as_blockquote(source)}\n" if source else ""


def atomic_write_text(path: Path, contents: str) -> None:
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            temporary_file.write(contents)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


def publish_draft(draft_id: str) -> dict[str, Any]:
    with DRAFT_LOCK:
        drafts = read_drafts()
        draft = next((item for item in drafts if item.get("id") == draft_id), None)
        if draft is None:
            raise KeyError("Draft not found.")
        if draft.get("status") == "Published":
            raise RuntimeError("This draft has already been published.")
        if draft.get("status") != "Draft":
            raise RuntimeError("Only saved drafts can be published.")

        CAPSULE_DIR.mkdir(parents=True, exist_ok=True)
        target = CAPSULE_DIR / subject_filename(draft["subject"])
        marker = f"<!-- nuclear-note-id:{draft_id} -->"
        try:
            previous_contents = target.read_text(encoding="utf-8") if target.exists() else ""
            if marker not in previous_contents:
                heading = f"# {markdown_heading(draft['subject'])}\n\n"
                if not previous_contents:
                    previous_contents = heading
                elif not previous_contents.startswith("# "):
                    previous_contents = heading + previous_contents.lstrip()
                elif previous_contents.splitlines()[0] != heading.strip():
                    raise DataStoreError(
                        f"Subject filename collision at {target.name}; choose a different subject name."
                    )
                elif not previous_contents.endswith("\n"):
                    previous_contents += "\n"
                separator = "" if previous_contents.endswith("\n\n") else "\n"
                atomic_write_text(target, previous_contents + separator + markdown_for_draft(draft))

            draft["status"] = "Published"
            draft["published_at"] = utc_now()
            write_drafts(drafts)
        except OSError as exc:
            raise DataStoreError(f"Could not publish note to {target.name}: {exc}") from exc
        except DataStoreError:
            raise
        return draft


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/drafts")
def list_drafts():
    try:
        with DRAFT_LOCK:
            drafts = read_drafts()
        return jsonify(sorted(drafts, key=lambda draft: draft.get("updated_at", ""), reverse=True))
    except DataStoreError as exc:
        return jsonify(error=str(exc)), 500


@app.get("/api/drafts/<draft_id>")
def get_draft(draft_id: str):
    try:
        with DRAFT_LOCK:
            draft = next((item for item in read_drafts() if item.get("id") == draft_id), None)
        if draft is None:
            return jsonify(error="Draft not found."), 404
        return jsonify(draft)
    except DataStoreError as exc:
        return jsonify(error=str(exc)), 500


@app.post("/api/drafts")
@app.post("/api/draft")
def save_draft():
    try:
        payload = request.get_json(silent=True)
        cleaned = validate_draft(payload)
        with DRAFT_LOCK:
            drafts = read_drafts()
            draft_id = payload.get("id") if isinstance(payload, dict) else None
            draft = next((item for item in drafts if item.get("id") == draft_id), None) if draft_id else None
            if draft_id and draft is None:
                return jsonify(error="Draft not found."), 404
            if draft and draft.get("status") != "Draft":
                return jsonify(error="Published notes cannot be edited. Save a new draft instead."), 409
            if draft is None:
                draft = {"id": str(uuid.uuid4()), "created_at": utc_now(), "status": "Draft"}
                drafts.append(draft)
            draft.update(cleaned)
            draft["updated_at"] = utc_now()
            write_drafts(drafts)
        return jsonify(success=True, **draft), 201
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except DataStoreError as exc:
        return jsonify(error=str(exc)), 500


@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify(results=[])
    try:
        return jsonify(results=search_question_bank(query))
    except FileNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 500


@app.post("/api/drafts/<draft_id>/publish")
def approve_and_publish(draft_id: str):
    try:
        published = publish_draft(draft_id)
        return jsonify(published)
    except KeyError as exc:
        return jsonify(error=str(exc)), 404
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 409
    except DataStoreError as exc:
        return jsonify(error=str(exc)), 500


if __name__ == "__main__":
    CAPSULE_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=False)
