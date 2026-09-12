from __future__ import annotations

from tree_sitter import Node

from app.services.parsing.models import ExtractedImport, ExtractedSymbol


def _docstring_of(body_node: Node | None) -> str | None:
    """
    Docstring = the block's first statement being a bare string literal.
    Handles both tree-sitter-python grammar variants seen in the wild:
    some wrap it in `expression_statement -> string`, this pack's grammar
    puts `string` directly as the block's first child.
    """
    if body_node is None or body_node.child_count == 0:
        return None
    first = body_node.children[0]
    if first.type == "expression_statement":
        if first.child_count == 0 or first.children[0].type != "string":
            return None
        string_node = first.children[0]
    elif first.type == "string":
        string_node = first
    else:
        return None

    content_parts = [
        c.text.decode("utf-8", errors="replace")
        for c in string_node.children
        if c.type == "string_content"
    ]
    if content_parts:
        return "".join(content_parts).strip() or None
    # Fallback for grammar variants without a string_content child.
    return string_node.text.decode("utf-8", errors="replace").strip("\"'").strip() or None


def extract_python(root: Node) -> tuple[list[ExtractedSymbol], list[ExtractedImport]]:
    symbols: list[ExtractedSymbol] = []
    imports: list[ExtractedImport] = []

    def walk(node: Node, parent_class: str | None) -> None:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            body_node = node.child_by_field_name("body")
            name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
            symbols.append(ExtractedSymbol(
                symbol_type="class",
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                docstring=_docstring_of(body_node),
            ))
            for child in node.children:
                walk(child, parent_class=name)
            return

        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            body_node = node.child_by_field_name("body")
            name = name_node.text.decode("utf-8") if name_node else "<anonymous>"
            symbols.append(ExtractedSymbol(
                symbol_type="method" if parent_class else "function",
                name=name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent_name=parent_class,
                docstring=_docstring_of(body_node),
            ))
            # Deliberately not recursing into a function body: nested
            # function/class definitions are real but out of scope for
            # this phase's symbol table (documented as a known limitation).
            return

        if node.type == "import_statement":
            # `import a.b.c` / `import a.b.c as d`
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(ExtractedImport(
                        module=child.text.decode("utf-8"),
                        line_number=node.start_point[0] + 1,
                    ))
                elif child.type == "aliased_import":
                    dotted = child.child_by_field_name("name")
                    if dotted:
                        imports.append(ExtractedImport(
                            module=dotted.text.decode("utf-8"),
                            line_number=node.start_point[0] + 1,
                        ))
            return

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module = module_node.text.decode("utf-8") if module_node else ""
            names: list[str] = []
            for child in node.children:
                if child.type == "dotted_name" and child != module_node:
                    names.append(child.text.decode("utf-8"))
                elif child.type == "aliased_import":
                    name_field = child.child_by_field_name("name")
                    if name_field:
                        names.append(name_field.text.decode("utf-8"))
                elif child.type == "wildcard_import":
                    names.append("*")
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
