"""
Unified Tree-sitter chunker — single file replacing function_chunker, class_chunker,
semantic_chunker, and fixed_chunker.

Tree-sitter builds a real Concrete Syntax Tree (CST) for each supported language,
giving us precise node types, exact line/column positions, and correct handling of
nested scopes — without regex heuristics.

Supported strategies  (strategy= at construction time)
  "comprehensive" - DEFAULT. One pass extracts every chunk type:
                    imports block · each function/method · each class ·
                    individual top-level declarations (constants, assignments).
                    Classes are also decomposed into their individual methods so
                    the LLM sees both the class overview and each method in detail.
  "function"      - every function / method in the file, including nested ones
  "class"         - top-level class / struct / trait / interface / enum definitions
  "semantic"      - imports block → top-level definitions → remaining top-level statements
  "fixed"         - fixed-window sliding (does not use the CST; pure line splitting)

Graceful fallback: if the grammar package for a language is not installed,
every strategy except "fixed" falls back to fixed-window chunking so the
pipeline never breaks.

Install all grammars at once:
    pip install tree-sitter>=0.22.0 \
        tree-sitter-python tree-sitter-javascript tree-sitter-typescript \
        tree-sitter-java tree-sitter-go tree-sitter-ruby tree-sitter-c-sharp \
        tree-sitter-cpp tree-sitter-c tree-sitter-rust tree-sitter-bash
"""

from __future__ import annotations

import importlib
import logging
from typing import Dict, List, Optional, Set, Tuple

from chunking.base import BaseChunker, CodeChunk

logger = logging.getLogger(__name__)

# ── Grammar loader ─────────────────────────────────────────────────────────────
#
# Each entry: language_slug → (pip_module_name, callable_attr_or_None)
# If callable_attr is None, we call module.language().
# Tree-sitter 0.22+ Language() takes the PyCapsule returned by that call.

_GRAMMAR_MAP: Dict[str, Tuple[str, Optional[str]]] = {
    "python":     ("tree_sitter_python",     None),
    "javascript": ("tree_sitter_javascript", None),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx":        ("tree_sitter_typescript", "language_tsx"),
    "java":       ("tree_sitter_java",       None),
    "go":         ("tree_sitter_go",         None),
    "ruby":       ("tree_sitter_ruby",       None),
    "csharp":     ("tree_sitter_c_sharp",    None),
    "cpp":        ("tree_sitter_cpp",        None),
    "c":          ("tree_sitter_c",          None),
    "rust":       ("tree_sitter_rust",       None),
    "bash":       ("tree_sitter_bash",       None),
}

# Module-level parser cache: language slug → Parser instance (or None when unavailable)
_PARSER_CACHE: Dict[str, object] = {}


def _get_parser(language: str):
    """
    Return a ready-to-use tree-sitter Parser for the given language slug,
    or None if the grammar package is not installed.
    Results are cached after the first successful load.
    """
    if language in _PARSER_CACHE:
        return _PARSER_CACHE[language]

    parser = None
    entry = _GRAMMAR_MAP.get(language)
    if entry:
        mod_name, attr = entry
        try:
            from tree_sitter import Language, Parser
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, attr) if attr else mod.language
            lang_obj = Language(fn())
            parser = Parser(lang_obj)
        except Exception as exc:
            logger.debug("tree-sitter grammar unavailable for %s: %s", language, exc)

    _PARSER_CACHE[language] = parser
    return parser


# ── Node-type tables ───────────────────────────────────────────────────────────
#
# These sets define which CST node types correspond to each concept per language.
# Extending support for a new language = add one entry per table.

