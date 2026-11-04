"""Adapter-Registry.

Ein neuer Verein braucht in der Regel nur einen Eintrag in clubs.yaml.
Nur fuer ein noch unbekanntes Portal kommt hier ein Adapter dazu.
"""
from __future__ import annotations

from typing import Dict, Type

from .base import Adapter
from .generic_html import GenericHtmlAdapter
from .hrworks import HRworksAdapter
from .js_generic import JsGenericAdapter
from .personio import PersonioAdapter
from .softgarden import SoftgardenAdapter

REGISTRY: Dict[str, Type[Adapter]] = {
    GenericHtmlAdapter.name: GenericHtmlAdapter,
    HRworksAdapter.name: HRworksAdapter,
    JsGenericAdapter.name: JsGenericAdapter,
    PersonioAdapter.name: PersonioAdapter,
    SoftgardenAdapter.name: SoftgardenAdapter,
}


class UnknownAdapter(Exception):
    """In clubs.yaml steht ein Adapter, den es noch nicht gibt."""


def get_adapter(name: str) -> Type[Adapter]:
    try:
        return REGISTRY[name]
    except KeyError:
        raise UnknownAdapter(
            "Adapter '{}' ist nicht implementiert. Verfuegbar: {}".format(
                name, ", ".join(sorted(REGISTRY)))
        )


__all__ = ["Adapter", "REGISTRY", "get_adapter", "UnknownAdapter"]
