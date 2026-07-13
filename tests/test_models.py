import pytest

from kitchenowl_mcp.models import (
    Recipe,
    RecipeItem,
    normalize_tags,
    parse_description,
    serialize_description,
)


def test_parse_description_no_heading_is_all_free_text() -> None:
    assert parse_description("Just some notes.") == ("Just some notes.", [])


def test_parse_description_extracts_steps_in_order() -> None:
    raw = "Intro text.\n\n## Steps\n1. Crack eggs.\n2. Whisk them.\n3. Cook."
    description, steps = parse_description(raw)
    assert description == "Intro text."
    assert steps == ["Crack eggs.", "Whisk them.", "Cook."]


@pytest.mark.parametrize(
    "free_text,steps",
    [
        ("", []),
        ("Free text only.", []),
        ("", ["Step one.", "Step two."]),
        ("Free text.", ["Step one.", "Step two."]),
    ],
)
def test_round_trip(free_text: str, steps: list[str]) -> None:
    serialized = serialize_description(free_text, steps)
    assert parse_description(serialized) == (free_text.strip(), steps)


def test_wire_payload_never_includes_id_or_ordering() -> None:
    recipe = Recipe(
        id=42,
        name="Omelet",
        description="Simple.",
        steps=["Crack eggs.", "Cook."],
        items=[RecipeItem(name="eggs")],
        tags=["breakfast"],
    )
    payload = recipe.to_wire_payload()
    assert set(payload.keys()) == {"name", "description", "items", "tags"}
    for item in payload["items"]:
        assert "id" not in item
        assert "ordering" not in item
    assert "## Steps" in payload["description"]


def test_normalize_tags_flattens_dicts_and_passes_through_strings() -> None:
    assert normalize_tags([{"id": 1, "name": "breakfast"}]) == ["breakfast"]
    assert normalize_tags(["breakfast"]) == ["breakfast"]
