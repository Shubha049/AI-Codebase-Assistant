"""
These tests verify OUR code's request-building and response-parsing
logic by mocking the HTTP layer — they do NOT verify the real OpenAI or
Ollama services are reachable or behave as documented (both are blocked/
unavailable in this environment; see providers' own module docstrings).
What they DO prove: given a realistic response shape, our provider
correctly builds the request and correctly parses the result — and given
an error response, it raises EmbeddingError with a useful message rather
than leaking a raw httpx exception.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.embeddings.base import EmbeddingError
from app.services.embeddings.providers.ollama_provider import OllamaEmbeddingProvider
from app.services.embeddings.providers.openai_provider import OpenAIEmbeddingProvider


# --- OpenAI ---

def _fake_openai_response(vectors: list[list[float]]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    }
    return resp


def test_openai_provider_parses_successful_response_in_correct_order():
    provider = OpenAIEmbeddingProvider(api_key="sk-fake", model_name="text-embedding-3-small")
    fake_resp = _fake_openai_response([[0.1, 0.2], [0.3, 0.4]])
    with patch("httpx.post", return_value=fake_resp) as mock_post:
        result = provider.embed_batch(["hello", "world"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["input"] == ["hello", "world"]
    assert call_kwargs["json"]["model"] == "text-embedding-3-small"
    assert call_kwargs["headers"]["Authorization"] == "Bearer sk-fake"


def test_openai_provider_reorders_by_index_not_response_order():
    """OpenAI's API doesn't guarantee response order matches request
    order — it returns an explicit `index` per item. Verify we actually
    sort by it rather than trusting array position."""
    provider = OpenAIEmbeddingProvider(api_key="sk-fake")
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "data": [
            {"index": 1, "embedding": [9.0, 9.0]},
            {"index": 0, "embedding": [1.0, 1.0]},
        ]
    }
    with patch("httpx.post", return_value=resp):
        result = provider.embed_batch(["first", "second"])
    assert result == [[1.0, 1.0], [9.0, 9.0]]


def test_openai_provider_raises_embedding_error_on_api_error_status():
    provider = OpenAIEmbeddingProvider(api_key="sk-bad-key")
    error_resp = httpx.Response(
        status_code=401, text='{"error": "invalid api key"}',
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
    )
    with patch("httpx.post", side_effect=httpx.HTTPStatusError("401", request=error_resp.request, response=error_resp)):
        with pytest.raises(EmbeddingError, match="401"):
            provider.embed_batch(["text"])


def test_openai_provider_raises_embedding_error_on_network_failure():
    provider = OpenAIEmbeddingProvider(api_key="sk-fake")
    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        with pytest.raises(EmbeddingError, match="request failed"):
            provider.embed_batch(["text"])


def test_openai_provider_rejects_missing_api_key_at_construction():
    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingProvider(api_key="")


def test_openai_provider_dimension_known_for_standard_models():
    provider = OpenAIEmbeddingProvider(api_key="sk-fake", model_name="text-embedding-3-large")
    assert provider.dimension == 3072


def test_openai_provider_unknown_model_raises_clear_error():
    provider = OpenAIEmbeddingProvider(api_key="sk-fake", model_name="not-a-real-model")
    with pytest.raises(EmbeddingError, match="Unknown OpenAI"):
        _ = provider.dimension


# --- Ollama ---

def test_ollama_provider_builds_correct_request_and_parses_response():
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", model_name="nomic-embed-text")
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"embedding": [0.5, 0.6, 0.7]}

    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        result = provider.embed_batch(["some code"])

    assert result == [[0.5, 0.6, 0.7]]
    call_args = mock_post.call_args
    assert call_args.args[0] == "http://localhost:11434/api/embeddings"
    assert call_args.kwargs["json"]["model"] == "nomic-embed-text"
    assert call_args.kwargs["json"]["prompt"] == "some code"


def test_ollama_provider_strips_trailing_slash_from_base_url():
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434/", model_name="m")
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"embedding": [0.1]}
    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        provider.embed_batch(["x"])
    assert mock_post.call_args.args[0] == "http://localhost:11434/api/embeddings"


def test_ollama_provider_calls_once_per_text_in_batch():
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", model_name="m")
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"embedding": [0.1]}
    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        provider.embed_batch(["a", "b", "c"])
    assert mock_post.call_count == 3


def test_ollama_provider_raises_embedding_error_when_unreachable():
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", model_name="m")
    with patch("httpx.Client.post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(EmbeddingError, match="Could not reach Ollama"):
            provider.embed_batch(["x"])


def test_ollama_provider_dimension_derived_from_probe_embedding():
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", model_name="m")
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3, 0.4, 0.5]}
    with patch("httpx.Client.post", return_value=fake_resp):
        assert provider.dimension == 5


def test_ollama_provider_malformed_response_raises_clear_error():
    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", model_name="m")
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"unexpected_key": "no embedding here"}
    with patch("httpx.Client.post", return_value=fake_resp):
        with pytest.raises(EmbeddingError, match="Unexpected Ollama response"):
            provider.embed_batch(["x"])
