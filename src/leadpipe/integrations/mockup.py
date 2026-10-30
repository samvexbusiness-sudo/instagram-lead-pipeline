"""Plug point for your existing mockup-generation workflow.

The pipeline hands each exported lead to a `MockupHandoff`. The default one just
drops a JSON file per lead into data/handoff/mockup_queue/, which any other tool
(a Claude workflow, a script, Zapier, you by hand) can pick up.

To connect your real workflow later, write a class with a `submit(record)` method
and pass it to export.run(...). Nothing else in the pipeline needs to change.
The record format is documented in docs/ARCHITECTURE.md ("Hand-off record").
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class MockupHandoff(Protocol):
    def submit(self, record: dict) -> None: ...


class FolderQueueHandoff:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def submit(self, record: dict) -> None:
        path = self.folder / f"{record['username']}.json"
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
