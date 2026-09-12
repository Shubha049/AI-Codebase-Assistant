from types import SimpleNamespace

from app.services.architecture.explorer import get_graph, get_impact, get_overview


def test_architecture_service_can_be_imported():
    assert callable(get_graph)
    assert callable(get_impact)
    assert callable(get_overview)
