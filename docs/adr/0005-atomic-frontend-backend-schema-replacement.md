# ADR 0005: Atomic Frontend + Backend Schema Replacement

**Status:** Accepted
**Date:** 2026-05-08
**Authors:** Tom S, Claude (Opus 4.7)

---

## Context

The v1 → v2 migration changed the public API contract substantially. Previous response shapes were:

```json
{
  "ticker": "ASML.AS",
  "composite_score": 76.4,
  "signal": "Buy",
  "scoring_breakdown": {
    "valuation": 35,
    "financial_health": 82,
    ...
  },
  "piotroski_f": 6,
  "altman_z": 4.2,
  "graham_number": 312.4
}
```

v2 atomically replaces this with:

```json
{
  "ticker": "ASML.AS",
  "horizons": {
    "long_term":   {"score": 78.4, "signal": "Buy", "passes_gates": true, "blockers": [], "recommended_account": null},
    "medium_term": {"score": 71.2, "signal": "Buy", "passes_gates": true, "blockers": [], "recommended_account": null},
    "short_term":  {"score": 42.1, "signal": "Hold", "passes_gates": false, "blockers": ["max_realized_vol_1y"], "recommended_account": "CTO"}
  },
  "sub_scores": {"valuation": 35, "health": 82, "profitability": 91, "growth": 73, "shareholder": 56, "risk_legacy": 64},
  "valuation": { "fair_value_low": 612, "fair_value_mid": 745, "fair_value_high": 882, "mos_low": -0.11, "mos_mid": 0.08, "mos_high": 0.28, "wacc_used": 0.084, "warnings": [] },
  "quality": { "piotroski_f": 8, "altman_z": 4.2, "altman_zone": "Safe", "graham_number": 312.4, "earnings_quality_score": 78, "moat_score": 88, "m_score": -2.4, "sloan_accruals": -0.024, "cash_conversion_ratio_5y": 1.05 },
  "risk": { "risk_score": 71, "realized_vol_1y": 0.32, "max_drawdown_3y": -0.43, "net_debt_ebitda": -0.18, "interest_coverage": 38.4, "beta": 1.12 },
  "momentum": { "momentum_12_1": -0.04, "rs_3m": -0.07, "above_50dma": false, ... }
}
```

This is not a backwards-compatible addition. The fields `composite_score`, `signal`, `scoring_breakdown` are **removed**, not deprecated. The new fields `horizons`, `sub_scores`, `valuation`, `quality`, `risk`, `momentum` are required for any v2 consumer to function.

The choice for the public API rollout:

1. **Versioned API** — keep `/api/v1/company/{ticker}` returning the legacy shape, expose `/api/v2/company/{ticker}` returning the new shape. Frontend migrates to v2; backend serves both indefinitely.
2. **Deprecation period** — add v2 fields alongside v1, mark v1 as deprecated, cutover later.
3. **Atomic replacement** — ship M10 (backend new schema) and M11 (frontend new schema) together. The new shape replaces the old shape in one PR's worth of work; no consumer ever sees a half-migrated state.

### Constraints

