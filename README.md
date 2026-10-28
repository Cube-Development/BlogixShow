# Album Collector

Middleware для aiogram 3, которое собирает Telegram **media group** (альбом из нескольких фото/видео) в одно событие.

## Проблема

Telegram присылает альбом не одним сообщением, а серией отдельных updates с общим `media_group_id`:

- обычный handler срабатывает на каждую часть, и бизнес-логика выполняется N раз;
- caption обычно есть только у одной части, причём не обязательно у первой;
- у пересланного альбома `forward_origin` есть у каждой части, поэтому источник нельзя брать из одного произвольного сообщения;
- если у бота несколько воркеров, части одного альбома могут попасть на разные инстансы.

## Решение

```
update ─► AlbumCollectorMiddleware ─► AlbumCollector.register_part
                                          │
                                          ├─ Redis: атомарный append (Lua) + дедупликация по message_id
                                          ├─ debounce-таймер (сброс на каждой новой части)
                                          └─ max_items достигнут → немедленный flush
                                                   │
                                          flush: distributed lock (SET NX + безопасный release через Lua)
                                                   │
                                          on_flush(AggregatedAlbum) ─► True  → mark_processed + delete buffer
                                                                       False/exception → буфер остаётся до TTL
```

Ключевые моменты:

- **Атомарность**: append и проверка дубликата выполняются одним Lua-скриптом, поэтому части не теряются при параллельной обработке.
- **Ровно один flush**: lock с UUID-владельцем, и снять его может только тот, кто его взял.
- **Идемпотентность**: после успешной обработки альбом помечается как `processed`, поэтому повторно доставленные updates игнорируются.
- **At-least-once**: если `on_flush` вернул `False` или упал, альбом не помечается обработанным.
- **Хранилище за протоколом** `AlbumBufferStore`: в проде используется Redis, в тестах in-memory реализация.

## Структура

| Файл | Роль |
|------|------|
| `album_collector/middleware.py` | outer middleware на `Dispatcher.message` |
| `album_collector/collector.py` | debounce, flush, преобразование `Message` → `AlbumPart` |
| `album_collector/redis_store.py` | Redis-хранилище, Lua-скрипты, lock |
| `album_collector/memory_store.py` | in-memory хранилище для тестов |
| `album_collector/forward_message.py` | извлечение источника пересланного сообщения |
| `album_collector/post_submission.py` | сборка итоговой структуры из альбома |

## Подключение

```python
store = RedisAlbumBufferStore(redis=redis, config=config)
collector = AlbumCollector(store=store, config=config, on_flush=handle_album)
dp.message.outer_middleware(AlbumCollectorMiddleware(collector))
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Redis в тестах эмулируется через `fakeredis[lua]`, поэтому поднимать отдельный сервер не нужно.

---

Этот модуль взят из коммерческого проекта и опубликован только для ознакомления. См. [LICENSE](LICENSE).
