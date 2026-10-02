"""DCSMizzer's public library API, loaded on demand without running the CLI."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from ._version import __version__

if TYPE_CHECKING:
    from .archive import ArchivePolicy as ArchivePolicy, inspect_miz as inspect_miz
    from .builder import (
        BuildSpecError as BuildSpecError,
        build_miz as build_miz,
        load_build_spec as load_build_spec,
        verify_miz as verify_miz,
    )
    from .campaign import analyse_cmp as analyse_cmp
    from .capabilities import capabilities_report as capabilities_report
    from .lua import LuaDataError as LuaDataError, LuaLimits as LuaLimits
    from .mission import analyse_miz as analyse_miz

_PUBLIC_MODULES = {
    "ArchivePolicy": "archive",
    "BuildSpecError": "builder",
    "LuaDataError": "lua",
    "LuaLimits": "lua",
    "analyse_cmp": "campaign",
    "analyse_miz": "mission",
    "build_miz": "builder",
    "capabilities_report": "capabilities",
    "inspect_miz": "archive",
    "load_build_spec": "builder",
    "verify_miz": "builder",
}
__all__ = ["__version__", *_PUBLIC_MODULES]


def __getattr__(name: str) -> Any:
    module = _PUBLIC_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
