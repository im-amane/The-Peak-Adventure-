"""Generate the sortable CSV reference chart from the canonical monster catalog."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "monsters.json"
OUTPUT = ROOT / "docs" / "monster_power_chart.csv"
FIELDS = (
    "level",
    "name",
    "power",
    "attack_power",
    "defense",
    "hp",
    "speed",
    "element",
    "weakness",
    "advantage",
    "disadvantage",
    "special_move",
    "unique_power",
    "trait_effect",
    "boss",
    "rank",
)


def render_csv(monsters: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for monster in monsters:
        row = {field: monster.get(field, "") for field in FIELDS}
        row["boss"] = str(bool(row["boss"])).lower()
        writer.writerow(row)
    return output.getvalue()


def main() -> None:
    monsters = json.loads(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_csv(monsters), encoding="utf-8", newline="")
    print(f"Wrote {len(monsters)} monster rows to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
