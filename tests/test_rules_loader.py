"""Loading and saving the rule set.

Everything that can be wrong with a rule set must be caught here, at load
time, with a message naming the offender -- never half-way through
categorising ten thousand rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pf.rules.loader import (
    load_rule_set,
    parse_categories,
    parse_rules,
    save_categories,
    save_rules,
)
from pf.rules.model import Category, Rule, RuleError

CATEGORIES = {
    "version": 1,
    "categories": [
        {"name": "Food", "kind": "spending", "parent": None},
        {"name": "Groceries", "kind": "spending", "parent": "Food"},
        {"name": "Transfers", "kind": "transfer", "parent": None},
    ],
}

RULES = {
    "version": 1,
    "rules": [
        {"pattern": "MERCADONA", "match": "contains", "category": "Groceries"},
        {"pattern": "BON AREA", "match": "contains", "category": "Groceries", "priority": 50},
    ],
}


def write(tmp_path: Path, categories=CATEGORIES, rules=RULES) -> tuple[Path, Path]:
    cat_path = tmp_path / "categories.json"
    rule_path = tmp_path / "rules.json"
    cat_path.write_text(json.dumps(categories), encoding="utf-8")
    rule_path.write_text(json.dumps(rules), encoding="utf-8")
    return cat_path, rule_path


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_loads_categories_and_rules(tmp_path):
    categories, rules = load_rule_set(*write(tmp_path))
    assert [c.name for c in categories] == ["Food", "Groceries", "Transfers"]
    assert [r.pattern for r in rules] == ["MERCADONA", "BON AREA"]


def test_rule_ids_come_from_file_order(tmp_path):
    # So that reading the file top to bottom tells you the precedence among
    # rules of equal priority.
    _, rules = load_rule_set(*write(tmp_path))
    assert [r.id for r in rules] == [1, 2]


def test_nesting_is_read(tmp_path):
    categories, _ = load_rule_set(*write(tmp_path))
    groceries = next(c for c in categories if c.name == "Groceries")
    assert groceries.parent == "Food"


def test_optional_fields_default_sensibly(tmp_path):
    _, rules = load_rule_set(*write(tmp_path))
    first = rules[0]
    assert first.priority == 100
    assert first.kind_filter is None
    assert first.note is None


# --------------------------------------------------------------------------
# Everything that should be refused
# --------------------------------------------------------------------------


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(RuleError) as err:
        load_rule_set(tmp_path / "nope.json", tmp_path / "also-nope.json")
    assert "missing rule file" in str(err.value)


def test_malformed_json_names_the_file(tmp_path):
    bad = tmp_path / "categories.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(RuleError) as err:
        load_rule_set(bad, tmp_path / "rules.json")
    assert "not valid JSON" in str(err.value)


def test_unknown_category_in_a_rule_names_the_category(tmp_path):
    rules = {"version": 1, "rules": [
        {"pattern": "X", "match": "contains", "category": "Nonexistent"}
    ]}
    with pytest.raises(RuleError) as err:
        load_rule_set(*write(tmp_path, rules=rules))
    assert "Nonexistent" in str(err.value)


def test_invalid_regex_names_the_pattern(tmp_path):
    rules = {"version": 1, "rules": [
        {"pattern": "[unclosed", "match": "regex", "category": "Groceries"}
    ]}
    with pytest.raises(RuleError) as err:
        load_rule_set(*write(tmp_path, rules=rules))
    assert "[unclosed" in str(err.value)


def test_unknown_match_type_is_refused(tmp_path):
    rules = {"version": 1, "rules": [
        {"pattern": "X", "match": "fuzzy", "category": "Groceries"}
    ]}
    with pytest.raises(RuleError) as err:
        load_rule_set(*write(tmp_path, rules=rules))
    assert "fuzzy" in str(err.value)


def test_duplicate_rule_points_at_both_lines(tmp_path):
    rules = {"version": 1, "rules": [
        {"pattern": "MERCADONA", "match": "contains", "category": "Groceries"},
        {"pattern": "MERCADONA", "match": "contains", "category": "Transfers"},
    ]}
    with pytest.raises(RuleError) as err:
        load_rule_set(*write(tmp_path, rules=rules))
    message = str(err.value)
    assert "rules[2]" in message and "rules[1]" in message


def test_same_pattern_with_different_match_types_is_allowed(tmp_path):
    # Not a duplicate: 'exact MERCADONA' and 'contains MERCADONA' are
    # genuinely different rules.
    rules = {"version": 1, "rules": [
        {"pattern": "MERCADONA", "match": "exact", "category": "Groceries"},
        {"pattern": "MERCADONA", "match": "contains", "category": "Groceries"},
    ]}
    _, loaded = load_rule_set(*write(tmp_path, rules=rules))
    assert len(loaded) == 2


def test_duplicate_category_is_refused(tmp_path):
    categories = {"version": 1, "categories": [
        {"name": "Groceries"}, {"name": "Groceries"},
    ]}
    with pytest.raises(RuleError) as err:
        load_rule_set(*write(tmp_path, categories=categories))
    assert "duplicate category" in str(err.value)


def test_missing_parent_is_refused(tmp_path):
    categories = {"version": 1, "categories": [
        {"name": "Groceries", "parent": "Food"},
    ]}
    with pytest.raises(RuleError) as err:
        load_rule_set(*write(tmp_path, categories=categories))
    assert "Food" in str(err.value)


def test_a_category_cannot_parent_itself(tmp_path):
    categories = {"version": 1, "categories": [
        {"name": "Food", "parent": "Food"},
    ]}
    with pytest.raises(RuleError):
        load_rule_set(*write(tmp_path, categories=categories))


def test_bad_category_kind_is_refused(tmp_path):
    categories = {"version": 1, "categories": [{"name": "Weird", "kind": "sideways"}]}
    with pytest.raises(RuleError) as err:
        load_rule_set(*write(tmp_path, categories=categories))
    assert "sideways" in str(err.value)


def test_a_list_where_an_object_is_expected_is_refused(tmp_path):
    path = tmp_path / "categories.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(RuleError):
        load_rule_set(path, tmp_path / "rules.json")


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def test_round_trips_without_losing_anything(tmp_path):
    categories = [
        Category("Food"),
        Category("Groceries", parent="Food"),
        Category("Transfers", kind="transfer"),
    ]
    rules = [
        Rule("MERCADONA", "contains", "Groceries", priority=50, note="the big one"),
        Rule("PEYRONA", "contains", "Transfers", kind_filter="transfer_person"),
    ]
    cat_path, rule_path = tmp_path / "c.json", tmp_path / "r.json"
    save_categories(categories, cat_path)
    save_rules(rules, rule_path)

    loaded_cats, loaded_rules = load_rule_set(cat_path, rule_path)
    assert [(c.name, c.kind, c.parent) for c in loaded_cats] == [
        ("Food", "spending", None),
        ("Groceries", "spending", "Food"),
        ("Transfers", "transfer", None),
    ]
    assert loaded_rules[0].note == "the big one"
    assert loaded_rules[0].priority == 50
    assert loaded_rules[1].kind_filter == "transfer_person"


def test_writing_is_deterministic(tmp_path):
    # These files live in git. A rule change must produce a one-line diff,
    # not a reshuffle of the whole file.
    rules = [Rule("A", "contains", "Groceries"), Rule("B", "prefix", "Groceries")]
    first, second = tmp_path / "1.json", tmp_path / "2.json"
    save_rules(rules, first)
    save_rules(rules, second)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_unset_optional_fields_are_omitted_from_the_file(tmp_path):
    # Keeps the common case terse and the diffs readable.
    path = tmp_path / "r.json"
    save_rules([Rule("MERCADONA", "contains", "Groceries")], path)
    entry = json.loads(path.read_text(encoding="utf-8"))["rules"][0]
    assert set(entry) == {"pattern", "match", "category", "priority"}


def test_accents_survive_writing(tmp_path):
    # Category names are Jose's, and may well be Spanish.
    path = tmp_path / "c.json"
    save_categories([Category("Niñera")], path)
    text = path.read_text(encoding="utf-8")
    assert "Niñera" in text               # written as a character, not ñ
    assert parse_categories(json.loads(text))[0].name == "Niñera"


def test_file_is_created_with_its_directory(tmp_path):
    target = tmp_path / "nested" / "deeper" / "rules.json"
    save_rules([Rule("A", "contains", "Groceries")], target)
    assert target.exists()


# --------------------------------------------------------------------------
# parse_* directly
# --------------------------------------------------------------------------


def test_parse_rules_requires_a_rules_list():
    with pytest.raises(RuleError) as err:
        parse_rules({"version": 1}, [Category("Groceries")])
    assert "'rules' list" in str(err.value)


def test_parse_categories_requires_a_categories_list():
    with pytest.raises(RuleError) as err:
        parse_categories({"version": 1})
    assert "'categories' list" in str(err.value)
