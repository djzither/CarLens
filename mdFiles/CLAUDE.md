# CarLens Project Context

## Project Goal

CarLens is NOT a car listing scraper.

CarLens is a personalized car decision engine.

Goal:

User enters:

- life situation
- budget
- priorities
- constraints

System:

1. recommends vehicle categories
2. recommends model + year ranges
3. explains recommendations
4. ranks listings
5. flags risks
6. later searches real listings

Primary value:

Help users decide WHAT to buy and avoid bad purchases.

Not:

"search all cars"

---

## Current MVP Scope

ONLY build:

buyer profile
→ recommend models/year ranges
→ rank sample listings
→ explain reasoning

Do NOT optimize for scale.

Do NOT add:

- AWS
- Docker
- auth
- scraping
- PostgreSQL
- agents
- background jobs
- production deployment
- vector databases
- ML models

No external APIs yet.

---

## Current Priority

Database quality and recommendation quality.

Recommendation quality matters more than UI quality.

The database is the product.

---

## Architecture Principles

Rule-based and transparent.

Avoid hidden heuristics.

Every score should be explainable.

Bad:

score = 83

Good:

score:
- reliability contribution
- budget contribution
- body type contribution
- mileage contribution
- risk penalties

Return explanations.

---

## Data Design

Vehicle profiles are:

model + year-range based

NOT:

Toyota Camry = good

BETTER:

Toyota Camry 2012–2017:
- buy confidence
- mileage ranges
- notes
- risks

Include:

- score
- confidence
- notes
- risk_flags

---

## Testing Philosophy

Scenario tests matter.

Examples:

student:
Camry > BMW

family_5_kids:
minivans/SUVs > sedans

outdoor_snow:
Outback > Corolla

Avoid fragile score assertions.

Test behaviors.

---

## Rebuild Commands

Run tests:

pytest

Run app:

streamlit run app/main.py

Run evaluation:

python -m evaluation.run_eval

## External API Policy

CarLens uses real providers sparingly.

Rules:

- Fixture providers must never be removed
- Fixtures are fallback if APIs fail
- Mock responses in tests
- Avoid real API calls in unit tests
- Return raw provider payloads
- Adapters own normalization
- Cache repeated requests during development
- Log external requests
- Prefer one real provider before adding more
- API failures should never crash aggregate search

Environment:

AUTODEV_API_KEY