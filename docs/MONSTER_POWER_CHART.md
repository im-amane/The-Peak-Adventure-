# Monster Power Chart

The complete sortable chart is available as [monster_power_chart.csv](monster_power_chart.csv).

It contains all 100 monsters and the following fields:

- Level, name and power rating
- Attack, defense, HP and speed
- Element and elemental weakness
- Advantage and disadvantage
- Special move and unique power
- Trait effect, boss flag and rank

The chart is generated from the canonical `monsters.json` file. To regenerate it after editing monster data:

```bash
python scripts/generate_monster_power_chart.py
```

The monster catalog tests verify the 100-level sequence, boss milestones, unique abilities and stories, strictly increasing power ratings, and that this CSV exactly matches the canonical JSON data.
