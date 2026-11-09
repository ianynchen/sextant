"""An analysis runs with the garbage collector's thresholds raised, and gives them back
(plan 2 task 9b). The scan and the resolve build heaps of millions of objects that live to
the end of their stage, and at the interpreter's defaults most of the collector's time went
on full collections that found nothing to free (polar: 31 full collections, about 12 s). The
thresholds change when the collector runs, never what the analysis writes."""

import gc

import pytest

from sextant import api


def test_an_analysis_raises_the_thresholds_and_gives_them_back() -> None:
    before = gc.get_threshold()
    with api._fewer_collections():
        during = gc.get_threshold()
    assert during == api._ANALYZE_GC_THRESHOLDS
    assert all(raised >= default for raised, default in zip(during, before, strict=True))
    assert gc.get_threshold() == before


def test_a_failed_analysis_gives_the_thresholds_back() -> None:
    before = gc.get_threshold()
    with pytest.raises(RuntimeError), api._fewer_collections():
        raise RuntimeError("the analysis failed")
    assert gc.get_threshold() == before
