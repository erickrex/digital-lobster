from __future__ import annotations

from src.adapters.base import PluginAdapter
from src.adapters.blocks import GutenbergCoreAdapter, KadenceBlocksAdapter
from src.adapters.custom_fields import (
    AcfAdapter,
    CarbonFieldsAdapter,
    MetaBoxAdapter,
    PodsAdapter,
)
from src.adapters.forms import (
    ContactForm7Adapter,
    GravityFormsAdapter,
    NinjaFormsAdapter,
    WpFormsAdapter,
)
from src.adapters.seo import AioSeoAdapter, RankMathAdapter, YoastAdapter
from src.adapters.utilities import RedirectAdapter, WidgetSidebarAdapter


def default_adapters() -> list[PluginAdapter]:
    """Return all built-in plugin adapters."""
    return [
        AcfAdapter(),
        PodsAdapter(),
        MetaBoxAdapter(),
        CarbonFieldsAdapter(),
        YoastAdapter(),
        RankMathAdapter(),
        AioSeoAdapter(),
        ContactForm7Adapter(),
        WpFormsAdapter(),
        GravityFormsAdapter(),
        NinjaFormsAdapter(),
        GutenbergCoreAdapter(),
        KadenceBlocksAdapter(),
        RedirectAdapter(),
        WidgetSidebarAdapter(),
    ]


def build_adapter_registry(
    adapters: list[PluginAdapter] | None = None,
) -> dict[str, PluginAdapter]:
    """Build a dict mapping plugin family → adapter instance."""
    return {a.plugin_family(): a for a in (adapters or default_adapters())}
