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