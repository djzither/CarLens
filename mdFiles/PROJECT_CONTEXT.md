# CarLens Project Context

## Vision

CarLens is not a car listing scraper.

CarLens is a personalized car decision engine that helps users decide:

"What should I buy?"

instead of:

"Show me every car."

Long-term flow:

User enters:
- life situation
- budget
- priorities
- constraints

CarLens:

1. recommends vehicle categories
2. recommends model/year ranges
3. explains recommendations
4. ranks listings
5. flags risks
6. later tracks better deals

---

## Current MVP Goal

Build:

buyer profile
→ model recommendation
→ listing ranking
→ explanations

No external APIs yet.

No scraping.

No cloud infrastructure.

No auth.

No SQL.

Priority:

Recommendation quality > UI quality

---

## Product Positioning

Not:

another CarGurus clone

Instead:

"Tell me your situation and budget and CarLens helps decide what to buy."

---

## Core Product Insight

Search already exists.

Decision support is the opportunity.

The value is helping users avoid bad decisions.

---

## Database Philosophy

Vehicle knowledge is model + year-range based.

Bad:

Toyota Camry = good

Better:

Toyota Camry 2012–2017:
- buy confidence
- notes
- risk flags
- mileage expectations

---

## Initial Vehicles

Starting small:

- Toyota Camry
- Toyota Corolla
- Honda Civic
- Mazda3
- Subaru Outback

Do not attempt all cars initially.

---

## Initial Buyer Profiles

- student
- outdoor_snow

Add later:

- family_5_kids
- retired_comfort
- sporty_budget

---

## Recommendation Philosophy

Scores should be explainable.

Avoid:

score = 82

Prefer:

- reliability contribution
- budget contribution
- year-range confidence
- penalties
- explanations

---

## Future Ideas

Later:

- Auto.dev
- MarketCheck
- EPA MPG data
- recall data
- favorite tracking
- listing alerts