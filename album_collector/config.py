from attrs import define


@define
class AlbumCollectorConfig:
    enabled: bool = True
    debounce_ms: int = 1000
    buffer_ttl_sec: int = 30
    max_items: int = 10
    flush_lock_ttl_sec: int = 30
    processed_ttl_sec: int = 86400
