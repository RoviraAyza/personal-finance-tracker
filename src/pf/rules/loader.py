"""Reading and writing the rule set.

`rules/categories.json` and `rules/rules.json` are the source of truth. They
are data, version-controlled and hand-editable -- the customising tables of
this project. The database copy exists so queries can join to it, never as the
authority.

Everything that could be wrong with a rule set is detected **here**, at load
time, with a message naming the offending rule. Nothing should ever fail
part-way through categorising ten thousand transactions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Sequence

from pf.rules.model import (
    MATCH_TYPES,
    REGEX,
    Category,
    Rule,
    RuleError,
)

FORMAT_VERSION = 1

#: Default locations, relative to the repository root.
CATEGORIES_FILE = Path("rules") / "categories.json"
RULES_FILE = Path("rules") / "rules.json"


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuleError(f"missing rule file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuleError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuleError(f"{path}: expected an object at the top level")
    return data


def parse_categories(data: dict[str, Any]) -> list[Category]:
    raw = data.get("categories")
    if not isinstance(raw, list):
        raise RuleError("categories file: expected a 'categories' list")

    categories: list[Category] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise RuleError(f"categories: expected objects, got {type(entry).__name__}")
        name = str(entry.get("name", "")).strip()
        category = Category(
            name=name,
            kind=str(entry.get("kind", "spending")),
            parent=(entry.get("parent") or None),
        )
        if category.name in seen:
            raise RuleError(f"duplicate category: {category.name!r}")
        seen.add(category.name)
        categories.append(category)

    # A parent must exist, or the tree is broken in a way that only shows up
    # when something tries to roll categories up.
    names = {c.name for c in categories}
    for category in categories:
        if category.parent and category.parent not in names:
            raise RuleError(
                f"category {category.name!r} has parent {category.parent!r}, "
                "which does not exist"
            )
        if category.parent == category.name:
            raise RuleError(f"category {category.name!r} is its own parent")

    return categories


def parse_rules(data: dict[str, Any], categories: Sequence[Category]) -> list[Rule]:
    raw = data.get("rules")
    if not isinstance(raw, list):
        raise RuleError("rules file: expected a 'rules' list")

    known = {c.name for c in categories}
    rules: list[Rule] = []
    seen: dict[tuple[str, str, str | None], int] = {}

    for index, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            raise RuleError(f"rules[{index}]: expected an object")

        match = str(entry.get("match", "contains"))
        if match not in MATCH_TYPES:
            raise RuleError(
                f"rules[{index}]: unknown match type {match!r}; "
                f"expected one of {sorted(MATCH_TYPES)}"
            )

        # ids come from file order, so reading the file top to bottom tells you
        # the precedence among rules of equal priority.
        rule = Rule(
            pattern=str(entry.get("pattern", "")),
            match=match,
            category=str(entry.get("category", "")),
            priority=int(entry.get("priority", 100)),
            kind_filter=(entry.get("kind_filter") or None),
            note=(entry.get("note") or None),
            id=index,
        )

        if rule.category not in known:
            raise RuleError(
                f"rules[{index}] ({rule.pattern!r}) names category "
                f"{rule.category!r}, which is not defined"
            )
        if rule.match == REGEX:
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                raise RuleError(
                    f"rules[{index}]: {rule.pattern!r} is not a valid regex: {exc}"
                ) from exc
        if rule.key in seen:
            raise RuleError(
                f"rules[{index}] duplicates rules[{seen[rule.key]}]: "
                f"{rule.pattern!r} / {rule.match}"
            )

        seen[rule.key] = index
        rules.append(rule)

    return rules


def load_rule_set(
    categories_path: Path | str = CATEGORIES_FILE,
    rules_path: Path | str = RULES_FILE,
) -> tuple[list[Category], list[Rule]]:
    """Read and fully validate both files."""
    categories = parse_categories(_read_json(Path(categories_path)))
    rules = parse_rules(_read_json(Path(rules_path)), categories)
    return categories, rules


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def _dump(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON deterministically.

    Stable ordering and two-space indentation matter: these files live in git,
    and a rule change should produce a one-line diff, not a reshuffle.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def save_categories(categories: Sequence[Category], path: Path | str = CATEGORIES_FILE) -> None:
    _dump(
        Path(path),
        {
            "version": FORMAT_VERSION,
            "categories": [
                {"name": c.name, "kind": c.kind, "parent": c.parent}
                for c in categories
            ],
        },
    )


def save_rules(rules: Sequence[Rule], path: Path | str = RULES_FILE) -> None:
    payload: list[dict[str, Any]] = []
    for rule in rules:
        entry: dict[str, Any] = {
            "pattern": rule.pattern,
            "match": rule.match,
            "category": rule.category,
            "priority": rule.priority,
        }
        # Optional keys are omitted when unset, so the common case stays terse.
        if rule.kind_filter:
            entry["kind_filter"] = rule.kind_filter
        if rule.note:
            entry["note"] = rule.note
        payload.append(entry)
    _dump(Path(path), {"version": FORMAT_VERSION, "rules": payload})
