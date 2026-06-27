from app.schemas.models import SearchResultItem
from app.services.search_service import SearchService
import pytest


class _SearchFilterSettings:
    def __init__(self, enabled: bool, rules: str = "") -> None:
        self.search_filter_enabled = enabled
        self.search_filter_rules = rules


class _PanSouStub:
    def __init__(self, enabled: bool, rules: str = "") -> None:
        self.settings = _SearchFilterSettings(enabled=enabled, rules=rules)


def test_dedupe_prefers_link_or_magnet() -> None:
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


def test_search_filter_is_empty_by_default() -> None:
    rows = [
        SearchResultItem(
            source="prowlarr",
            source_id="1",
            title="蜘蛛侠：纵横宇宙 2023 1080p BluRay x265",
            link="magnet:?xt=urn:btih:GOOD1",
            magnet="magnet:?xt=urn:btih:GOOD1",
            cloud_type="magnet",
            score=9,
        ),
        SearchResultItem(
            source="prowlarr",
            source_id="2",
            title="蜘蛛侠 无码 JAV FC2-PPV-123456 中文字幕",
            link="magnet:?xt=urn:btih:BAD1",
            magnet="magnet:?xt=urn:btih:BAD1",
            cloud_type="magnet",
            score=10,
        ),
        SearchResultItem(
            source="pansou",
            source_id="3",
            title="蜘蛛侠 115 网盘资源",
            link="https://115.com/s/keep",
            cloud_type="115",
            score=8,
        ),
    ]

    svc = SearchService(None, None, None)  # type: ignore[arg-type]
    svc.pansou = _PanSouStub(enabled=True)  # type: ignore[assignment]

    out = svc._filter_search_results(rows)

    assert [row.source_id for row in out] == ["1", "2", "3"]


def test_search_filter_removes_results_when_keyword_rules_are_configured() -> None:
    rows = [
        SearchResultItem(
            source="prowlarr",
            source_id="1",
            title="蜘蛛侠：纵横宇宙 2023 1080p BluRay x265",
            link="magnet:?xt=urn:btih:GOOD1",
            magnet="magnet:?xt=urn:btih:GOOD1",
            cloud_type="magnet",
            score=9,
        ),
        SearchResultItem(
            source="prowlarr",
            source_id="2",
            title="蜘蛛侠 无码 JAV FC2-PPV-123456 中文字幕",
            link="magnet:?xt=urn:btih:BAD1",
            magnet="magnet:?xt=urn:btih:BAD1",
            cloud_type="magnet",
            score=10,
        ),
    ]

    rules = (
        '[{"id":"r1","name":"规则 1","enabled":true,"match_mode":"keyword","pattern":"jav"},'
        '{"id":"r2","name":"规则 2","enabled":true,"match_mode":"keyword","pattern":"无码"}]'
    )
    svc = SearchService(None, None, None)  # type: ignore[arg-type]
    svc.pansou = _PanSouStub(enabled=True, rules=rules)  # type: ignore[assignment]

    out = svc._filter_search_results(rows)

    assert [row.source_id for row in out] == ["1"]


def test_search_filter_requires_all_comma_separated_keywords_on_same_line() -> None:
    rows = [
        SearchResultItem(
            source="prowlarr",
            source_id="1",
            title="蜘蛛侠 无码 1080p",
            link="magnet:?xt=urn:btih:GOOD1",
            magnet="magnet:?xt=urn:btih:GOOD1",
            cloud_type="magnet",
            score=9,
        ),
        SearchResultItem(
            source="prowlarr",
            source_id="2",
            title="蜘蛛侠 无码 JAV 1080p",
            link="magnet:?xt=urn:btih:BAD1",
            magnet="magnet:?xt=urn:btih:BAD1",
            cloud_type="magnet",
            score=10,
        ),
    ]

    rules = (
        '[{"id":"r1","name":"规则 1","enabled":true,"match_mode":"keyword","pattern":"蜘蛛侠,jav"}]'
    )
    svc = SearchService(None, None, None)  # type: ignore[arg-type]
    svc.pansou = _PanSouStub(enabled=True, rules=rules)  # type: ignore[assignment]

    out = svc._filter_search_results(rows)

    assert [row.source_id for row in out] == ["1"]


def test_search_filter_can_be_disabled() -> None:
    rows = [
        SearchResultItem(
            source="prowlarr",
            source_id="2",
            title="蜘蛛侠 无码 JAV FC2-PPV-123456 中文字幕",
            link="magnet:?xt=urn:btih:BAD1",
            magnet="magnet:?xt=urn:btih:BAD1",
            cloud_type="magnet",
            score=10,
        )
    ]

    svc = SearchService(None, None, None)  # type: ignore[arg-type]
    svc.pansou = _PanSouStub(enabled=False)  # type: ignore[assignment]

    out = svc._filter_search_results(rows)

    assert [row.source_id for row in out] == ["2"]


@pytest.mark.asyncio
async def test_search_response_includes_search_filter_counts() -> None:
    class _ProviderSettings:
        enable_pansou = True
        enable_prowlarr = True
        pansou_search_limit_enabled = False
        prowlarr_search_limit_enabled = False

    class _PanSou:
        def __init__(self) -> None:
            self.settings = _ProviderSettings()
            self.settings.search_filter_enabled = True
            self.settings.search_filter_rules = (
                '[{"id":"r1","name":"规则 1","enabled":true,"match_mode":"keyword","pattern":"jav"}]'
            )

        async def search(self, keyword: str, limit: int | None) -> list[SearchResultItem]:
            return [
                SearchResultItem(
                    source="pansou",
                    source_id="1",
                    title=f"{keyword} 正常资源",
                    link="https://115.com/s/ok",
                    cloud_type="115",
                    score=8,
                )
            ]

    class _Prowlarr:
        def __init__(self, settings: _ProviderSettings) -> None:
            self.settings = settings

        async def search(self, keyword: str, limit: int | None) -> list[SearchResultItem]:
            return [
                SearchResultItem(
                    source="prowlarr",
                    source_id="2",
                    title=f"{keyword} JAV 无码",
                    link="magnet:?xt=urn:btih:BAD1",
                    magnet="magnet:?xt=urn:btih:BAD1",
                    cloud_type="magnet",
                    score=10,
                )
            ]

    pansou = _PanSou()
    svc = SearchService(pansou, _Prowlarr(pansou.settings), None)  # type: ignore[arg-type]

    out = await svc.search("req-1", "蜘蛛侠", None)

    assert out.total_before_search_filter == 2
    assert out.search_filter_removed == 1
    assert out.total_after_search_filter == 1
    assert out.total == 1