FUNCTION_TYPES: Dict[str, Set[str]] = {
    "python": {
        "function_definition",
        "async_function_definition",
    },
    "javascript": {
        "function_declaration",
        "generator_function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    },
    "typescript": {
        "function_declaration",
        "generator_function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
        "method_signature",
        "abstract_method_signature",
        "function_signature",
    },
    "tsx": {
        "function_declaration",
        "generator_function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
    },
    "java": {
        "method_declaration",
        "constructor_declaration",
    },
    "go": {
        "function_declaration",
        "method_declaration",
    },
    "ruby": {
        "method",
        "singleton_method",
    },
    "csharp": {
        "method_declaration",
        "constructor_declaration",
        "local_function_statement",
        "operator_declaration",
        "conversion_operator_declaration",
    },
    "cpp": {
        "function_definition",
    },
    "c": {
        "function_definition",
    },
    "rust": {
        "function_item",
    },
    "bash": {
        "function_definition",
    },
}

CLASS_TYPES: Dict[str, Set[str]] = {
    "python": {
        "class_definition",
    },
    "javascript": {
        "class_declaration",
        "class_expression",
    },
    "typescript": {
        "class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
    },
    "tsx": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
    },
    "java": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "annotation_type_declaration",
        "record_declaration",
    },
    "go": {
        "type_declaration",
    },
    "ruby": {
        "class",
        "module",
    },
    "csharp": {
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "enum_declaration",
        "record_declaration",
    },
    "cpp": {
        "class_specifier",
        "struct_specifier",
        "enum_specifier",
    },
    "c": {
        "struct_specifier",
        "enum_specifier",
    },
    "rust": {
        "struct_item",
        "enum_item",
        "impl_item",
        "trait_item",
        "union_item",
    },
    "bash": set(),
}

IMPORT_TYPES: Dict[str, Set[str]] = {
    "python": {
        "import_statement",
        "import_from_statement",
    },
    "javascript": {
        "import_statement",
    },
    "typescript": {
        "import_statement",
    },
    "tsx": {
        "import_statement",
    },
    "java": {
        "import_declaration",
        "package_declaration",
    },
    "go": {
        "import_declaration",
        "package_clause",  # package main / package foo
    },
    "ruby": set(),  # require() is a call_expression; skip rather than false-positive
    "csharp": {
        "using_directive",
    },
    "cpp": {
        "preproc_include",
        "preproc_def",
    },
    "c": {
        "preproc_include",
        "preproc_def",
    },
    "rust": {
        "use_declaration",
        "extern_crate_declaration",
    },
    "bash": {
        "source_command",
    },
}

# Namespace / module wrapper types that are transparent containers — their
# children should be treated as if they were top-level.  Used in the
# comprehensive strategy so C# classes inside `namespace Foo { }` and
# Java classes inside a top-level block are still found.
_TRANSPARENT_WRAPPERS: Set[str] = {
    "namespace_declaration",     # C#
    "namespace_definition",      # C++
    "declaration_list",          # C# body of namespace
    "module",                    # Ruby (treated separately via CLASS_TYPES)
}

# Parent node types where an arrow_function / function_expression is considered
# "named" (i.e. assigned to a variable or exported). Anonymous lambdas passed
# as arguments (items.map(x => x), Promise.then(...)) are excluded.
_NAMED_ANON_PARENTS: Set[str] = {
    "variable_declarator",
    "assignment_expression",
    "pair",                    # { key: function() {} }  in object literals
    "export_statement",
    "field_definition",        # class fields: foo = () => {}
    "public_field_definition",
}

# Node types that carry no semantic weight and should be skipped when
# grouping "other" top-level statements in semantic chunking.
_NOISE_TYPES: Set[str] = {
    "comment", "block_comment", "line_comment",
    "newline", "empty_statement",
}

