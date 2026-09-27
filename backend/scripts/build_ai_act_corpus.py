"""Build backend/data/ai_act_en.json from the official EUR-Lex text of the AI Act.

One-off dev tool (specs/007-ai-act-article-explanations): the backend only reads the
committed JSON, so no external site is needed at request time. Standard library only —
no HTML-parsing dependency added to the backend for a script run once.

    cd backend && .venv/bin/python scripts/build_ai_act_corpus.py [--html saved_page.html]

Source: Regulation (EU) 2024/1689, Official Journal English HTML on EUR-Lex. EU legal
texts may be reused with attribution (Commission Decision 2011/833/EU).
"""

import argparse
import json
import re
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

SOURCE_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "ai_act_en.json"

_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
_PARAGRAPH_ID_RE = re.compile(r"^\d{3}\.\d{3}$")
_CHAPTER_ID_RE = re.compile(r"^cpt_([IVXL]+)(?:\.sct_(\d+))?$")


class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict):
        self.tag = tag
        self.attrs = attrs
        self.children: list = []

    @property
    def id(self) -> str:
        return self.attrs.get("id") or ""

    def has_class(self, name: str) -> bool:
        return name in (self.attrs.get("class") or "").split()

    def elements(self) -> list["Node"]:
        return [child for child in self.children if isinstance(child, Node)]

    def descendants(self):
        for child in self.elements():
            yield child
            yield from child.descendants()


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self._stack = [self.root]
        self.by_id: dict[str, Node] = {}

    def _add(self, tag, attrs) -> Node:
        node = Node(tag, dict(attrs))
        self._stack[-1].children.append(node)
        if node.id:
            self.by_id[node.id] = node
        return node

    def handle_starttag(self, tag, attrs):
        node = self._add(tag, attrs)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._add(tag, attrs)

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data):
        self._stack[-1].children.append(data)


def text_of(node) -> str:
    if isinstance(node, str):
        return node
    raw = " ".join(text_of(child) for child in node.children)
    return re.sub(r"\s+", " ", raw.replace("\xa0", " ")).strip()


def _normalize_marker(marker: str) -> str:
    # "(a)" stays "(a)"; annex items "1." become "(1)" so labels read "Annex III(1)".
    marker = marker.strip()
    numbered = re.fullmatch(r"(\d+)\.", marker)
    return f"({numbered.group(1)})" if numbered else marker


def _passages_of_block(container: Node, base_label: str, skip: set[int]) -> list[dict]:
    """Split one block (a paragraph, a paragraph-less article, an annex) into passages.

    A block with a points table becomes one passage per point, each prefixed with the
    block's intro sentence so it reads on its own ("1. The following AI practices shall
    be prohibited: (f) ..."). A block without points is a single passage.
    """
    intro_parts, trailing_parts, rows = [], [], []
    heading = ""  # group heading between tables, e.g. Annex I "Section A. ..."
    for child in container.elements():
        if id(child) in skip:
            continue
        if child.tag == "table":
            for row in _top_level_rows(child):
                # Some tables have an empty leading layout cell (Annex I): the marker is
                # the first non-empty cell, the body is everything after it.
                cells = [text_of(cell) for cell in row.elements() if cell.tag == "td"]
                filled = [index for index, cell in enumerate(cells) if cell]
                if len(filled) >= 2:
                    marker = cells[filled[0]]
                    body = " ".join(cell for cell in cells[filled[0] + 1:] if cell)
                    rows.append((heading, marker, body))
        elif child.has_class("oj-ti-grseq-1"):
            heading = text_of(child)
        elif child.tag in ("p", "div"):
            (trailing_parts if rows else intro_parts).append(text_of(child))
    intro = " ".join(part for part in intro_parts if part)

    if not rows:
        full = " ".join(part for part in intro_parts + trailing_parts if part)
        return [{"label": base_label, "text": full}] if full else []

    passages = [
        {
            "label": f"{base_label}{_normalize_marker(marker)}",
            "text": " ".join(part for part in (intro, row_heading, marker, body) if part),
        }
        for row_heading, marker, body in rows
    ]
    trailing = " ".join(part for part in trailing_parts if part)
    if trailing:
        passages.append({"label": base_label, "text": f"{intro} {trailing}".strip()})
    return passages


