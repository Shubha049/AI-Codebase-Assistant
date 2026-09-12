from app.services.chunking.hashing import hash_bytes, hash_content
from app.services.chunking.token_estimator import estimate_tokens


def test_identical_content_produces_identical_hash():
    assert hash_content("def foo(): pass") == hash_content("def foo(): pass")


def test_different_content_produces_different_hash():
    assert hash_content("def foo(): pass") != hash_content("def bar(): pass")


def test_hash_is_sensitive_to_whitespace_not_normalized():
    """Deliberate design choice: two chunks are only duplicates if
    byte-for-byte identical — near-identical-but-reformatted code is NOT
    treated as a duplicate."""
    assert hash_content("def foo():\n    pass") != hash_content("def foo():\n pass")


def test_hash_bytes_matches_hash_content_for_utf8():
    text = "def foo(): pass"
    assert hash_bytes(text.encode("utf-8")) == hash_content(text)


def test_empty_string_produces_zero_tokens():
    assert estimate_tokens("") == 0


def test_short_string_produces_at_least_one_token():
    assert estimate_tokens("x") >= 1


def test_longer_text_produces_more_tokens():
    short = "a" * 10
    long = "a" * 1000
    assert estimate_tokens(long) > estimate_tokens(short)


def test_roughly_four_chars_per_token():
    text = "a" * 400
    assert 90 <= estimate_tokens(text) <= 110
