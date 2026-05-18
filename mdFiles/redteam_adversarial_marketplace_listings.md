# CarLens Red-Team Adversarial Marketplace Listings

Format: `id | raw listing (title + key fields) | expected failure mode | buyer trust impact | pytest target`

1. `A01 | "2016 Toyota Corolla clean title" + description "salvage title from minor hit" | explanation conflict (clean + salvage) | buyer sees contradictory trust signal | test_listing_normalizer.py::test_detect_clean_title_dirty_overrides_clean`
2. `A02 | "2016 Toyota Corolla not clean title" | normalization misread clean phrase | dirty car shown as clean | test_detect_clean_title_not_clean_title_is_dirty`
3. `A03 | "2016 Toyota Corolla clean title: no" | normalization misread clean phrase | explicit dirty statement ignored | test_detect_clean_title_clean_title_no_is_dirty`
4. `A04 | "No flood damage, clean carfax" | dirty-title false positive on "flood damage" substring | legit listing marked risky | test_detect_clean_title_no_flood_damage_not_dirty`
5. `A05 | title "2016 Corolla 85k", mileage field `185000` | confidence misses field/title contradiction | buyer assumes odometer certainty | test_low_confidence_when_title_and_field_mileage_conflict`
6. `A06 | title "engine replaced at 30k, chassis 190k" + mileage omitted | parsing picks wrong mileage candidate | hidden high-mileage risk | new param test for ambiguous compound mileage`
7. `A07 | "2016 Toyota Corolla 85,000mi (new motor 45k mi)" | ambiguity detection gap | confidence too high despite two mileages | extend title_has_ambiguous_mileage tests`
8. `A08 | year field `2016`, title "2024 Toyota Corolla update post" | year extraction confusion risk | stale model-year trust confusion | year-extraction precedence test`
9. `A09 | "2016 Toyota Corola LE" typo model | parsing miss -> invalid listing drop | buyer loses valid options silently | fuzzy spelling rejection test`
10. `A10 | "2016 Corolla LE", make/model absent | extraction dependency brittle | inconsistent inclusion/exclusion behavior | normalization extraction test`
11. `A11 | price "$10.5k" | parse_price drop (None) | ranking degrades from missing price | parse_price shorthand test`
12. `A12 | price "10 500" | parse_price fails on spaced numeral | listing appears incomplete | parse_price locale-format test`
13. `A13 | mileage "85k-ish" | parse_mileage fails | confidence/rank penalty from missing mileage | parse_mileage suffix-noise test`
14. `A14 | mileage "085000" | integer-like leading zeros accepted maybe okay | potential dedupe mismatch with text | parse + dedupe consistency test`
15. `A15 | URL dup: same post with `?fbclid=` tracker | dedupe miss by URL variant | duplicate spam boosts exposure | test_duplicate_url_ignores_tracking_query_params`
16. `A16 | URL dup: same path with trailing slash + query order swap | dedupe instability | duplicates feel manipulative | dedupe URL canonicalization test`
17. `A17 | source/id dup with case variance (`Craigslist`, `craigslist`) | dedupe casefold check | duplicate clutter | source-id casefold test`
18. `A18 | near-identical title tokens, different VIN/year hidden in description | false dedupe from token overlap | one of two real cars disappears | dedupe non-match guard test`
19. `A19 | same make/model/year, price diff $450, mileage diff 900, different neighborhoods | false dedupe via tolerance | buyer misses better option | tolerance-boundary non-dup test`
20. `A20 | same car reposted, price diff $600 after reduction | false non-dedupe | repeated listing gaming ranking | tolerance-boundary dup test`
21. `A21 | drive_type "AWD?" | normalization keeps raw token, AWD requirement fails | good car under-ranked due punctuation | drive_type normalization test`
22. `A22 | drive_type "All wheel drive" | AWD synonym not recognized | false AWD-negative reason | AWD synonym test`
23. `A23 | clean_title omitted, title says "rebuilt engine, clean title" | should remain clean | false dirty if rebuilt keyword misread | rebuilt-engine false-positive guard`
24. `A24 | "rebuilt title but clean title now" | conflict resolution unclear | explanation not explicit about conflict | reason ordering/conflict test`
25. `A25 | title "lemon yellow Corolla, clear title" | lemon false-positive risk | trust warning appears nonsensical | existing guard regression test`
26. `A26 | title "no salvage title, rebuilt transmission" | negation + risky words | simplistic regex may flip to dirty | negation precedence test`
27. `A27 | listing with only year/make/model | confidence medium/high drift risk | under-disclosed listings look too certain | confidence sparse floor test`
28. `A28 | title only with year/make/model and promotional text | inferred fields inflate certainty | buyer overtrusts inferred data | inferred-fields threshold test`
29. `A29 | wrong model but perfect price/mileage | conflicting positive/negative reasons | explanation sounds self-contradictory | conflicting_signals confidence test`
30. `A30 | known bad year but otherwise perfect | rank may stay too high | trust in "recommended" label erodes | cap-label for known bad year test`
31. `A31 | salvage in description, clean in title, explicit `clean_title=True` field | source-of-truth conflict | seller-provided boolean can mask text risk | raw-vs-text consistency test`
32. `A32 | mileage `2016` (year-like) + title "85k miles" | field dropped, title inferred | silent override unclear in explanation | inferred mileage provenance test`
33. `A33 | listing_id reused across two different URLs/models | source-id dedupe false positive | real alternative listing disappears | source-id dedupe guard test`
34. `A34 | model trim unknown "LE+" | warning only, still strong rank | buyer sees unrecognized trim but high fit | trim warning confidence penalty test`
35. `A35 | price missing, mileage missing, title missing clean status | many warnings but medium confidence edge | weak evidence appears actionable | confidence severity test`
36. `A36 | title "2016 Toyota Corolla 85k" + price `0` | parser accepts zero price | scammy bait price may rank high | zero-price trust rule test`
37. `A37 | title "cash only no title in hand" + clean_title True | clean flag override bug risk | legal/title risk hidden | dirty phrase expansion test`
38. `A38 | title "parts only bill of sale" | missing dirty-title lexicon | obvious non-roadworthy listing not flagged | dirty lexicon extension test`
39. `A39 | duplicate cross-post: same images/text, different URLs and source IDs | dedupe miss without strong heuristics | feed spam dominates top slots | cross-source duplicate heuristic test`
40. `A40 | title "2016 Toyota Corolla 85k miles", mileage 85000, but description "odometer replaced, true miles unknown" | trust-signal gap from disclaimers | confidence too high on bad odometer provenance | disclaimer warning test`

## Minimal deterministic patches implemented

1. `listing_normalizer.detect_clean_title`
   - Added negated clean-title patterns (`not clean title`, `clean title: no`) -> dirty.
   - Added negated dirty-title phrases (`no salvage history`, `no flood damage`) to avoid false dirty classification.
2. `listing_deduper._norm_url`
   - Canonicalizes URL by lowercasing scheme/host/path and removing common tracking params (`fbclid`, `utm_*`).
3. `listing_confidence.assess_listing_confidence`
   - Detects mileage contradiction when title contains a single mileage and explicit field disagrees.
   - Forces confidence to `Low` when contradiction is present.