- The project is solo-developed. There is **one** frontend consumer (this repo's `frontend/`) and effectively zero external API users. There is no third-party integration that would break if the legacy shape disappeared.
- The schema changes are extensive: legacy `composite_score` becomes three scores, legacy `signal` becomes three signals plus gates plus blockers, and entirely new blocks (`valuation`, `momentum`, `quality.earnings_quality_score`) are added that have no v1 equivalent.
- Maintaining v1 in parallel would require keeping the legacy scoring path alive in `scoring_engine.py` and a translation layer in the API. Both add ~500 lines of code that exists only to serve the legacy shape — code that has to be tested, maintained, and eventually removed anyway.

---

## Decision

Ship M10 (backend) and M11 (frontend) **together**, atomically replacing the v1 schema with the v2 schema in one merge.

Concrete commitments:

1. **Backend M10**:
   - `backend/app/models/horizons.py` — new shared sub-models (`HorizonScoring`, `DCFValuation`, `QualitySignals`, `RiskSignals`, `MomentumSignals`, `SubScores`).
   - `backend/app/models/company.py`, `screener.py`, `portfolio.py`, `watchlist.py` — all rewritten to consume the new sub-models.
   - `backend/app/services/scoring_service.py` — emits the new schema; legacy `composite_score`/`signal` are no longer in the response.
   - `tests/test_api_contract.py` — pins the new schema. Snapshot tests guarantee shape stability going forward.
   - `openapi_v2.json` — committed to the repo root as a frozen reference for any future external consumer.

2. **Frontend M11**:
   - `frontend/src/lib/types.ts` — `Horizon` type, `CompanyDetail`, `ScreenerResultItem`, etc. all updated.
   - `frontend/src/components/ui/HorizonSelector.tsx`, `HorizonScoreCard.tsx`, `DCFFairValueRange.tsx`, `MoSBar.tsx`, `EarningsQualityPanel.tsx`, `MomentumPanel.tsx`, `CTOWarningBanner.tsx` — new components.
   - `frontend/src/app/company/[ticker]/page.tsx`, `screener/page.tsx`, `portfolio/page.tsx`, `watchlist/page.tsx` — rewritten to consume the new schema.
   - `frontend/src/hooks/` — `useCompany`, `useScreener`, `useHorizon` adapters for the new shape.

3. **One PR per branch, both branches required to merge** before the schema change lands on `main`. The atomic-replacement discipline is enforced at the merge level, not at the code-review level — `feat/m10-api` and `feat/m11-frontend` ship to `main` in lockstep.

4. **No transitional fields**. The legacy `composite_score`, `signal`, `scoring_breakdown` are removed cleanly. No `Optional[float]` placeholder, no `deprecated: true` flag — just gone.

5. **CHANGELOG documents the breaking change loudly** (see `CHANGELOG.md` `[0.4.0]` `### Changed` section).

---

## Consequences

### Positive

- **No bridging code to maintain**. The codebase has exactly one schema active at any time. No translation layer, no legacy path branches, no "if v1 client" logic in the API.
- **Cleaner test surface**. Tests pin one schema; no need to test "v1 shape compatibility" or "v2 shape compatibility" or "translation correctness".
- **Faster iteration after the merge**. Future schema additions (M14 forward valuation columns, M15 portfolio risk metrics) extend a single shape, not two.
- **Forced coupling = forced consistency**. The frontend cannot drift from the backend because they ship together. Any backend addition that breaks the schema has to be fixed in the frontend before the merge.
- **OpenAPI spec is frozen and committed**. Even though we don't have external consumers, `openapi_v2.json` is in the repo, regenerated by FastAPI on schema changes. A future external consumer has a single source of truth.
- **Scope is right-sized for solo development**. The constraint "no external consumers" makes versioned APIs over-engineered; atomic replacement is the smallest discipline that delivers a clean cut.

### Negative / trade-offs

- **No staged rollout**. If the v2 frontend has a bug that the v1 frontend didn't have, there's no way to roll back to v1 without reverting both PRs. Mitigated by the snapshot test suite (`tests/test_api_contract.py`, frontend snapshot/e2e tests in M11) but not eliminated.
- **No blue-green deployment story**. A production cutover would require both backend and frontend to deploy in the same window. For this project (single dev, single user) it doesn't matter; for a multi-tenant production deployment it would.
- **Higher coordination cost during the actual M10+M11 development**. The two branches had to be developed in tandem; a backend change that broke the frontend schema couldn't merge until the frontend caught up. Resolved with the worktree pattern (separate working trees, integration branch), but added scheduling friction.
- **Loss of evidence**. Any logs, dashboards, or external reports that referenced `composite_score` are silently broken. There is no compatibility shim to map old field names. Acceptable for this project (no external dashboards) but a real cost for a production system.
- **No communication grace period**. External consumers (had there been any) would have no warning. Deprecation periods give consumers time to adapt; atomic replacement gives them none.
- **Risk of "version sprawl forever"**. Without the discipline of atomic releases, every added field could become the start of a new compatibility layer. The project commits to the discipline; future schema changes must be additions or be batched into a v3 release with the same atomic pattern.

---

## Alternatives considered

### Alternative 1: Versioned API (`/v1/`, `/v2/` prefixes)

**Rejected because** there are no external consumers needing v1. Maintaining v1 indefinitely is overhead for zero benefit. If a future external consumer arrives and needs a frozen contract, the right response is "use the OpenAPI spec at `openapi_v2.json` to generate a client", not "maintain a parallel API".

### Alternative 2: Deprecation period — both shapes coexist for N weeks, then v1 is removed

**Rejected because** the deprecation period itself doubles the schema's complexity. During the period, every endpoint must serialise both shapes; every test must verify both; every frontend caller must check which shape is active. With one consumer, the period gains nothing — the consumer can update in lockstep with the API.

### Alternative 3: Additive migration — keep `composite_score` AND add the new fields, mark legacy as `deprecated`

**Rejected because** the legacy `composite_score` was *systematically wrong* on the audit-flagged fields (fabricated EBIT, fabricated interest expense, etc.). Keeping it alive would be telling consumers "here's a number we know is wrong, please don't use it". Better to remove it.

### Alternative 4: Feature flag — gate the new schema behind a `?api_version=2` query param

**Rejected because** feature flags in API responses are a known antipattern. They proliferate, they break caches, they make logs untraceable. Atomic replacement is cleaner than any flag-based approach.

### Alternative 5: Parallel deployment — run two backends, route by header

**Rejected as over-engineered** for a solo project with one consumer. This is the right answer for a multi-tenant production API; it's the wrong answer here.

---

## When this ADR would be revisited

If any of these become true:
- An external consumer integrates against the API → versioned API becomes the right pattern.
- The schema needs another breaking change (v2 → v3) → revisit whether atomic replacement is still the right discipline at that scale.
- Rollback time becomes a real production constraint (e.g. a regression in the frontend forces a sub-hour rollback) → blue-green deployment of both layers is the right answer.

---

## References

- M10 commit: `68f77e9 feat(api): replace public schema with three-horizon scoring + DCF + quality blocks (M10)`
- M11 commit: `8cd37ad feat(frontend): three-horizon UI with DCF range, earnings quality, momentum panels (M11)`
- Implementation:
  - `backend/app/models/horizons.py`, `company.py`, `screener.py`, `portfolio.py`, `watchlist.py` — Pydantic schema.
  - `backend/app/services/scoring_service.py` — emits the new schema.
  - `tests/test_api_contract.py` — schema regression tests.
  - `openapi_v2.json` — committed OpenAPI spec.
  - `frontend/src/lib/types.ts` — TypeScript types.
  - `frontend/src/components/ui/HorizonSelector.tsx`, `HorizonScoreCard.tsx`, `DCFFairValueRange.tsx`, `MoSBar.tsx`, `EarningsQualityPanel.tsx`, `MomentumPanel.tsx`, `CTOWarningBanner.tsx` — new components.
- Companion ADRs: [0001](0001-three-horizon-scoring.md) (the schema change driver — three horizons replacing one composite).
- CHANGELOG: [`CHANGELOG.md`](../../CHANGELOG.md) `[0.4.0]` `### Changed` block.
