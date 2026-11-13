# ADR 017 — No budgets, currencies or prices (for now)

- **Status:** **Accepted** on 2026-11-13 (owner instruction: "I don't want currencies or meal
  budgets or anything. I want to remove budgets from the app altogether for now, and remove
  currency and meal budget per person from the new trip UI").
- **Date:** 2026-11-13
- **Related:** [`002-api-strategy.md`](002-api-strategy.md) (FX provider, price sources),
  [`012-phase-2-data-and-search-choices.md`](012-phase-2-data-and-search-choices.md),
  [`016-phase-6-meals-and-area-destinations.md`](016-phase-6-meals-and-area-destinations.md),
  [`../app-plan.md`](../app-plan.md) D10 and Phase 8, [`../product-brief.md`](../product-brief.md)

## Context

The product brief listed a trip currency and a meal budget per person as trip inputs, user-entered
restaurant prices with price bands and a budget fit, and a daily FX job (Frankfurter) for
conversions. Phase 2 built the columns (`app.trip.currency_code`, `meal_budget_per_person`,
`price_band_thresholds`, `app.installation.home_currency_code`), the `app.price_record` table and
`geo.fx_rate`; Phase 5 put currency and meal budget on the new-trip form. Prices, bands and FX
were Phase 8 and had no endpoints. The owner does not want any of it.

## Decision

1. **Removed from the app and the API:** the trip's currency, meal budget per person and price-band
   thresholds; the installation's home currency. `TripCreate` and `TripUpdate` reject them as
   unknown fields; `Trip` no longer has them. The new-trip form has no currency or budget field,
   and the trip screen shows no budget.
2. **Removed from the database** (migration `0006`): those four columns, `app.price_record` and
   `geo.fx_rate`. The migration refuses to run if either table holds rows. The trips' currency and
   budget values are discarded (the owner asked for this); a downgrade restores the columns, not
   the values.
3. **Removed from the plan:** price records (expected and actual prices), price bands and their
   defaults (D10), the budget-fit calculation and the reason code `FITS_BUDGET`, the daily FX job
   and Frankfurter (ADR 002's FX choice is not used), and the KPI "price provenance". Phase 8
   becomes "Add a restaurant" without prices.
4. **Kept:** the GeoNames country and currency reference rows (`geo.country.default_currency_code`,
   `geo.currency`). They are imported with the gazetteer and unused; removing them would change
   the import for no benefit. `geo.restaurant_profile.provider_price_level` stays as it was:
   always null.
5. **Places to eat carry no price**, as before: no provider price level, no user price.

## Alternatives

| Alternative | Why not |
|---|---|
| Hide the fields in the app, keep the API and tables | Dead columns and endpoints to maintain; the owner asked to remove budgets altogether |
| Keep price records without currencies | A price without a currency is not a fact (CLAUDE.md, never invent data) |
| Also drop `geo.currency` and the country currency | Imported reference data; touches the gazetteer import and its tests for no user-visible gain |

## Consequences

- Documents changed in the same commit: product brief, architecture, data model, app plan, KPIs,
  build prompts, API evaluation (a note), CLAUDE.md, README.
- Bringing prices, budgets or currencies back needs a new ADR, a migration and the owner's approval
  (CLAUDE.md, rule 3); this ADR's "for now" leaves that open.
- Older app builds still send `currency_code` or `meal_budget_per_person` when creating a trip; the
  API now answers `422`. The owner installs the new APK.
