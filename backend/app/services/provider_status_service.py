from __future__ import annotations

import asyncio
import time
from typing import Protocol

from app.adapters.c115 import C115Adapter
from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.tmdb import TMDBAdapter
from app.schemas.models import ProviderStatusItem, ProviderStatusResponse


class Checkable(Protocol):
    async def check(self) -> tuple[bool, str]: ...


class ProviderStatusService:
    def __init__(
        self,
        pansou: PanSouAdapter,
        prowlarr: ProwlarrAdapter,
        tmdb: TMDBAdapter,
        c115: C115Adapter,
    ) -> None:
        self.providers: dict[str, Checkable] = {
            "pansou": pansou,
            "prowlarr": prowlarr,
            "tmdb": tmdb,
            "c115": c115,
        }

    async def get_status(self, request_id: str) -> ProviderStatusResponse:
        async def probe(name: str):
            begin = time.perf_counter()
            ok, msg = await self.providers[name].check()
            latency = int((time.perf_counter() - begin) * 1000)
            return ProviderStatusItem(name=name, ok=ok, message=msg, latency_ms=latency)

        items = await asyncio.gather(*(probe(name) for name in self.providers))
        return ProviderStatusResponse(request_id=request_id, providers=list(items))
