from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import re

register = template.Library()


@register.filter(name="highlight")
def highlight(text, terms):
    """
    Wrap occurrences of any term in `terms` inside the given `text` with
    <span class="highlight">...</span>. Case-insensitive; supports multi-word terms.
    `terms` should be an iterable of strings. If empty or None, returns text.
    """
    if text is None:
        return ""

    if not terms:
        return escape(text)

    # Filter out empty terms and deduplicate while preserving order
    cleaned = []
    seen = set()
    for t in terms:
        t = (t or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            cleaned.append(t)

    if not cleaned:
        return escape(text)

    # Escape text to avoid breaking HTML, then apply highlighting
    safe_text = escape(text)

    # Build one combined regex that matches any term, case-insensitive
    pattern = re.compile(r"(" + "|".join(re.escape(t) for t in cleaned) + r")", re.IGNORECASE)

    def repl(m):
        return f'<span class="highlight">{m.group(0)}</span>'

    highlighted = pattern.sub(repl, safe_text)
    return mark_safe(highlighted)


@register.filter(name="url_with_icons")
def url_with_icons(text):
    """
    Detects URLs in text and adds icons if they match Estadao or Folha.
    Supports input that might already contain HTML (like from the highlight filter).
    """
    if not text:
        return ""

    # Simple URL pattern
    url_pattern = re.compile(r'(https?://[^\s<"]+)')

    def repl(match):
        url = match.group(0)
        icon_html = ""
        
        if url.startswith("https://www.estadao.com.br/"):
            icon_url = "https://yt3.ggpht.com/dadwqkT3WM7VFPtTSOfacJmMynJsDTj5EfX6uDL0USiae1ZCzePFidLi4J_tTCQFALPefY11Oxk=s176-c-k-c0x00ffffff-no-rj-mo"
            icon_html = f'<img src="{icon_url}" width="16" height="16" class="me-1" style="border-radius: 50%; vertical-align: middle;">'
        elif url.startswith("https://www1.folha.uol.com.br/"):
            icon_url = "https://yt3.googleusercontent.com/hueB58GarYamE3VfoTU_kiHuftYCM_lCZxdkfKbs380f7Obx9HJn8hf0islbiYTj74DFpjONBg=s160-c-k-c0x00ffffff-no-rj"
            icon_html = f'<img src="{icon_url}" width="16" height="16" class="me-1" style="border-radius: 50%; vertical-align: middle;">'
        
        return f'{icon_html}<a href="{url}" target="_blank">{url}</a>'

    # We need to be careful not to match URLs inside of already existing tags.
    # For now, let's assume it's just plain text or highlighted text.
    result = url_pattern.sub(repl, text)
    return mark_safe(result)