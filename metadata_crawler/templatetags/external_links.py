from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import re

register = template.Library()

@register.filter(name="url_with_icons")
def url_with_icons(text):
    """
    Detects URLs in text and adds icons if they match Estadao or Folha.
    Supports input that might already contain HTML (like from the highlight filter).
    """
    if not text:
        return ""

    # If it's already safe (like from highlight), we should be careful not to escape it again.
    # But we want to find URLs. URLs in the middle of HTML tags might be tricky.
    
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
