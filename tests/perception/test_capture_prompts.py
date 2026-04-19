"""Tests for the COCO prompt-whitelist plumbing in capture.py.

The capture daemon itself can only run on the OAK, but the prompt
validation + COCO ontology can be exercised purely in Python.
"""
from __future__ import annotations

import pytest

from src.perception.capture import (
    COCO_80_CLASSES,
    DEFAULT_HOUSEHOLD_PROMPTS,
    _resolve_prompts,
)


def test_coco_class_list_has_exactly_80_entries() -> None:
    assert len(COCO_80_CLASSES) == 80
    assert len(set(COCO_80_CLASSES)) == 80, "COCO class names must be unique"


def test_default_household_prompts_are_all_in_coco() -> None:
    coco = set(COCO_80_CLASSES)
    for name in DEFAULT_HOUSEHOLD_PROMPTS:
        assert name in coco, f"household prompt '{name}' not in COCO-80"


def test_resolve_prompts_accepts_valid_subset() -> None:
    out = _resolve_prompts(["chair", "bottle", "cup"])
    assert out == {"chair", "bottle", "cup"}


def test_resolve_prompts_all_keyword_returns_full_coco() -> None:
    out = _resolve_prompts(["all"])
    assert out == set(COCO_80_CLASSES)


def test_resolve_prompts_rejects_unknown_class() -> None:
    with pytest.raises(ValueError, match="popcorn_cup"):
        _resolve_prompts(["chair", "popcorn_cup"])


def test_resolve_prompts_rejects_capitalisation_typo() -> None:
    """COCO names are lowercase; capitalised input is rejected."""
    with pytest.raises(ValueError, match="'Cup'"):
        _resolve_prompts(["Cup", "bowl"])


def test_default_household_set_has_at_least_5_classes() -> None:
    """Sanity: the zero-config default needs to cover real scenes."""
    assert len(DEFAULT_HOUSEHOLD_PROMPTS) >= 5
