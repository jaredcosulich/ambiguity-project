---
title: "Cover the mission line's prefix, suffix and single-word states"
mode: ui
createdAt: "2026-10-04T20:27:12Z"
source: proposed-plan
---

## Summary

The coverage plan for `src/components/MissionLine.astro` lists four code paths, and only the rotating-word paths have screenshots (`missionline-default`, `missionline-reduced-motion`). An editor can clear the mission prefix or suffix, or enter a single mission word, in Site Settings; none of those states has a scenario, so a layout break there would go unnoticed.

## Key Decisions

- Use the existing `?typewriter=static` flag so the new captures stay steady.
- Seed through new `.codeyam/seeds/*.json` variants of `home-full.json` rather than new props, since MissionLine reads its text from `settings.json`.

## Implementation

1. Add seeds with an empty `missionPrefix`, an empty `missionSuffix`, and a single-word `missionWords`.
2. Register `MissionLine - No Prefix Or Suffix` and `MissionLine - Single Word` component scenarios at `/isolated-components/MissionLine?typewriter=static`.
3. Mark the matching states covered in `.codeyam/scenarios/coverage-plan/missionline.json` via the scenario taxonomy.