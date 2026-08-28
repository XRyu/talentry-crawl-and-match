"""
HTML to Markdown converter for Talentry job descriptions.
Converts HTML tags (headings, paragraphs, lists, bold, italics, links, images)
into clean, well-formatted GitHub-Flavored Markdown.
"""

import re
import html
from html.parser import HTMLParser


class HTMLToMarkdown(HTMLParser):
    BLOCK_TAGS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'hr', 'blockquote'}

    def __init__(self):
        super().__init__()
        self.result = []
        self.list_depth = 0
        self.list_type = []  # 'ul' or 'ol'
        self.ol_counter = []
        self.tag_stack = []
        self.href_stack = []

    def _ensure_newline(self, count: int = 1):
        """Ensure the output ends with at least `count` newlines."""
        if not self.result:
            return
        # Count existing trailing newlines
        trailing = 0
        for chunk in reversed(self.result):
            for ch in reversed(chunk):
                if ch == '\n':
                    trailing += 1
                else:
                    break
            else:
                continue
            break
        needed = max(0, count - trailing)
        if needed > 0:
            self.result.append('\n' * needed)

    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag)
        attrs_dict = dict(attrs)

        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self._ensure_newline(2)
            level = int(tag[1])
            self.result.append(f"{'#' * level} ")
        elif tag == 'p':
            self._ensure_newline(2)
        elif tag == 'div':
            self._ensure_newline(1)
        elif tag == 'br':
            self.result.append("\n")
        elif tag == 'hr':
            self._ensure_newline(2)
            self.result.append("---\n\n")
        elif tag == 'ul':
            self._ensure_newline(1)
            self.list_depth += 1
            self.list_type.append('ul')
        elif tag == 'ol':
            self._ensure_newline(1)
            self.list_depth += 1
            self.list_type.append('ol')
            self.ol_counter.append(1)
        elif tag == 'li':
            self._ensure_newline(1)
            indent = "  " * max(0, self.list_depth - 1)
            if self.list_type and self.list_type[-1] == 'ol':
                cnt = self.ol_counter[-1]
                self.ol_counter[-1] += 1
                self.result.append(f"{indent}{cnt}. ")
            else:
                self.result.append(f"{indent}- ")
        elif tag in ['strong', 'b']:
            self.result.append("**")
        elif tag in ['em', 'i']:
            self.result.append("*")
        elif tag == 'code':
            self.result.append("`")
        elif tag == 'a':
            href = attrs_dict.get('href', '')
            self.href_stack.append(href)
            self.result.append("[")
        elif tag == 'img':
            src = attrs_dict.get('src', '')
            alt = attrs_dict.get('alt', '')
            if src:
                self._ensure_newline(2)
                self.result.append(f"![{alt}]({src})\n\n")

    def handle_endtag(self, tag):
        if self.tag_stack and tag in self.tag_stack:
            while self.tag_stack:
                popped = self.tag_stack.pop()
                if popped == tag:
                    break

        if tag in ['strong', 'b']:
            self.result.append("**")
        elif tag in ['em', 'i']:
            self.result.append("*")
        elif tag == 'code':
            self.result.append("`")
        elif tag == 'a':
            href = self.href_stack.pop() if self.href_stack else ""
            self.result.append(f"]({href})")
        elif tag == 'ul':
            if self.list_depth > 0:
                self.list_depth -= 1
                if self.list_type:
                    self.list_type.pop()
            self._ensure_newline(2)
        elif tag == 'ol':
            if self.list_depth > 0:
                self.list_depth -= 1
                if self.list_type:
                    self.list_type.pop()
                if self.ol_counter:
                    self.ol_counter.pop()
            self._ensure_newline(2)
        elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p']:
            self._ensure_newline(2)
        elif tag == 'div':
            self._ensure_newline(1)

    def handle_data(self, data):
        self.result.append(data)

    def get_markdown(self) -> str:
        raw_text = "".join(self.result)
        text = html.unescape(raw_text)

        # Fix headings wrapped in bold e.g. "### **DEINE ROLLE**" -> "### DEINE ROLLE"
        text = re.sub(r'^(#{1,6})\s*\*\*(.*?)\*\*\s*$', r'\1 \2', text, flags=re.MULTILINE)

        # Fix paragraph titles formatted as standalone bold lines: e.g. "**DEINE BENEFITS**\n" -> "### DEINE BENEFITS\n"
        def promote_bold_headers(match):
            content = match.group(1).strip()
            if content.isupper() and len(content) < 40:
                return f"### {content}"
            return f"**{content}**"

        text = re.sub(r'^\*\*(.*?)\*\*$', promote_bold_headers, text, flags=re.MULTILINE)

        # Fix spacing where bold tags were glued to list dashes: "-** " -> "- **"
        text = re.sub(r'-\s*\*\*', '- **', text)
        text = re.sub(r'(\d+\.)\s*\*\*', r'\1 **', text)

        # Fix trailing space inside bold tags: "**Title: **Text" -> "**Title:** Text"
        text = re.sub(r'\*\*([^\*\n]+?)\s+\*\*', r'**\1** ', text)

        # Clean list linebreaks & spaces
        lines = [line.rstrip() for line in text.split('\n')]
        cleaned_lines = []
        empty_count = 0
        for line in lines:
            if not line.strip():
                empty_count += 1
                if empty_count <= 1:
                    cleaned_lines.append('')
            else:
                empty_count = 0
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()


def html_to_markdown(html_content: str) -> str:
    """Convert HTML string to clean Markdown."""
    if not html_content:
        return ""
    parser = HTMLToMarkdown()
    parser.feed(html_content)
    return parser.get_markdown()
