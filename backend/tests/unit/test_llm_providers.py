import httpx
import pytest

from app.services.llm.providers import OpenAILLMProvider, OllamaLLMProvider


def test_openai_request_parsing(monkeypatch):
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            return httpx.Response(200, request=httpx.Request("POST", "http://test"), json={"choices": [{"message": {"content": "answer"}}]})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: Client())
    assert OpenAILLMProvider("key", "model").generate("s", "u").text == "answer"


def test_ollama_request_parsing(monkeypatch):
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            return httpx.Response(200, request=httpx.Request("POST", "http://test"), json={"message": {"content": "answer"}})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: Client())
    assert OllamaLLMProvider("http://localhost:11434", "model").generate("s", "u").text == "answer"


def test_mock_stream_yields_grounded_answer():
    chunks = list(__import__('app.services.llm.providers', fromlist=['MockLLMProvider']).MockLLMProvider().stream(
        "s", "RETRIEVED CONTEXT:\n[S1] app/a.py:1-2\nhello"
    ))
    assert chunks and "hello" in chunks[0]


def test_openai_stream_parses_sse_while_context_is_open(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" world"}}]}'
            yield 'data: [DONE]'
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args, **kwargs): return Response()
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: Client())
    assert ''.join(OpenAILLMProvider("key", "model").stream("s", "u")) == "hello world"
