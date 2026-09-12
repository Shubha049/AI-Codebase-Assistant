import pytest

from app.services.embeddings.base import EmbeddingError, EmbeddingProvider
from app.services.embeddings.retry import embed_batch_with_retry


class _FlakyProvider(EmbeddingProvider):
    """Fails a configurable number of times before succeeding — lets us
    verify retry COUNT and eventual success/failure without any real
    network call."""

    def __init__(self, fail_times: int):
        self._fail_times = fail_times
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "flaky"

    @property
    def model_name(self) -> str:
        return "flaky-model"

    @property
    def dimension(self) -> int:
        return 4

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise EmbeddingError(f"simulated transient failure #{self.call_count}")
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


def test_succeeds_immediately_if_no_failure():
    provider = _FlakyProvider(fail_times=0)
    result = embed_batch_with_retry(provider, ["a", "b"], max_retries=3)
    assert len(result) == 2
    assert provider.call_count == 1


def test_retries_and_eventually_succeeds():
    provider = _FlakyProvider(fail_times=2)
    result = embed_batch_with_retry(provider, ["a"], max_retries=5)
    assert result == [[0.1, 0.2, 0.3, 0.4]]
    assert provider.call_count == 3  # failed twice, succeeded on 3rd


def test_gives_up_after_max_retries_and_raises():
    provider = _FlakyProvider(fail_times=10)
    with pytest.raises(EmbeddingError):
        embed_batch_with_retry(provider, ["a"], max_retries=3)
    assert provider.call_count == 3  # never exceeds the configured cap


def test_max_retries_of_one_means_no_retry_at_all():
    provider = _FlakyProvider(fail_times=1)
    with pytest.raises(EmbeddingError):
        embed_batch_with_retry(provider, ["a"], max_retries=1)
    assert provider.call_count == 1
