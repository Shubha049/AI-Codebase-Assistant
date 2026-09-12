from __future__ import annotations

from tree_sitter import Node

from app.services.parsing.models import ExtractedImport, ExtractedSymbol


def _string_content(node: Node | None) -> str:
    if node is None:
        return ""
    for child in node.children:
        if child.type == "string_fragment":
            return child.text.decode("utf-8")
    # Fallback: strip quotes manually.
    return node.text.decode("utf-8").strip("'\"")


def extract_js_ts(root: Node) -> tuple[list[ExtractedSymbol], list[ExtractedImport]]:
    symbols: list[ExtractedSymbol] = []
    imports: list[ExtractedImport] = []

    def walk(node: Node, parent_class: str | None) -> None:
        if node.type in ("class_declaration", "abstract_class_declaration"):
            # NOTE: only "class_declaration" / "abstract_class_declaration" — NOT the bare "class" node
            # type, which is just the `class` keyword TOKEN and a child of
            # class_declaration itself. Matching it too double-counted
            # every class as a second, nameless "<anonymous>" entry — a
            # tree-sitter node-type collision, found via direct parse-tree
            # inspection, not assumed.
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
            symbols.append(ExtractedSymbol(
                symbol_type="class",
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
            ))
            for child in node.children:
                walk(child, parent_class=name)
            return

        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
            symbols.append(ExtractedSymbol(
                symbol_type="method",
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent_name=parent_class,
            ))
            return  # don't recurse into method bodies for nested symbols (documented limitation)

        if node.type in ("function_declaration", "generator_function_declaration"):
            # Same keyword-token collision as class_declaration/"class"
            # above — "function" alone is just the keyword token.
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
            symbols.append(ExtractedSymbol(
                symbol_type="method" if parent_class else "function",
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent_name=parent_class,
            ))
            return

        if node.type in ("lexical_declaration", "variable_declaration"):
            for declarator in node.children:
                if declarator.type != "variable_declarator":
                    continue
                value = declarator.child_by_field_name("value")
                if value is not None and value.type in ("arrow_function", "function_expression", "function", "generator_function"):
                    name_node = declarator.child_by_field_name("name")
                    name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
                    symbols.append(ExtractedSymbol(
                        symbol_type="arrow_function" if value.type == "arrow_function" else ("method" if parent_class else "function"),
                        name=name,
                        start_line=declarator.start_point[0] + 1,
                        end_line=declarator.end_point[0] + 1,
                        parent_name=parent_class,
                    ))
            return

        if node.type == "import_statement":
            string_node = next((c for c in node.children if c.type == "string"), None)
            module = _string_content(string_node)
            names: list[str] = []
            clause = next((c for c in node.children if c.type == "import_clause"), None)
            if clause is not None:
                for part in clause.children:
                    if part.type == "identifier":
                        names.append(part.text.decode("utf-8"))  # default import
                    elif part.type == "namespace_import":
                        ident = next((c for c in part.children if c.type == "identifier"), None)
                        if ident:
                            names.append("* as " + ident.text.decode("utf-8"))
                    elif part.type == "named_imports":
                        for spec in part.children:
                            if spec.type == "import_specifier":
                                ident = next(
                                    (c for c in spec.children if c.type == "identifier"), None
                                )
                                if ident:
                                    names.append(ident.text.decode("utf-8"))
            imports.append(ExtractedImport(
                module=module,
                imported_names=names,
                line_number=node.start_point[0] + 1,
            ))
            return

        for child in node.children:
            walk(child, parent_class)

    walk(root, parent_class=None)
    return symbols, imports
