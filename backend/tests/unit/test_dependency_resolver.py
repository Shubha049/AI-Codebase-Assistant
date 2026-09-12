from app.services.dependency_graph.resolver import ImportToResolve, build_dependency_graph

KNOWN = {
    "app/main.py", "app/config.py", "app/services/foo.py",
    "app/services/bar/__init__.py", "app/services/bar/helper.py",
    "frontend/src/App.tsx", "frontend/src/utils.ts",
    "frontend/src/components/Button.tsx", "frontend/src/components/index.ts",
}


def test_python_dotted_module_resolves_to_file():
    edges = build_dependency_graph(
        [ImportToResolve("app/main.py", "Python", "app.config")], KNOWN
    )
    assert edges[0].target_file == "app/config.py"


def test_python_package_resolves_to_init_file():
    edges = build_dependency_graph(
        [ImportToResolve("app/main.py", "Python", "app.services.bar")], KNOWN
    )
    assert edges[0].target_file == "app/services/bar/__init__.py"


def test_python_stdlib_and_third_party_are_not_resolved():
    edges = build_dependency_graph(
        [
            ImportToResolve("app/main.py", "Python", "os"),
            ImportToResolve("app/main.py", "Python", "fastapi"),
        ],
        KNOWN,
    )
    assert edges == []


def test_ts_relative_import_resolves_with_extension_added():
    edges = build_dependency_graph(
        [ImportToResolve("frontend/src/App.tsx", "TypeScript", "./utils")], KNOWN
    )
    assert edges[0].target_file == "frontend/src/utils.ts"


def test_ts_relative_import_to_directory_resolves_to_index():
    edges = build_dependency_graph(
        [ImportToResolve("frontend/src/App.tsx", "TypeScript", "./components")], KNOWN
    )
    assert edges[0].target_file == "frontend/src/components/index.ts"


def test_ts_parent_directory_traversal_resolves_correctly():
    """Regression test: PurePosixPath's own str() does NOT collapse '..'
    segments (unlike posixpath.normpath) — this silently failed to
    resolve any '../' import until fixed. Verified via direct comparison
    of the two, not assumed."""
    edges = build_dependency_graph(
        [ImportToResolve("frontend/src/components/Button.tsx", "TypeScript", "../utils")],
        KNOWN,
    )
    assert len(edges) == 1
    assert edges[0].target_file == "frontend/src/utils.ts"


def test_ts_bare_specifier_is_external_not_resolved():
    edges = build_dependency_graph(
        [ImportToResolve("frontend/src/App.tsx", "TypeScript", "react")], KNOWN
    )
    assert edges == []


def test_unresolvable_relative_import_is_silently_skipped_not_an_error():
    edges = build_dependency_graph(
        [ImportToResolve("frontend/src/App.tsx", "TypeScript", "./does_not_exist")],
        KNOWN,
    )
    assert edges == []


def test_duplicate_edges_are_deduplicated():
    edges = build_dependency_graph(
        [
            ImportToResolve("app/main.py", "Python", "app.config"),
            ImportToResolve("app/main.py", "Python", "app.config"),
        ],
        KNOWN,
    )
    assert len(edges) == 1
