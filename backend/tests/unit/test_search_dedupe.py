from app.schemas.models import SearchResultItem
from app.services.search_service import SearchService


def test_dedupe_uses_magnet_or_link() -> None:
    rows = [
        SearchResultItem(
            source="pansou", source_id="1", title="a", link="l1", magnet="m1", score=8
        ),
        SearchResultItem(
            source="prowlarr", source_id="2", title="b", link="l2", magnet="m1", score=9
        ),
        SearchResultItem(
            source="prowlarr", source_id="3", title="c", link="l3", magnet=None, score=7
        ),
    ]
    out = SearchService._dedupe(rows)
    assert len(out) == 2
    assert out[0].score >= out[1].score
