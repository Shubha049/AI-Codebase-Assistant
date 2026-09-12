import math

import pytest

from app.config import Settings
from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.factory import build_embedding_provider
from app.services.embeddings.providers.mock_provider import MockEmbeddingProvider


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def test_mock_provider_identical_text_produces_identical_vector():
    p = MockEmbeddingProvider()
    v1, v2 = p.embed_batch(["def foo(): pass", "def foo(): pass"])
    assert v1 == v2


def test_mock_provider_similar_text_scores_higher_than_unrelated():
    p = MockEmbeddingProvider()
    base = p.embed_batch(["def authenticate_user(username, password):"])[0]
    similar = p.embed_batch(["def authenticate_admin(username, password):"])[0]
    unrelated = p.embed_batch(["banana fruit tropical smoothie recipe"])[0]
    assert _cosine(base, similar) > _cosine(base, unrelated)


def test_mock_provider_vectors_are_unit_normalized():
    p = MockEmbeddingProvider()
    v = p.embed_batch(["some text"])[0]
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-9


def test_mock_provider_respects_configured_dimension():
    p = MockEmbeddingProvider(dimension=128)
    assert p.dimension == 128
    assert len(p.embed_batch(["x"])[0]) == 128


def test_mock_provider_empty_text_produces_zero_vector_not_crash():
    p = MockEmbeddingProvider()
    v = p.embed_batch([""])[0]
    assert len(v) == p.dimension
    assert all(x == 0.0 for x in v)


def test_factory_builds_mock_provider_by_default():
    settings = Settings(environment="test", embedding_provider="mock")
    provider = build_embedding_provider(settings)
    assert provider.provider_name == "mock"


def test_factory_refuses_mock_in_production():
    settings = Settings(environment="production", embedding_provider="mock", database_url="postgresql://x/y")
    with pytest.raises(EmbeddingError, match="not allowed when ENVIRONMENT=production"):
        build_embedding_provider(settings)


def test_settings_validate_for_production_also_refuses_mock():
    """The SECOND, independent guard — Settings.validate_for_production()
    — not just the factory."""
    settings = Settings(environment="production", embedding_provider="mock", database_url="postgresql://x/y")
    with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER=mock"):
        settings.validate_for_production()


def test_factory_refuses_openai_without_api_key():
    settings = Settings(environment="test", embedding_provider="openai", openai_api_key=None)
    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
        build_embedding_provider(settings)


def test_factory_builds_openai_provider_with_key():
    settings = Settings(environment="test", embedding_provider="openai", openai_api_key="sk-fake-key-for-construction-test")
    provider = build_embedding_provider(settings)
    assert provider.provider_name == "openai"


def test_factory_builds_ollama_provider():
    settings = Settings(environment="test", embedding_provider="ollama", ollama_url="http://localhost:11434")
    provider = build_embedding_provider(settings)
    assert provider.provider_name == "ollama"


def test_factory_builds_local_provider():
    settings = Settings(environment="test", embedding_provider="local")
    provider = build_embedding_provider(settings)
    assert provider.provider_name == "local"
    # Known dimension for the default model, answerable WITHOUT loading
    # the actual model (see local_provider.py's _MODEL_DIMENSIONS table) —
    # this assertion works even though the model itself can't be
    # downloaded in this sandbox.
    assert provider.dimension == 384
