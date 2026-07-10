import html
from html.parser import HTMLParser

_RICH_TEXT_ALLOWED_TAGS = {"p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "u"}
_RICH_TEXT_STRIP_CONTENT_TAGS = {"script", "style"}


class _RichTextSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._strip_stack = []
        self._saw_tag = False

    @property
    def saw_tag(self) -> bool:
        return self._saw_tag

    def handle_starttag(self, tag, attrs):
        normalized = tag.lower()
        self._saw_tag = True
        if normalized in _RICH_TEXT_STRIP_CONTENT_TAGS:
            self._strip_stack.append(normalized)
            return
        if self._strip_stack:
            return
        if normalized in _RICH_TEXT_ALLOWED_TAGS:
            if normalized == "br":
                self.parts.append("<br>")
            else:
                self.parts.append(f"<{normalized}>")

    def handle_endtag(self, tag):
        normalized = tag.lower()
        self._saw_tag = True
        if normalized in _RICH_TEXT_STRIP_CONTENT_TAGS:
            if self._strip_stack and self._strip_stack[-1] == normalized:
                self._strip_stack.pop()
            return
        if self._strip_stack:
            return
        if normalized in _RICH_TEXT_ALLOWED_TAGS and normalized != "br":
            self.parts.append(f"</{normalized}>")

    def handle_data(self, data):
        if self._strip_stack or not data:
            return
        self.parts.append(html.escape(data))

    def handle_entityref(self, name):
        if not self._strip_stack:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self._strip_stack:
            self.parts.append(f"&#{name};")


def normalize_rich_text(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""

    parser = _RichTextSanitizer()
    parser.feed(value)
    parser.close()
    sanitized = "".join(parser.parts).strip()
    if parser.saw_tag:
        return sanitized
    return html.escape(value).replace("\n", "<br>")
