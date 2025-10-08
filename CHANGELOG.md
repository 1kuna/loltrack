## 2025-10-07 — GIS Calibration & Weights

- Added Generalized Improvement Score (GIS) pipeline with per-domain inst scores, smoothing, role/queue scoping, outlier damping, and per-match delta clamp.
- Calibration & gating per (queue, role): stages 0/1/2; ranked SR-only influence.
- Patch easing: widen Huber clamp for 3 matches after patch change.
- Champion mastery guardrail: cap per-match negative domain impact; knob `gis.maxNegativeImpactLowMastery`.
- New APIs:
  - `GET /api/gis/summary` (schema `gis.v1`): includes resolved `context`, `confidence_band`, calibration flags, and `focus_debug`.
  - `GET/PUT /api/gis/weights` (schema `weights.v1`): file-backed role domain weights; PUT admin-gated via `LOLTRACK_ADMIN=1`.
- UI:
  - Dashboard GIS card with calibration state and confidence ribbon.
  - Matches domain badges (thresholded; max 3).
  - Match drawer domain contributions.
- Tests: gating transitions, band guard, hysteresis, patch easing, mastery cap, and weights validation.

