import re

from pydantic import BaseModel, Field

STEPS_HEADING = "## Steps"
_STEPS_RE = re.compile(r"(?:^|\n)##\s*Steps\s*\n", re.IGNORECASE)
_NUMBERED_LINE_RE = re.compile(r"^\d+\.\s+.+", re.MULTILINE)


class RecipeItem(BaseModel):
    """KitchenOwl's write schema is strictly {name, description, optional} —
    id and ordering are rejected by the API with a 400."""

    name: str
    description: str = ""
    optional: bool = False


class Recipe(BaseModel):
    id: int | None = None
    name: str
    description: str = ""
    steps: list[str] = Field(default_factory=list)
    items: list[RecipeItem] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    def to_wire_payload(self) -> dict:
        """{name, description, items, tags} — description has steps embedded."""
        return {
            "name": self.name,
            "description": serialize_description(self.description, self.steps),
            "items": [i.model_dump() for i in self.items],
            "tags": self.tags,
        }


def parse_description(raw: str) -> tuple[str, list[str]]:
    """Split a KitchenOwl description into (free_text, steps).

    No '## Steps' heading -> whole string is free text, steps=[] (legacy
    recipes created before this convention existed).
    """
    match = _STEPS_RE.search(raw)
    if not match:
        return raw.strip(), []
    free_text = raw[: match.start()].strip()
    steps = [
        re.sub(r"^\d+\.\s+", "", line.strip())
        for line in raw[match.end() :].splitlines()
        if line.strip()
    ]
    return free_text, steps


def serialize_description(free_text: str, steps: list[str]) -> str:
    """Inverse of parse_description."""
    free_text = (free_text or "").strip()
    if not steps:
        return free_text
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    steps_section = f"{STEPS_HEADING}\n{numbered}"
    return f"{free_text}\n\n{steps_section}" if free_text else steps_section


def normalize_tags(raw_tags: list) -> list[str]:
    """KitchenOwl returns tags as [{id, name}] on read, accepts [str] on write."""
    return [t.get("name", "") if isinstance(t, dict) else str(t) for t in raw_tags]


def has_unmigrated_steps(raw_description: str) -> bool:
    """True if description holds a numbered list with no '## Steps' heading —
    steps embedded the old way, before the heading convention existed.
    parse_description() returns these as unstructured free text (steps=[])."""
    if _STEPS_RE.search(raw_description):
        return False
    return len(_NUMBERED_LINE_RE.findall(raw_description)) >= 2
