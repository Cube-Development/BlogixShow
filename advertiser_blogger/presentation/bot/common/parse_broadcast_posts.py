from dataclasses import dataclass
import re

@dataclass
class PublishedPostsBroadcast:
    id: int
    post_url: str


def parse_broadcast_posts(text: str) -> list[PublishedPostsBroadcast]:
    result = []
    for line in text.splitlines():
        match = re.search(r'^\s*(\d+)\.\s*(https?://\S+)', line)
        if match:
            idx = int(match.group(1))  # берем id из текста (число перед точкой)
            url = match.group(2)
            result.append(PublishedPostsBroadcast(id=idx, post_url=url))
    return result
