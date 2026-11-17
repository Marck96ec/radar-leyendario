import re
from html.parser import HTMLParser


MIN_SOURCE_CONTENT_CHARS = 400
MAX_SOURCE_CONTENT_CHARS = 12_000

_BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "pre",
    "section",
}
_IGNORED_TAGS = {"script", "style", "template", "noscript", "svg"}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible_chunks: list[str] = []
        self.article_chunks: list[str] = []
        self.main_chunks: list[str] = []
        self._ignored_depth = 0
        self._article_depth = 0
        self._main_depth = 0

    def handle_starttag(
        self, tag: str, _attrs: list[tuple[str, str | None]]
    ) -> None:
        del _attrs
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if normalized_tag == "article":
            self._article_depth += 1
        elif normalized_tag == "main":
            self._main_depth += 1
        if normalized_tag in _BLOCK_TAGS:
            self._append_break()

    def handle_startendtag(
        self, tag: str, _attrs: list[tuple[str, str | None]]
    ) -> None:
        del _attrs
        if not self._ignored_depth and tag.lower() in _BLOCK_TAGS:
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if normalized_tag == "article":
            self._article_depth = max(0, self._article_depth - 1)
        elif normalized_tag == "main":
            self._main_depth = max(0, self._main_depth - 1)
        if normalized_tag in _BLOCK_TAGS:
            self._append_break()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = data.strip()
        if not text:
            return
        self.visible_chunks.append(text)
        if self._article_depth:
            self.article_chunks.append(text)
        if self._main_depth:
            self.main_chunks.append(text)

    def _append_break(self) -> None:
        if self.visible_chunks and self.visible_chunks[-1] != "\n":
            self.visible_chunks.append("\n")
        if self.article_chunks and self.article_chunks[-1] != "\n":
            self.article_chunks.append("\n")
        if self.main_chunks and self.main_chunks[-1] != "\n":
            self.main_chunks.append("\n")


def clean_source_text(value: str, *, max_chars: int = MAX_SOURCE_CONTENT_CHARS) -> str:
    """Return readable text from RSS fragments or HTML documents."""
    parser = _VisibleTextParser()
    parser.feed(value)
    parser.close()
    text = _collapse_whitespace(" ".join(parser.visible_chunks))
    return text[:max_chars].strip()


def extract_article_text(
    html: str, *, max_chars: int = MAX_SOURCE_CONTENT_CHARS
) -> str:
    """Prefer article/main text while retaining a visible-text fallback."""
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()

    for chunks in (parser.article_chunks, parser.main_chunks, parser.visible_chunks):
        text = _collapse_whitespace(" ".join(chunks))
        if text:
            return text[:max_chars].strip()
    return ""


def has_sufficient_source_content(
    content: str, *, minimum_chars: int = MIN_SOURCE_CONTENT_CHARS
) -> bool:
    return len(clean_source_text(content)) >= minimum_chars


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
