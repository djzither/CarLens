from src.listings.listing_deduper import dedupe_listings, pick_more_complete_listing


def _corolla_base(**overrides) -> dict:
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 10500,
        "mileage": 92000,
        "clean_title": True,
        "trim": "LE",
        "raw_title": "2016 Toyota Corolla LE clean title 92k miles",
    }
    listing.update(overrides)
    return listing


def test_duplicate_url_is_deduped():
    sparse = _corolla_base(
        listing_url="https://example.com/listing/abc",
        price=None,
        mileage=None,
        clean_title=None,
        raw_title="Corolla",
    )
    complete = _corolla_base(
        listing_url="https://example.com/listing/abc/",
        price=10500,
        mileage=92000,
        clean_title=True,
    )

    result = dedupe_listings([sparse, complete])

    assert len(result) == 1
    assert result[0] is complete
    assert result[0]["price"] == 10500
    assert result[0]["mileage"] == 92000


def test_duplicate_source_and_listing_id_is_deduped():
    sparse = _corolla_base(
        listing_id="abc123",
        source="craigslist",
        price=None,
        mileage=None,
        raw_title="Corolla",
    )
    complete = _corolla_base(
        listing_id="abc123",
        source="craigslist",
        listing_url="https://example.com/listing/abc123",
    )

    result = dedupe_listings([sparse, complete])

    assert len(result) == 1
    assert result[0] is complete
    assert result[0]["listing_url"] == "https://example.com/listing/abc123"


def test_same_car_with_slightly_different_title_is_deduped():
    first = _corolla_base(
        raw_title="2016 Toyota Corolla LE clean title 92k miles",
    )
    second = _corolla_base(
        raw_title="2016 Toyota Corolla LE - clean title, 92,000 miles",
        listing_url="https://example.com/listing/other",
    )

    result = dedupe_listings([first, second])

    assert len(result) == 1


def test_different_trims_are_not_deduped():
    le_listing = _corolla_base(trim="LE", raw_title="2016 Toyota Corolla LE")
    se_listing = _corolla_base(trim="SE", raw_title="2016 Toyota Corolla SE")

    result = dedupe_listings([le_listing, se_listing])

    assert len(result) == 2


def test_different_prices_are_not_deduped():
    cheaper = _corolla_base(price=9000)
    dearer = _corolla_base(price=14500)

    result = dedupe_listings([cheaper, dearer])

    assert len(result) == 2


def test_different_mileages_are_not_deduped():
    lower = _corolla_base(mileage=60000)
    higher = _corolla_base(mileage=140000)

    result = dedupe_listings([lower, higher])

    assert len(result) == 2


def test_keep_most_complete_record():
    sparse = _corolla_base(
        clean_title=None,
        listing_url=None,
        raw_title="Corolla",
    )
    complete = _corolla_base(
        listing_url="https://example.com/listing/complete",
        raw_title="2016 Toyota Corolla LE clean title 92k miles with full details",
    )

    assert pick_more_complete_listing(sparse, complete) is complete

    result = dedupe_listings([sparse, complete])

    assert len(result) == 1
    assert result[0] is complete
    assert len(result[0]["raw_title"]) > len("Corolla")


def test_duplicate_url_ignores_tracking_query_params():
    first = _corolla_base(
        listing_url="https://facebook.com/marketplace/item/123?fbclid=abc&utm_source=feed",
        price=None,
        mileage=None,
        clean_title=None,
    )
    second = _corolla_base(
        listing_url="https://facebook.com/marketplace/item/123",
    )

    result = dedupe_listings([first, second])

    assert len(result) == 1
