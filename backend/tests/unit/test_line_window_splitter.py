from app.services.chunking.line_window_splitter import split_lines_into_windows


def test_small_content_produces_single_window():
    lines = ["def foo():", "    return 1"]
    chunks = split_lines_into_windows(lines, 1, max_tokens=400, overlap_ratio=0.15, chunk_type="file_window")
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2


def test_empty_input_produces_no_chunks():
    assert split_lines_into_windows([], 1, 400, 0.15, "file_window") == []


def test_oversized_single_line_becomes_its_own_chunk_not_dropped():
    lines = ["x = " + "a" * 500]
    chunks = split_lines_into_windows(lines, 5, max_tokens=10, overlap_ratio=0.15, chunk_type="function_window")
    assert len(chunks) == 1
    assert chunks[0].start_line == 5
    assert chunks[0].end_line == 5
    assert chunks[0].token_count > 10  # over budget, but present — not silently dropped


def test_start_line_offset_is_respected():
    lines = ["a", "b", "c"]
    chunks = split_lines_into_windows(lines, 100, max_tokens=400, overlap_ratio=0.15, chunk_type="file_window")
    assert chunks[0].start_line == 100
    assert chunks[0].end_line == 102


def test_small_windows_do_not_produce_pathological_overlap():
    """Regression test: a naive 'minimum 1 line of overlap' floor caused
    50% effective overlap on small windows, producing 15 near-duplicate
    windows for 20 short lines instead of a reasonable ~9. Verified via
    direct run before fixing, not assumed."""
    lines = [f"line number {i}" for i in range(1, 21)]
    chunks = split_lines_into_windows(lines, 1, max_tokens=10, overlap_ratio=0.2, chunk_type="file_window")
    assert len(chunks) <= 10


def test_large_input_gives_full_line_coverage_no_gaps():
    lines = [f"def func_{i}(): pass" for i in range(1, 101)]
    chunks = split_lines_into_windows(lines, 1, max_tokens=100, overlap_ratio=0.15, chunk_type="file_window")
    covered = set()
    for c in chunks:
        covered.update(range(c.start_line, c.end_line + 1))
    assert covered == set(range(1, 101))


def test_windows_actually_overlap_when_ratio_and_size_allow_it():
    lines = [f"def func_{i}(): pass" for i in range(1, 101)]
    chunks = split_lines_into_windows(lines, 1, max_tokens=100, overlap_ratio=0.15, chunk_type="file_window")
    assert len(chunks) >= 2
    # Second window's start must be <= first window's end (real overlap),
    # not simply adjacent.
    assert chunks[1].start_line <= chunks[0].end_line


def test_symbol_name_and_parent_are_carried_through():
    lines = ["a", "b"]
    chunks = split_lines_into_windows(
        lines, 1, 400, 0.15, "method_window", symbol_name="run", parent_symbol_name="App"
    )
    assert chunks[0].symbol_name == "run"
    assert chunks[0].parent_symbol_name == "App"
