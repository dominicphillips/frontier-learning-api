"""A minimal, bounded DOM built on the standard library HTML parser."""

from __future__ import annotations

from collections.abc import Iterator
from html.parser import HTMLParser

VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
HIDDEN = frozenset({"script", "style", "template", "svg", "noscript", "head"})
MAX_NODES = 250_000


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: Node | None):
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []
        self.parent = parent

    def __repr__(self) -> str:
        return f"Node({self.tag!r}, {self.attrs!r})"

    @property
    def elements(self) -> list[Node]:
        return [c for c in self.children if isinstance(c, Node)]

    def iter(self) -> Iterator[Node]:
        stack = list(reversed(self.elements))
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.elements))

    def find_all(self, tag: str | None = None, **attrs: str) -> list[Node]:
        return [
            n
            for n in self.iter()
            if (tag is None or n.tag == tag)
            and all(n.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items())
        ]

    def find(self, tag: str | None = None, **attrs: str) -> Node | None:
        found = self.find_all(tag, **attrs)
        return found[0] if found else None

    def raw_text(self) -> str:
        return "".join(c if isinstance(c, str) else c.raw_text() for c in self.children)

    def text(self) -> str:
        """Visible text with collapsed whitespace; scripts, styles and icons are skipped."""
        parts: list[str] = []

        def walk(node: Node) -> None:
            for child in node.children:
                if isinstance(child, str):
                    parts.append(child)
                elif child.tag not in HIDDEN:
                    walk(child)

        walk(self)
        return " ".join("".join(parts).split())

    def next_element(self) -> Node | None:
        if self.parent is None:
            return None
        siblings = self.parent.elements
        index = next(i for i, n in enumerate(siblings) if n is self)
        return siblings[index + 1] if index + 1 < len(siblings) else None

    def previous_element(self) -> Node | None:
        if self.parent is None:
            return None
        siblings = self.parent.elements
        index = next(i for i, n in enumerate(siblings) if n is self)
        return siblings[index - 1] if index > 0 else None


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", {}, None)
        self.stack = [self.root]
        self.count = 0

    def _add(self, tag: str, attrs: list[tuple[str, str | None]]) -> Node:
        self.count += 1
        if self.count > MAX_NODES:
            raise ValueError("HTML document has too many elements")
        parent = self.stack[-1]
        node = Node(tag, {k: v or "" for k, v in attrs}, parent)
        parent.children.append(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._add(tag, attrs)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._add(tag, attrs)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(text: str) -> Node:
    builder = _Builder()
    builder.feed(text)
    builder.close()
    return builder.root