# Top-level declaration node types (constants, variable assignments, type aliases).
# Used exclusively by the comprehensive strategy to produce individual declaration chunks.
DECLARATION_TYPES: Dict[str, Set[str]] = {
    "python": {
        "expression_statement",   # x = 5  (child must be assignment; checked at runtime)
        "annotated_assignment",   # x: int = 5
    },
    "javascript": {
        "lexical_declaration",    # const / let
        "variable_declaration",   # var
    },
    "typescript": {
        "lexical_declaration",
        "variable_declaration",
    },
    "tsx": {
        "lexical_declaration",
        "variable_declaration",
    },
    "java": {
        "field_declaration",
        "local_variable_declaration",
    },
    "go": {
        "var_declaration",
        "const_declaration",
    },
    "ruby": {
        "assignment",
        "operator_assignment",
    },
    "csharp": {
        "field_declaration",
        "property_declaration",
    },
    "cpp": {
        "declaration",
    },
    "c": {
        "declaration",
    },
    "rust": {
        "static_item",
        "const_item",
    },
    "bash": {
        "variable_assignment",
    },
}


# ── Name extraction ────────────────────────────────────────────────────────────

def _extract_name(node, parent, src: bytes) -> str:
    """
    Return a human-readable name for a syntax node.

    Most grammars expose a "name" field pointing to an identifier child.
    For anonymous constructs (arrow functions, function expressions) we
    look at the parent variable declarator to get the assigned variable name.
    For wrapper nodes (Go type_declaration, Rust impl_item) we descend one
    level to find the name field on the inner spec node.
    Falls back to a "<type@line>" label so chunk_id is always unique.
    """
    # Standard "name" field (Python, Java, Rust fn/struct/enum, …)
    name_node = node.child_by_field_name("name")
    if name_node:
        return src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")

    # Wrapper nodes: Go type_declaration → type_spec, Rust impl_item → type field
    for child in node.children:
        deep = child.child_by_field_name("name") or child.child_by_field_name("type")
        if deep and deep.type in {
            "type_identifier", "identifier", "scoped_type_identifier",
        }:
            return src[deep.start_byte:deep.end_byte].decode("utf-8", errors="replace")

    # JS/TS: const foo = () => {} — name lives in the parent variable_declarator
    if parent is not None:
        if parent.type == "variable_declarator":
            pname = parent.child_by_field_name("name")
            if pname:
                return src[pname.start_byte:pname.end_byte].decode("utf-8", errors="replace")
        # obj.method = function() {}  or  { key: function() {} }
        if parent.type in {"assignment_expression", "pair"}:
            left = parent.child_by_field_name("left") or parent.child_by_field_name("key")
            if left:
                return src[left.start_byte:left.end_byte].decode("utf-8", errors="replace")

    # C / C++: function_definition uses a chain of 'declarator' fields.
    # Walk: function_definition → declarator(function_declarator) → declarator(identifier)
    # Also handles pointer_declarator and qualified_identifier (namespaced methods).
    decl = node.child_by_field_name("declarator")
    if decl:
        curr = decl
        for _ in range(5):  # guard against pathological nesting
            if curr.type in {
                "identifier", "field_identifier", "destructor_name",
                "operator_name", "qualified_identifier",
            }:
                return src[curr.start_byte:curr.end_byte].decode("utf-8", errors="replace")
            inner = curr.child_by_field_name("declarator")
            if inner is None:
                for child in curr.children:
                    if child.type in {"identifier", "field_identifier"}:
                        return src[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                break
            curr = inner

    # Walk direct children for common identifier types
    for child in node.children:
        if child.type in {
            "identifier", "property_identifier", "private_property_identifier",
            "type_identifier", "field_identifier", "namespace_identifier",
        }:
            return src[child.start_byte:child.end_byte].decode("utf-8", errors="replace")

    return f"<{node.type}@{node.start_point[0] + 1}>"


# ── Tree traversal ─────────────────────────────────────────────────────────────

# Anonymous function types that are only meaningful when assigned to a name.
_ANON_FN_TYPES: Set[str] = {"arrow_function", "function_expression"}


def _collect_recursive(node, target_types: Set[str], src: bytes, _parent=None) -> List[Tuple]:
    """
    DFS over the CST, collecting every node whose type is in target_types.
    Returns list of (node, name) in document order (pre-order DFS = source order).
    Recurses INTO matching nodes so nested definitions are included.

    Anonymous arrow functions / function expressions are skipped unless their
    immediate parent is a named assignment context (variable_declarator, etc.).
    """
    results = []
    if node.type in target_types:
        if node.type in _ANON_FN_TYPES:
            # Only keep if the parent gives this function a name
            if _parent is not None and _parent.type in _NAMED_ANON_PARENTS:
                results.append((node, _extract_name(node, _parent, src)))
            # Always recurse so we don't miss named functions inside callbacks
        else:
            results.append((node, _extract_name(node, _parent, src)))
    for child in node.children:
        results.extend(_collect_recursive(child, target_types, src, node))
    return results


# ── Comprehensive-strategy helpers ────────────────────────────────────────────

def _flatten_top_level(nodes) -> list:
    """
    Recursively expand transparent wrapper nodes (namespace_declaration,
    declaration_list, etc.) so that C# / C++ namespace-scoped declarations
    are treated as if they lived at the top level of the file.
    """
    result = []
    for node in nodes:
        if node.type in _TRANSPARENT_WRAPPERS:
            result.extend(_flatten_top_level(node.children))
        elif node.type not in _NOISE_TYPES:
            result.append(node)
    return result


def _unwrap_export(node):
    """
    For JS/TS export_statement nodes, return the inner exported declaration.
    Allows the comprehensive strategy to route 'export const X = ...' as a
    declaration and 'export function foo()' as a function without special-casing
    export_statement in every type table.
    """
    if node.type != "export_statement":
        return node
    for child in node.children:
        if child.is_named and child.type not in {
            "default", "from_clause", "export_clause", "string", "identifier",
            "namespace_import",
        }:
            return child
    return node


def _declaration_name(node, src: bytes) -> str:
    """
    Extract the primary variable / constant name from a top-level declaration node.
    Handles the varied structures across Python, JS/TS, Go, Rust, C/C++ etc.
    """
    # Python expression_statement wraps the actual assignment — unwrap first
    actual = node
    if node.type == "expression_statement":
        for child in node.children:
            if child.type in {"assignment", "augmented_assignment", "annotated_assignment"}:
                actual = child
                break

    # Direct left / name field  (Python assignment, Rust const/static, …)
    for field in ("left", "name"):
        fnode = actual.child_by_field_name(field)
        if fnode:
            return src[fnode.start_byte:fnode.end_byte].decode("utf-8", errors="replace").strip()

    # JS/TS lexical_declaration → variable_declarator → name
    # Go const_declaration / var_declaration → const_spec / var_spec → name
    for child in actual.children:
        if child.type in {
            "variable_declarator", "const_spec", "var_spec", "init_declarator",
        }:
            nnode = child.child_by_field_name("name")
            if nnode:
                return src[nnode.start_byte:nnode.end_byte].decode("utf-8", errors="replace")

    # C / C++ nested declarators
    for child in actual.children:
        if child.type in {"init_declarator", "declarator", "pointer_declarator"}:
            for gc in child.children:
                if gc.type == "identifier":
                    return src[gc.start_byte:gc.end_byte].decode("utf-8", errors="replace")

    # Walk direct children for any identifier
    for child in actual.children:
        if child.type == "identifier":
            return src[child.start_byte:child.end_byte].decode("utf-8", errors="replace")

    return f"<decl@{node.start_point[0] + 1}>"


def _is_function_declaration(node, fn_types: Set[str]) -> bool:
    """
    Return True when a lexical/variable declaration is actually assigning a
    function to a variable (e.g. const foo = () => {}).  These are already
    captured by the function pass so the declaration pass should skip them.
    """
    for child in node.children:
        if child.type in {"variable_declarator", "const_spec", "var_spec"}:
            val = child.child_by_field_name("value")
            if val and val.type in fn_types:
                return True
    return False


# ── Chunker ────────────────────────────────────────────────────────────────────

class TreeSitterChunker(BaseChunker):
    """
    Single chunker class supporting all four strategies via tree-sitter CST parsing.
    Instantiate with the desired strategy; the registry in __init__.py handles this.
    """

    def __init__(self, strategy: str = "semantic") -> None:
        self.strategy = strategy
        self.strategy_id = strategy  # keeps parity with the per-class pattern

    # ── Public entry point ────────────────────────────────────────────────────

    def chunk(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        # Fixed strategy never needs a parser
        if self.strategy == "fixed":
            return self._fixed_window(source, language, file_name)

        parser = _get_parser(language)
        if parser is None:
            logger.debug(
                "No tree-sitter grammar for '%s'; falling back to fixed window", language
            )
            return self._fixed_window(source, language, file_name)

        src_bytes = source.encode("utf-8", errors="replace")
        tree = parser.parse(src_bytes)
        root = tree.root_node
        lines = source.splitlines()

        if self.strategy == "comprehensive":
            chunks = self._chunk_comprehensive(root, src_bytes, lines, language, file_name)
        elif self.strategy == "function":
            chunks = self._chunk_functions(root, src_bytes, lines, language, file_name)
        elif self.strategy == "class":
            chunks = self._chunk_classes(root, src_bytes, lines, language, file_name)
        else:  # "semantic"
            chunks = self._chunk_semantic(root, src_bytes, lines, language, file_name)

        return chunks or self._module_fallback(source, language, file_name)

    # ── Strategy implementations ──────────────────────────────────────────────

    def _chunk_functions(
        self,
        root,
        src_bytes: bytes,
        lines: List[str],
        language: str,
        file_name: str,
    ) -> List[CodeChunk]:
        fn_types = FUNCTION_TYPES.get(language, set())
        if not fn_types:
            return []

        chunks = []
        for node, name in _collect_recursive(root, fn_types, src_bytes):
            chunks.append(
                self._make_chunk(
                    node, name, "function", src_bytes, lines, language, file_name,
                    metadata={"parser": "tree-sitter"},
                )
            )
        return chunks

    def _chunk_classes(
        self,
        root,
        src_bytes: bytes,
        lines: List[str],
        language: str,
        file_name: str,
    ) -> List[CodeChunk]:
        cls_types = CLASS_TYPES.get(language, set())
        if not cls_types:
            return []

        # Top-level only: direct children of the root node.
        # This matches the existing ClassChunker behaviour and avoids duplicating
        # inner classes that appear inside outer class chunks.
        chunks = []
        for child in root.children:
            if child.type in cls_types:
                name = _extract_name(child, root, src_bytes)
                chunks.append(
                    self._make_chunk(
                        child, name, "class", src_bytes, lines, language, file_name,
                        metadata={"parser": "tree-sitter"},
                    )
                )
        return chunks

    def _chunk_semantic(
        self,
        root,
        src_bytes: bytes,
        lines: List[str],
        language: str,
        file_name: str,
    ) -> List[CodeChunk]:
        fn_types  = FUNCTION_TYPES.get(language, set())
        cls_types = CLASS_TYPES.get(language, set())
        imp_types = IMPORT_TYPES.get(language, set())

        import_nodes: List = []
        def_nodes:    List[Tuple] = []  # (node, name)
        other_nodes:  List = []

        for child in root.children:
            if child.type in _NOISE_TYPES:
                continue
            if child.type in imp_types:
                import_nodes.append(child)
            elif child.type in fn_types or child.type in cls_types:
                def_nodes.append((child, _extract_name(child, root, src_bytes)))
            else:
                other_nodes.append(child)

        chunks: List[CodeChunk] = []

        # All imports → one combined chunk
        if import_nodes:
            start = import_nodes[0].start_point[0] + 1
            end   = import_nodes[-1].end_point[0] + 1
            chunks.append(CodeChunk(
                chunk_id   = f"{file_name}::imports#{start}",
                chunk_type = "semantic",
                name       = "imports",
                start_line = start,
                end_line   = end,
                code       = "\n".join(lines[start - 1 : end]),
                language   = language,
                metadata   = {"group": "imports", "parser": "tree-sitter"},
            ))

        # Each function / class → individual chunk
        for node, name in def_nodes:
            chunks.append(
                self._make_chunk(
                    node, name, "semantic", src_bytes, lines, language, file_name,
                    metadata={"group": "definition", "parser": "tree-sitter"},
                )
            )

        # Remaining top-level statements → one combined chunk
        if other_nodes:
            start = other_nodes[0].start_point[0] + 1
            end   = other_nodes[-1].end_point[0] + 1
            chunks.append(CodeChunk(
                chunk_id   = f"{file_name}::top_level#{start}",
                chunk_type = "semantic",
                name       = "top_level",
                start_line = start,
                end_line   = end,
                code       = "\n".join(lines[start - 1 : end]),
                language   = language,
                metadata   = {"group": "top_level", "parser": "tree-sitter"},
            ))

        return sorted(chunks, key=lambda c: c.start_line)

    def _chunk_comprehensive(
        self,
        root,
        src_bytes: bytes,
        lines: List[str],
        language: str,
        file_name: str,
    ) -> List[CodeChunk]:
        """
        Single-pass comprehensive extraction — produces every meaningful chunk type:

          imports     - all import / use / #include statements grouped into one chunk
          function    - every named function and method (recursive; includes nested)
          class       - each top-level class / struct / trait / interface
          method      - each method inside a class (also reviewed individually)
          declaration - each top-level constant / variable assignment

        Classes are intentionally yielded as both a full "class" chunk (for
        structural context) AND decomposed into individual "method" chunks (for
        detailed logic review).  Arrow functions / lambdas assigned to a named
        variable are treated as functions.  Truly anonymous callbacks are skipped.
        """
        fn_types   = FUNCTION_TYPES.get(language, set())
        cls_types  = CLASS_TYPES.get(language, set())
        imp_types  = IMPORT_TYPES.get(language, set())
        decl_types = DECLARATION_TYPES.get(language, set())

        chunks: List[CodeChunk] = []
        import_nodes: List = []

        # Flatten top-level: transparently unwrap namespace / module containers
        # so C# classes inside `namespace Foo {}` appear as top-level items.
        top_level = _flatten_top_level(root.children)

        # Pre-scan: record byte ranges of all methods that live inside a class.
        # Pass 1 will skip these so each method is reviewed exactly once —
        # either as a standalone function or as ClassName.method (in a class).
        method_byte_ranges: Set[Tuple[int, int]] = set()
        for child in top_level:
            inner_pre = _unwrap_export(child)
            if inner_pre.type in cls_types:
                for mnode, _ in _collect_recursive(inner_pre, fn_types, src_bytes, inner_pre):
                    method_byte_ranges.add((mnode.start_byte, mnode.end_byte))

        # ── Pass 1: standalone functions (skip class-body methods) ───────────
        for node, name in _collect_recursive(root, fn_types, src_bytes):
            if (node.start_byte, node.end_byte) in method_byte_ranges:
                continue
            chunks.append(self._make_chunk(
                node, name, "function", src_bytes, lines, language, file_name,
                metadata={"parser": "tree-sitter", "group": "function"},
            ))

        # ── Pass 2 + 3 + 4: flattened top-level walk ──────────────────────────
        for child in top_level:
            # Unwrap JS/TS export_statement to see what's inside
            inner = _unwrap_export(child)

            # Pass 2: imports
            if inner.type in imp_types or child.type in imp_types:
                import_nodes.append(child)
                continue

            # Pass 3: classes — full class chunk + individual method chunks
            if inner.type in cls_types:
                cls_name = _extract_name(inner, child, src_bytes)
                chunks.append(self._make_chunk(
                    child, cls_name, "class", src_bytes, lines, language, file_name,
                    metadata={"parser": "tree-sitter", "group": "class"},
                ))
                for mnode, mname in _collect_recursive(inner, fn_types, src_bytes, inner):
                    chunks.append(self._make_chunk(
                        mnode, f"{cls_name}.{mname}", "function", src_bytes, lines, language, file_name,
                        metadata={"parser": "tree-sitter", "group": "method", "class": cls_name},
                    ))
                continue

            # Pass 4: declarations (skip function assignments — already in Pass 1)
            if inner.type in decl_types:
                # Python: expression_statement must wrap an assignment, not a bare call
                if inner.type == "expression_statement":
                    has_assign = any(
                        c.type in {"assignment", "augmented_assignment", "annotated_assignment"}
                        for c in inner.children
                    )
                    if not has_assign:
                        continue
                # JS/TS: skip `const foo = () => {}` — captured as function in Pass 1
                if _is_function_declaration(inner, fn_types):
                    continue
                name = _declaration_name(inner, src_bytes)
                chunks.append(self._make_chunk(
                    child, name, "declaration", src_bytes, lines, language, file_name,
                    metadata={"parser": "tree-sitter", "group": "declaration"},
                ))

        # ── Combine all import nodes into one block ────────────────────────────
        if import_nodes:
            start = import_nodes[0].start_point[0] + 1
            end   = import_nodes[-1].end_point[0] + 1
            chunks.append(CodeChunk(
                chunk_id   = f"{file_name}::imports#{start}",
                chunk_type = "imports",
                name       = "imports",
                start_line = start,
                end_line   = end,
                code       = "\n".join(lines[start - 1 : end]),
                language   = language,
                metadata   = {"parser": "tree-sitter", "group": "imports"},
            ))

        return sorted(chunks, key=lambda c: c.start_line)

    def _fixed_window(
        self,
        source: str,
        language: str,
        file_name: str,
        window: int = 40,
        overlap: int = 5,
    ) -> List[CodeChunk]:
        lines = source.splitlines() or [""]
        step  = window - overlap
        chunks: List[CodeChunk] = []
        block = 0
        i = 0

        while i < len(lines):
            start_line = i + 1
            end_line   = min(i + window, len(lines))
            chunks.append(CodeChunk(
                chunk_id   = f"{file_name}::block_{block}#{start_line}",
                chunk_type = "fixed",
                name       = f"block_{block}",
                start_line = start_line,
                end_line   = end_line,
                code       = "\n".join(lines[i:end_line]),
                language   = language,
                metadata   = {"window": window, "overlap": overlap},
            ))
            block += 1
            i += step

        return chunks or [CodeChunk(
            chunk_id   = f"{file_name}::block_0#1",
            chunk_type = "fixed",
            name       = "block_0",
            start_line = 1,
            end_line   = 1,
            code       = source,
            language   = language,
            metadata   = {"window": window, "overlap": overlap},
        )]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_chunk(
        self,
        node,
        name: str,
        chunk_type: str,
        src_bytes: bytes,
        lines: List[str],
        language: str,
        file_name: str,
        metadata: Optional[dict] = None,
    ) -> CodeChunk:
        start_line = node.start_point[0] + 1  # tree-sitter rows are 0-indexed
        end_line   = node.end_point[0] + 1
        return CodeChunk(
            chunk_id   = f"{file_name}::{name}#{start_line}",
            chunk_type = chunk_type,
            name       = name,
            start_line = start_line,
            end_line   = end_line,
            code       = "\n".join(lines[start_line - 1 : end_line]),
            language   = language,
            metadata   = metadata or {"parser": "tree-sitter"},
        )

    def _module_fallback(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        """Return the whole file as a single chunk when no structure was found.
        Returns an empty list for empty/whitespace-only files — nothing to review."""
        if not source or not source.strip():
            return []
        lines = source.splitlines()
        return [CodeChunk(
            chunk_id   = f"{file_name}::module",
            chunk_type = self.strategy,
            name       = "<module>",
            start_line = 1,
            end_line   = max(1, len(lines)),
            code       = source,
            language   = language,
            metadata   = {"fallback": True, "parser": "tree-sitter"},
        )]
