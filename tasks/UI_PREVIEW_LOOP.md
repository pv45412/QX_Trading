# UI Development Preview Loop

This policy is mandatory for any milestone that modifies visible UI. It is not authorization to expand a milestone's approved scope.

## Required loop

1. Start the local frontend and backend required by the active task.
2. After each meaningful UI slice, open the affected route with Playwright or a browser.
3. Capture a preview screenshot under `data/reports/<task_id>/preview/`.
4. Inspect hierarchy, spacing, information density, responsive behavior, canonical/legacy labeling, and unavailable/blocked states.
5. Repair obvious visual or product issues before implementing the next slice.
6. Validate desktop and mobile before final independent checker review.
7. Do not defer the first visual inspection until the end of the milestone.

## Required final evidence

- First preview
- Final preview
- Major-state screenshots
- Visual issues discovered and repaired during implementation
- Desktop and mobile validation results

If a task does not modify visible UI, its final evidence must record this policy as `NOT_APPLICABLE`.
