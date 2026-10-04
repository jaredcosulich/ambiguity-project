---
title: "Hold the rotating hero word still in screenshots"
mode: ui
createdAt: "2026-10-04T19:03:47Z"
source: proposed-plan
---

## Summary

The hero's rotating mission word (`src/components/MissionLine.astro`) starts animating 2 seconds after load, so scenario screenshots catch it at whatever frame the capture lands on ("students|", "international devel|"). Captures of the home page, Hero and MissionLine can therefore differ run to run for reasons unrelated to any change, and there is no scenario showing the reduced-motion behaviour.

## Key Decisions

- Keep the animation exactly as it is for visitors; only make it hold still when the page is being captured.
- Let a URL flag pin the typewriter (e.g. `?typewriter=static` holds the first word with no caret blink), so a scenario opts in explicitly rather than the page guessing it is being screenshotted.
- Add a reduced-motion scenario that shows the whole-word swap rather than the typing frames.

## Implementation

1. In `src/components/MissionLine.astro`, read the flag in the inline script and skip scheduling `typewriterStep` when it is set; also stop the caret blink via a class.
2. Point `hero-default`, `hero-long-quote-and-long-word`, `missionline-default`, `home-full-content`, `home-full-content-mobile` at the pinned URL and recapture.
3. Add a scenario that emulates reduced motion (or uses the existing `reduceMotion` path in `src/lib/typewriter.ts`) and captures after one swap.
4. Extend `src/lib/typewriter.test.ts` only if the step function changes.