def _top_level_rows(table: Node) -> list[Node]:
    # Rows of this table only, not of tables nested inside its cells (sub-points
    # (i), (ii)... stay inside their parent point's text).
    rows = []
    for child in table.elements():
        if child.tag == "tr":
            rows.append(child)
        elif child.tag in ("tbody", "thead"):
            rows.extend(node for node in child.elements() if node.tag == "tr")
    return rows


def _dedupe_labels(passages: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    for passage in passages:
        count = seen.get(passage["label"], 0)
        seen[passage["label"]] = count + 1
        if count:
            passage["label"] = f"{passage['label']}#{count + 1}"
    return passages


def parse_article(node: Node, number: str) -> dict:
    title_node = next((d for d in node.descendants() if d.id == f"art_{number}.tit_1"), None)
    heading = [child for child in node.elements() if child.has_class("oj-ti-art") or child is title_node]
    paragraphs = [child for child in node.elements() if _PARAGRAPH_ID_RE.match(child.id)]

    passages = []
    if paragraphs:
        for paragraph in paragraphs:
            paragraph_number = str(int(paragraph.id.split(".")[1]))
            for passage in _passages_of_block(paragraph, f"{number}({paragraph_number})", set()):
                passage["paragraph"] = paragraph_number
                passages.append(passage)
    else:
        passages = _passages_of_block(node, number, {id(h) for h in heading})
        for passage in passages:
            passage["paragraph"] = None
    return {"title": text_of(title_node) if title_node else "", "passages": _dedupe_labels(passages)}


def parse_annex(node: Node, roman: str) -> dict:
    titles = [child for child in node.elements() if child.has_class("oj-doc-ti")]
    title = text_of(titles[1]) if len(titles) > 1 else ""
    passages = _passages_of_block(node, f"Annex {roman}", {id(t) for t in titles})
    for passage in passages:
        marker = re.search(r"\((\d+)\)$", passage["label"])
        passage["paragraph"] = marker.group(1) if marker else None
    return {"title": title, "passages": _dedupe_labels(passages)}


def build(html: str) -> dict:
    builder = _TreeBuilder()
    builder.feed(html)
    by_id = builder.by_id

    articles, chapters = {}, {}
    for element_id, node in by_id.items():
        chapter_match = _CHAPTER_ID_RE.match(element_id)
        if not chapter_match:
            continue
        chapter, section = chapter_match.groups()
        title_node = by_id.get(f"{element_id}.tit_1")
        contained = [d.id.removeprefix("art_") for d in node.descendants() if re.fullmatch(r"art_\d+", d.id)]
        entry = chapters.setdefault(chapter, {"title": "", "articles": [], "sections": {}})
        if section:
            entry["sections"][section] = {"title": text_of(title_node) if title_node else "", "articles": contained}
        else:
            entry["title"] = text_of(title_node) if title_node else ""
            entry["articles"] = contained

    article_location = {}
    for chapter, entry in chapters.items():
        for number in entry["articles"]:
            article_location[number] = (chapter, None)
        for section, section_entry in entry["sections"].items():
            for number in section_entry["articles"]:
                article_location[number] = (chapter, section)

    for element_id, node in by_id.items():
        if re.fullmatch(r"art_\d+", element_id):
            number = element_id.removeprefix("art_")
            article = parse_article(node, number)
            article["chapter"], article["section"] = article_location.get(number, (None, None))
            articles[number] = article

    annexes = {
        element_id.removeprefix("anx_"): parse_annex(node, element_id.removeprefix("anx_"))
        for element_id, node in by_id.items()
        if re.fullmatch(r"anx_[IVXL]+", element_id)
    }

    return {
        "source": SOURCE_URL,
        "retrieved": date.today().isoformat(),
        "articles": dict(sorted(articles.items(), key=lambda item: int(item[0]))),
        "annexes": annexes,
        "chapters": chapters,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--html", type=Path, help="parse a saved copy instead of downloading")
    args = parser.parse_args()

    if args.html:
        html = args.html.read_text(encoding="utf-8")
    else:
        request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0 (cowsay corpus builder)"})
        with urllib.request.urlopen(request, timeout=120) as response:
            html = response.read().decode("utf-8")

    corpus = build(html)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(corpus, ensure_ascii=False, indent=1), encoding="utf-8")
    passages = sum(len(a["passages"]) for a in corpus["articles"].values())
    passages += sum(len(a["passages"]) for a in corpus["annexes"].values())
    print(f"{len(corpus['articles'])} articles, {len(corpus['annexes'])} annexes, "
          f"{len(corpus['chapters'])} chapters, {passages} passages -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
