#!/usr/bin/env python3
"""Personal running spreadsheet for the Podcast Production Engine (Skill 58).

Implements PRD Step 17 (Personal branch) and PRD Section 8 (SOLO preset):

  "Personal: append the episode row to the running spreadsheet, no workflows, no
   messages."
  "SOLO (mode: personal_podcast_style). Full run minus teaser and workflows;
   running spreadsheet update instead."

Three responsibilities:
  1. CREATE-AT-SETUP: create the client's running episode spreadsheet once, when the
     client is onboarded, idempotently (reuse an existing sheet, never duplicate).
  2. APPEND-PER-EPISODE: add one row per completed Personal-mode episode.
  3. CUSTOM-FIELD LINK STORAGE: record the spreadsheet link in per-client state and,
     when a field writer is provided, in a Convert and Flow custom field so the link
     is retrievable. No standardized field key is invented here (ghl-design forbids
     inventing keys); the caller supplies the field key it wants written.

Mode guard (mirror of the Interview-side enrollment refusal): Personal mode NEVER
touches the two Convert and Flow workflows and Interview mode NEVER touches this
spreadsheet. append_episode() hard-refuses interview_style_podcast.

Silence doctrine: this module sends NO customer message of any kind. It writes rows
and stores a link. Convert and Flow owns all customer messaging; the engine stops
here.

Tooling (Documents-module detection order, PRD Step 12): Google preferred, then
Notion, then plain-text as the last resort. The Google and Notion backends bind to
an injected client from the client's own detected tooling; the CSV backend is the
fully functional plain-text last resort and needs nothing external.

Writing rules: zero em dash characters and no triple-backtick fences in any row this
module writes (fail-closed assertion on every cell).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional, Protocol

EM_DASH = "\u2014"
FENCE = chr(96) * 3  # three backticks, constructed so no literal fence sits in source

PERSONAL_MODE = "personal_podcast_style"
INTERVIEW_MODE = "interview_style_podcast"

# The running-spreadsheet column schema (create-once header; append matches order).
COLUMNS = [
    "Episode #",
    "Date",
    "Title",
    "Style",
    "Runtime (minutes)",
    "Spoken word count",
    "Podbean link",
    "Episode Package link",
    "Speech Script link",
    "Cover image",
    "MP3",
    "Submitter",
    "Status",
]

_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str) -> str:
    return _SLUG.sub("_", text.strip()).strip("_") or "client"


def assert_cell_clean(value: str) -> str:
    """Fail closed if a produced cell carries an em dash or a triple backtick."""
    text = "" if value is None else str(value)
    if EM_DASH in text:
        raise ValueError("spreadsheet cell contains an em dash character (forbidden): " + text)
    if FENCE in text:
        raise ValueError("spreadsheet cell contains a triple-backtick fence (forbidden): " + text)
    return text


def assert_personal_mode(mode: str) -> None:
    """Hard-refuse Interview mode. The spreadsheet is a Personal-mode artifact."""
    normalized = (mode or "").strip().lower()
    if normalized == INTERVIEW_MODE or "interview" in normalized:
        raise ValueError(
            "personal_spreadsheet refuses Interview mode: Interview episodes enroll "
            "the Convert and Flow workflows and never touch the running spreadsheet"
        )
    if normalized and normalized != PERSONAL_MODE and "personal" not in normalized:
        raise ValueError("personal_spreadsheet requires Personal mode, got: " + str(mode))


@dataclass
class SheetRef:
    backend: str
    sheet_id: str
    url: str
    title: str

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "sheet_id": self.sheet_id,
            "url": self.url,
            "title": self.title,
        }


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class SpreadsheetBackend(Protocol):
    name: str

    def find(self, title: str) -> Optional[SheetRef]: ...

    def create(self, title: str, columns: list[str]) -> SheetRef: ...

    def append(self, ref: SheetRef, row: list[str]) -> None: ...

    def header(self, ref: SheetRef) -> Optional[list[str]]: ...


class CsvBackend:
    """Plain-text last resort. Fully functional and self-contained.

    Writes <base_dir>/<slug(title)>.csv on the client's own box. This is the
    running-spreadsheet counterpart the dashboard references (dashboard-design 10.2)
    when neither Google nor Notion tooling is wired.
    """

    name = "csv"

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, title: str) -> str:
        return os.path.join(self.base_dir, _slug(title) + ".csv")

    def find(self, title: str) -> Optional[SheetRef]:
        path = self._path(title)
        if os.path.exists(path):
            return SheetRef(backend=self.name, sheet_id=path, url="file://" + os.path.abspath(path), title=title)
        return None

    def create(self, title: str, columns: list[str]) -> SheetRef:
        path = self._path(title)
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow([assert_cell_clean(c) for c in columns])
        return SheetRef(backend=self.name, sheet_id=path, url="file://" + os.path.abspath(path), title=title)

    def append(self, ref: SheetRef, row: list[str]) -> None:
        with open(ref.sheet_id, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([assert_cell_clean(c) for c in row])

    def header(self, ref: SheetRef) -> Optional[list[str]]:
        if not os.path.exists(ref.sheet_id):
            return None
        with open(ref.sheet_id, "r", newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for first in reader:
                return first
        return None


class _InjectedClientBackend:
    """Common shape for the Google and Notion backends.

    The runtime binds `client`, an object from the client's OWN detected tooling
    (Skill 14 Google Workspace integration, or the Notion integration) exposing:
      client.find(title) -> {"id","url"} | None
      client.create(title, columns) -> {"id","url"}
      client.append(sheet_id, row) -> None
      client.header(sheet_id) -> list | None   (optional)
    When no client is bound, the backend raises so the caller falls back to CSV
    rather than silently doing nothing (no false-done).
    """

    name = "injected"

    def __init__(self, client=None):
        self.client = client

    def _require(self):
        if self.client is None:
            raise NotImplementedError(
                self.name
                + " backend needs a bound client from the client's own detected tooling; "
                + "wire it at setup or fall back to the CSV backend"
            )
        return self.client

    def find(self, title: str) -> Optional[SheetRef]:
        got = self._require().find(title)
        if not got:
            return None
        return SheetRef(backend=self.name, sheet_id=got["id"], url=got["url"], title=title)

    def create(self, title: str, columns: list[str]) -> SheetRef:
        got = self._require().create(title, [assert_cell_clean(c) for c in columns])
        return SheetRef(backend=self.name, sheet_id=got["id"], url=got["url"], title=title)

    def append(self, ref: SheetRef, row: list[str]) -> None:
        self._require().append(ref.sheet_id, [assert_cell_clean(c) for c in row])

    def header(self, ref: SheetRef) -> Optional[list[str]]:
        client = self._require()
        if hasattr(client, "header"):
            return client.header(ref.sheet_id)
        return None


class GoogleSheetsBackend(_InjectedClientBackend):
    name = "google_sheets"


class NotionBackend(_InjectedClientBackend):
    name = "notion"


def detect_backend(
    base_dir: str,
    google_client=None,
    notion_client=None,
) -> SpreadsheetBackend:
    """Choose the backend in the Documents-module preference order.

    Google (if its client is wired) preferred, then Notion, then the plain-text CSV
    last resort. The runtime passes the clients it detected on the client's box.
    """
    if google_client is not None:
        return GoogleSheetsBackend(google_client)
    if notion_client is not None:
        return NotionBackend(notion_client)
    return CsvBackend(base_dir)


# ---------------------------------------------------------------------------
# Per-client state (create-once memory + link storage)
# ---------------------------------------------------------------------------


def _state_path(state_dir: str) -> str:
    return os.path.join(state_dir, "personal-spreadsheet.json")


def load_state(state_dir: str) -> Optional[dict]:
    path = _state_path(state_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def save_state(state_dir: str, state: dict) -> None:
    os.makedirs(state_dir, exist_ok=True)
    path = _state_path(state_dir)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def store_spreadsheet_link(
    client_id: str,
    ref: SheetRef,
    state_dir: str,
    field_writer: Optional[Callable[[str, str], None]] = None,
    field_key: Optional[str] = None,
) -> dict:
    """Persist the spreadsheet link (create-once memory) and optionally to a field.

    field_writer, when supplied, is the Convert and Flow field layer's writer; it
    receives (field_key, url). No standardized field key is invented here; the
    caller passes the key it wants written. When no writer is given, the link lives
    only in per-client state.
    """
    state = load_state(state_dir) or {}
    state.update(
        {
            "client_id": client_id,
            "backend": ref.backend,
            "sheet_id": ref.sheet_id,
            "url": ref.url,
            "title": ref.title,
        }
    )
    if "created_at" not in state:
        state["created_at"] = date.today().isoformat()
    if field_writer is not None and field_key:
        field_writer(field_key, ref.url)
        state["custom_field_key"] = field_key
        state["custom_field_written"] = True
    save_state(state_dir, state)
    return state


# ---------------------------------------------------------------------------
# Setup and append
# ---------------------------------------------------------------------------


def default_title(client_id: str) -> str:
    return client_id + " Podcast Episodes"


def create_at_setup(
    client_id: str,
    backend: SpreadsheetBackend,
    state_dir: str,
    title: Optional[str] = None,
    field_writer: Optional[Callable[[str, str], None]] = None,
    field_key: Optional[str] = None,
) -> SheetRef:
    """Create the running spreadsheet once, idempotently, and store its link.

    Create-once, reuse-forever: first the per-client state file is consulted, then
    the backend is asked whether a sheet by this title already exists; only if
    neither has one is a new sheet created with the COLUMNS header. The link is then
    stored (state file, and a custom field when a writer is provided).
    """
    title = title or default_title(client_id)

    existing = load_state(state_dir)
    if existing and existing.get("url") and existing.get("title") == title:
        ref = SheetRef(
            backend=existing.get("backend", backend.name),
            sheet_id=existing["sheet_id"],
            url=existing["url"],
            title=title,
        )
        store_spreadsheet_link(client_id, ref, state_dir, field_writer, field_key)
        return ref

    found = backend.find(title)
    ref = found or backend.create(title, COLUMNS)
    store_spreadsheet_link(client_id, ref, state_dir, field_writer, field_key)
    return ref


def _submitter_name(record: dict) -> str:
    submitter = record.get("submitter")
    if isinstance(submitter, dict):
        parts = [submitter.get("first_name"), submitter.get("last_name")]
        name = " ".join(p for p in parts if p)
        if name:
            return name
    parts = [record.get("submitter_first_name"), record.get("submitter_last_name")]
    return " ".join(p for p in parts if p)


def row_from_record(record: dict) -> list[str]:
    """Build one running-spreadsheet row from a completed episode record."""

    def g(*keys, default=""):
        for key in keys:
            if key in record and record[key] not in (None, ""):
                return record[key]
        return default

    row = [
        g("episode_number"),
        g("publish_date", "date", default=date.today().isoformat()),
        g("episode_title", "title"),
        g("style"),
        g("runtime_minutes"),
        g("spoken_word_count"),
        g("podbean_permalink"),
        g("episode_package_url"),
        g("speech_script_url"),
        g("cover_image_url"),
        g("mp3_media_url"),
        _submitter_name(record),
        g("status", default="complete"),
    ]
    return [assert_cell_clean(str(cell)) for cell in row]


def append_episode(
    ref: SheetRef,
    backend: SpreadsheetBackend,
    record: dict,
    mode: str,
) -> list[str]:
    """Append one episode row. Hard-refuses Interview mode. Sends no message."""
    assert_personal_mode(mode)
    row = row_from_record(record)
    backend.append(ref, row)
    return row


# ---------------------------------------------------------------------------
# CLI (CSV backend only; Google and Notion need an injected runtime client)
# ---------------------------------------------------------------------------


def _load_record(value: str) -> dict:
    import sys

    if value == "-":
        return json.load(sys.stdin)
    with open(value, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="personal_spreadsheet.py",
        description="Personal-mode running spreadsheet: create at setup, append per episode.",
    )
    parser.add_argument("--state-dir", required=True, help="per-client state directory")
    parser.add_argument("--base-dir", default=None, help="CSV backend directory (defaults to state-dir)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("create-setup", parents=[common], help="create the running spreadsheet once (idempotent)")
    p_setup.add_argument("--client-id", required=True)
    p_setup.add_argument("--title", default=None)

    p_append = sub.add_parser("append", parents=[common], help="append one Personal-mode episode row")
    p_append.add_argument("--client-id", required=True)
    p_append.add_argument("--record-file", required=True, help="episode record JSON (path or -)")
    p_append.add_argument("--mode", default=PERSONAL_MODE)
    p_append.add_argument("--title", default=None)

    args = parser.parse_args(argv)
    base_dir = args.base_dir or args.state_dir
    backend = CsvBackend(base_dir)

    try:
        if args.command == "create-setup":
            ref = create_at_setup(args.client_id, backend, args.state_dir, args.title)
            out = {"action": "created_or_reused", **ref.to_dict()}
        elif args.command == "append":
            title = args.title or default_title(args.client_id)
            state = load_state(args.state_dir)
            if state and state.get("url"):
                ref = SheetRef(state.get("backend", backend.name), state["sheet_id"], state["url"], state.get("title", title))
            else:
                ref = create_at_setup(args.client_id, backend, args.state_dir, title)
            record = _load_record(args.record_file)
            row = append_episode(ref, backend, record, args.mode)
            out = {"action": "appended", "sheet": ref.to_dict(), "row": row}
        else:  # pragma: no cover
            parser.error("unknown command")
            return 2
    except ValueError as exc:
        import sys

        print(str(exc), file=sys.stderr)
        return 3

    print(json.dumps(out, indent=2) if args.json else json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
