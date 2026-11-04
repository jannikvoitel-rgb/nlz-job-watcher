"""Gemeinsame Testhilfen."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


class FakeFetcher:
    """Ersetzt den HTTP-Client: liefert gespeicherte Seiten statt Netzabrufen."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.calls = []
        self.request_count = 0

    def get_text(self, url: str) -> str:
        """Erst exakte Treffer, dann Teilstrings in Einfuegereihenfolge.

        Eine Listen-URL ist oft ein Teilstring der Detail-URL
        ("/de" steckt in "/de?id=123"), deshalb gehoert das Detail-Muster
        im Aufruf vor die Listen-URL.
        """
        self.calls.append(url)
        self.request_count += 1
        if url in self.pages:
            return self.pages[url]
        for needle, content in self.pages.items():
            if needle in url:
                return content
        raise AssertionError("Unerwarteter Abruf im Test: {}".format(url))

    def allowed(self, url: str) -> bool:
        return True

    def close(self) -> None:
        pass


@pytest.fixture(scope="session")
def filters() -> dict:
    return yaml.safe_load((ROOT / "filters.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def classifier(filters):
    from nlzwatch.classify import Classifier
    return Classifier(filters)
