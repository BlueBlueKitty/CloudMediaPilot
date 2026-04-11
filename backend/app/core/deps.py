from functools import lru_cache

from app.adapters.c115 import C115Adapter
from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.quark import QuarkAdapter
from app.adapters.tmdb import TMDBAdapter
from app.core.config import ProviderSettings, get_settings
from app.services.app_config_service import AppConfigStore, build_provider_settings
from app.services.provider_status_service import ProviderStatusService
from app.services.search_service import SearchService
from app.services.task_service import TaskService


@lru_cache
def get_app_config_store() -> AppConfigStore:
    settings = get_settings()
    return AppConfigStore(settings.config_env_path)


def _provider_settings() -> ProviderSettings:
    runtime = get_settings()
    app_cfg = get_app_config_store().get()
    return build_provider_settings(runtime, app_cfg)


def get_search_service() -> SearchService:
    settings = _provider_settings()
    return SearchService(PanSouAdapter(settings), ProwlarrAdapter(settings), TMDBAdapter(settings))


def get_task_service() -> TaskService:
    settings = _provider_settings()
    return TaskService(C115Adapter(settings), QuarkAdapter(settings), settings)


def get_provider_status_service() -> ProviderStatusService:
    settings = _provider_settings()
    return ProviderStatusService(
        PanSouAdapter(settings),
        ProwlarrAdapter(settings),
        TMDBAdapter(settings),
        C115Adapter(settings),
    )
