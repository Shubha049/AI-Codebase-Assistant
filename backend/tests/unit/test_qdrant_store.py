"""
These tests use qdrant-client's real embedded ':memory:' mode — a
genuine, documented mode the library ships, not a mock. Every assertion
here is against actual Qdrant behavior.
"""
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.services.vectorstore.qdrant_store import (
    collection_info,
    collection_name_for_repo,
    delete_collection,
    delete_points,
    ensure_collection,
    health_check,
    list_point_ids,
    search,
    upsert_chunks,
)


@pytest.fixture
def client():
    return QdrantClient(":memory:")


def test_health_check_against_real_embedded_instance(client):
    assert health_check(client) is True


def test_collection_name_is_filesystem_safe():
    name = collection_name_for_repo("abc-123-def", "aica_chunks")
    assert name == "aica_chunks_abc-123-def"


def test_collection_name_sanitizes_unsafe_characters():
    name = collection_name_for_repo("weird id/with spaces", "prefix")
    assert "/" not in name and " " not in name


def test_ensure_collection_creates_then_is_idempotent(client):
    ensure_collection(client, "test_col", vector_size=4)
    assert client.collection_exists("test_col")
    ensure_collection(client, "test_col", vector_size=4)  # should not raise
    assert client.collection_exists("test_col")


def test_upsert_and_retrieve_real_points(client):
    ensure_collection(client, "test_col", vector_size=3)
    points = [
        PointStruct(id="11111111-1111-1111-1111-111111111111", vector=[1.0, 0.0, 0.0], payload={"file": "a.py"}),
        PointStruct(id="22222222-2222-2222-2222-222222222222", vector=[0.0, 1.0, 0.0], payload={"file": "b.py"}),
    ]
    upsert_chunks(client, "test_col", points)
    info = collection_info(client, "test_col")
    assert info["points_count"] == 2
    assert info["vector_size"] == 3


def test_search_returns_closest_vector_first(client):
    ensure_collection(client, "test_col", vector_size=3)
    points = [
        PointStruct(id="11111111-1111-1111-1111-111111111111", vector=[1.0, 0.0, 0.0], payload={"label": "x"}),
        PointStruct(id="22222222-2222-2222-2222-222222222222", vector=[0.0, 1.0, 0.0], payload={"label": "y"}),
        PointStruct(id="33333333-3333-3333-3333-333333333333", vector=[0.9, 0.1, 0.0], payload={"label": "close_to_x"}),
    ]
    upsert_chunks(client, "test_col", points)
    results = search(client, "test_col", query_vector=[1.0, 0.0, 0.0], limit=2)
    assert results[0].payload["label"] == "x"
    assert results[1].payload["label"] == "close_to_x"


def test_delete_points_removes_only_specified_ids(client):
    ensure_collection(client, "test_col", vector_size=2)
    points = [
        PointStruct(id="11111111-1111-1111-1111-111111111111", vector=[1.0, 0.0], payload={}),
        PointStruct(id="22222222-2222-2222-2222-222222222222", vector=[0.0, 1.0], payload={}),
    ]
    upsert_chunks(client, "test_col", points)
    delete_points(client, "test_col", ["11111111-1111-1111-1111-111111111111"])
    remaining = list_point_ids(client, "test_col")
    assert remaining == {"22222222-2222-2222-2222-222222222222"}


def test_delete_collection_removes_it_entirely(client):
    ensure_collection(client, "test_col", vector_size=2)
    delete_collection(client, "test_col")
    assert not client.collection_exists("test_col")


def test_operations_on_nonexistent_collection_do_not_raise(client):
    # Real behavior verified: search/delete/info on a collection that was
    # never created should degrade gracefully, not throw.
    assert collection_info(client, "never_created") is None
    assert search(client, "never_created", [1.0, 0.0], limit=5) == []
    delete_points(client, "never_created", ["some-id"])  # must not raise
    delete_collection(client, "never_created")  # must not raise
    assert list_point_ids(client, "never_created") == set()


def test_list_point_ids_paginates_beyond_default_scroll_limit(client):
    """Real verification that list_point_ids's scroll loop actually
    paginates rather than silently truncating at Qdrant's default page
    size — inserts more points than one scroll page and confirms all are
    returned."""
    ensure_collection(client, "test_col", vector_size=2)
    points = [
        PointStruct(id=f"{i:08x}-0000-0000-0000-000000000000", vector=[float(i % 2), float((i + 1) % 2)], payload={})
        for i in range(1500)  # > the 1000-per-page limit used internally
    ]
    upsert_chunks(client, "test_col", points)
    ids = list_point_ids(client, "test_col")
    assert len(ids) == 1500
