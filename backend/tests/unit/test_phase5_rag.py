from app.config import Settings
from app.services.llm import MockLLMProvider, build_llm_provider
from app.services.rag.confidence import confidence
from app.services.rag.prompt_builder import build_prompt
from app.services.rag.retrieval import RetrievedChunk


def chunk(i, score, content):
    return RetrievedChunk(str(i), score, "r", "repo", f"app/{i}.py", "python", f"app.{i}", None, f"fn{i}", "function", i, i+2, content)


def test_prompt_deduplicates_and_preserves_citations():
    c1 = chunk(1, .9, "def login():\n    return True")
    c2 = chunk(2, .8, "def other():\n    return False")
    bundle = build_prompt("How does login work?", [c1, c1, c2])
    assert len(bundle.chunks) == 2
    assert "[S1] app/1.py:1-3" in bundle.user_prompt
    assert "[S2] app/2.py:2-4" in bundle.user_prompt


def test_confidence_levels():
    assert confidence([]) == "Low"
    assert confidence([.3]) == "Medium"
    assert confidence([.8, .77]) == "High"


def test_mock_llm_is_grounded_in_retrieved_context():
    p = MockLLMProvider()
    result = p.generate("system", "QUESTION: x\n\nRETRIEVED CONTEXT:\n[S1] app/a.py:1-2\nprint('hello')")
    assert "app/a.py" in result.text
    assert "hello" in result.text


def test_mock_llm_forbidden_in_production():
    settings = Settings(environment="production", llm_provider="mock", database_url="postgresql://x")
    try:
        build_llm_provider(settings)
    except Exception as exc:
        assert "production" in str(exc).lower()
    else:
        raise AssertionError("Mock LLM must not be selectable in production")


def test_prompt_dedup_keeps_highest_scoring_duplicate():
    low = chunk(1, .41, "same")
    high = chunk(1, .91, "same")
    bundle = build_prompt("q", [low, high])
    assert len(bundle.chunks) == 1
    assert bundle.chunks[0].score == .91
    assert "score=0.9100" in bundle.user_prompt


def test_prompt_keeps_distinct_overlapping_chunks():
    a = chunk(1, .9, "line one\nline two")
    b = chunk(2, .8, "line two\nline three")
    bundle = build_prompt("q", [a, b])
    assert len(bundle.chunks) == 2
