"""Mapping validation errors, reported all at once and in plain words."""

from __future__ import annotations


class MappingError(Exception):
    """A mapping spec is invalid. Carries every problem found, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Invalid mapping spec:\n" + "\n".join(f"  - {p}" for p in problems))
