import re
import html as html_lib
from bs4 import BeautifulSoup, NavigableString, Tag, Comment


def cleanup(text: str) -> str:
    """Очистка текста от лишних пробелов, табуляций и переносов."""
    if not text:
        return ""
    text = text.replace("\r", "")
    # Убираем лишние горизонтальные пробелы
    text = re.sub(r"[ \t]+", " ", text)
    # Сокращаем 3+ переноса до 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_html_for_telegram(html: str) -> str:
    """Нормализует HTML для Telegram: убирает head/meta/style, делает <a> верхним тегом."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Удаляем ненужные теги
    for tag in soup.find_all(["meta", "style", "script", "head", "title"]):
        tag.decompose()

    result: list[str] = []

    TAG_MAP = {
        "b": "b", "strong": "b",
        "i": "i", "em": "i",
        "u": "u", "ins": "u",
        "s": "s", "strike": "s", "del": "s",
        "code": "code",
        "pre": "pre",
        "blockquote": "blockquote"
    }

    def walk(node, styles: list[str], in_link: bool = False):
        if isinstance(node, Comment):
            return

        if isinstance(node, NavigableString):
            content = str(node)
            # Не пропускаем пробелы, если они внутри тегов, но и не плодим лишние
            if not content.strip() and "\n" not in content and not styles and not in_link:
                return
            
            escaped = html_lib.escape(content)
            for s in reversed(styles):
                escaped = f"<{s}>{escaped}</{s}>"
            
            result.append(escaped)
            return

        if not isinstance(node, Tag):
            return

        name = node.name.lower()

        if name == "br":
            result.append("\n")
            return

        if name in {"p", "div"}:
            for child in node.children:
                walk(child, styles, in_link)
            result.append("\n\n")
            return

        if name == "a":
            if in_link:
                 for child in node.children:
                     walk(child, styles, True)
                 return

            # Telegram НЕ допускает ссылки с пустым текстом.
            if not node.get_text(strip=True):
                return

            href = node.get("href") or ""
            result.append(f'<a href="{html_lib.escape(href)}">')
            for child in node.children:
                walk(child, styles, True)
            result.append("</a>")
            return

        if name in TAG_MAP:
            telegram_tag = TAG_MAP[name]
            
            if telegram_tag in {"code", "pre"}:
                text_content = node.get_text()
                if text_content.strip() or "\n" in text_content:
                    result.append(f"<{telegram_tag}>{html_lib.escape(text_content)}</{telegram_tag}>")
            elif telegram_tag == "blockquote":
                if not node.get_text(strip=True):
                    return
                result.append("<blockquote>")
                for child in node.children:
                    walk(child, styles, in_link)
                result.append("</blockquote>")
            else:
                new_styles = styles if telegram_tag in styles else styles + [telegram_tag]
                for child in node.children:
                    walk(child, new_styles, in_link)
            return

        for child in node.children:
            walk(child, styles, in_link)

    root = soup.body if soup.body else soup
    for child in root.children:
        walk(child, [], False)

    final_text = "".join(result)
    final_text = final_text.replace("&nbsp;", " ").replace("\xa0", " ")
    
    return cleanup(final_text)


def safe_truncate_html(html: str, max_len: int) -> tuple[str, str | None]:
    """
    Безопасно обрезает HTML, закрывая все открытые теги для первой части 
    и открывая их заново для второй.
    Возвращает (caption, extra_text).
    """
    if not html or len(html) <= max_len:
        return html, None

    # Поиск безопасной точки разреза (не внутри тега и не внутри сущности)
    cut_idx = max_len
    
    # Не режем посреди тега <...>
    last_open_bracket = html.rfind("<", 0, cut_idx)
    last_close_bracket = html.rfind(">", 0, cut_idx)
    if last_open_bracket > last_close_bracket:
        cut_idx = last_open_bracket
        
    # Не режем посреди сущности &...;
    last_amp = html.rfind("&", 0, cut_idx)
    last_semi = html.rfind(";", 0, cut_idx)
    if last_amp > last_semi:
        cut_idx = last_amp

    head = html[:cut_idx]
    tail = html[cut_idx:]

    # Анализ баланса тегов в head
    open_tags_full = [] # [<a href="...">, <b>, ...]
    open_tag_names = [] # [a, b, ...]
    
    tag_pattern = re.compile(r"<(/?)([a-z1-6]+)([^>]*)>", re.I)
    
    for match in tag_pattern.finditer(head):
        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()
        if is_closing:
            if open_tag_names and open_tag_names[-1] == tag_name:
                open_tag_names.pop()
                open_tags_full.pop()
        elif tag_name != "br":
            open_tag_names.append(tag_name)
            open_tags_full.append(match.group(0))

    # Формируем Caption (закрываем теги)
    caption = head
    for name in reversed(open_tag_names):
        caption += f"</{name}>"
        
    # Формируем Extra (открываем теги заново)
    extra = "".join(open_tags_full) + tail
    
    return caption, extra