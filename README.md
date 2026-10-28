# Album Collector

An [aiogram 3](https://docs.aiogram.dev/) middleware that turns a Telegram **media group** (an album of several photos / videos / documents) into **one** event, safely, across multiple bot workers.

> Extracted from a production Telegram bot of an advertising marketplace and published for review only. See [LICENSE](LICENSE).

---

## Table of contents

- [Background](#background)
- [The problem](#the-problem)
- [How it works](#how-it-works)
  - [Components](#components)
  - [End-to-end flow](#end-to-end-flow)
  - [Step by step](#step-by-step)
  - [Redis data layout](#redis-data-layout)
  - [Register results](#register-results)
  - [Forwarded albums](#forwarded-albums)
- [Guarantees](#guarantees)
- [Edge cases](#edge-cases)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Design decisions and trade-offs](#design-decisions-and-trade-offs)

---

## Background

The bot belongs to a marketplace where advertisers buy ad placements in Telegram channels. After a channel owner publishes an ad post, they send it to the bot as proof: a link to the post, a forward of the post, or the post's media. The bot then verifies the submission.

Many ad posts are **albums**. Forwarding an album to the bot is the most natural thing for a user to do, and this is where things break without special handling.

## The problem

Telegram does not deliver an album as one message. It delivers **N separate updates** that share a `media_group_id`:

```
update 1001  message 501  photo  media_group_id=777  caption="Ad text..."
update 1002  message 502  photo  media_group_id=777
update 1003  message 503  video  media_group_id=777
```

This causes four problems:

1. **Duplicate processing.** A regular handler fires once per part, so verification (and every side effect behind it) runs N times.
2. **The caption is on one part only**, and it is not always the first part to arrive. Updates can come out of order.
3. **Forward metadata is per part.** Each forwarded part carries its own `forward_origin`. You cannot just take "the last message" and trust it as the album source.
4. **Horizontal scaling.** With several bot workers behind a webhook, the parts of one album can land on different processes. An in-memory buffer cannot see the whole album.

There is also no "album finished" signal from Telegram. The only option is to wait for a quiet period.

## How it works

The idea: intercept album parts **before** any handler sees them, accumulate them in Redis, and when the album has stopped growing, hand the complete album to a single callback exactly once.

### Components

| Component | Responsibility |
|-----------|----------------|
| `AlbumCollectorMiddleware` | Outer middleware on `Dispatcher.message`. Lets normal messages through, routes album parts to the collector and stops them from reaching handlers. |
| `AlbumCollector` | Converts `Message` → `AlbumPart`, runs the debounce timer, performs the flush and calls `on_flush`. |
| `AlbumBufferStore` (protocol) | Storage contract: append, get, delete, lock, processed marker. |
| `RedisAlbumBufferStore` | Production storage. Atomic append and safe lock release through Lua scripts. |
| `InMemoryAlbumBufferStore` | Same contract in memory, used in tests. |
| `forward_message` | Extracts forward source (channel id, username, message id, post URL) from a message or a stored part. |
| `post_submission` | Builds the final `PostSubmissionInput` from an aggregated album. |

### End-to-end flow

```mermaid
sequenceDiagram
    autonumber
    participant TG as Telegram
    participant MW as AlbumCollectorMiddleware
    participant C as AlbumCollector
    participant R as Redis
    participant H as on_flush callback

    TG->>MW: update (part 1, media_group_id=777)
    MW->>C: register_part()
    C->>R: EXISTS processed:777?
    R-->>C: no
    C->>R: EVAL append.lua (dedup + append + TTL)
    R-->>C: {status: ok, flush_immediately: false}
    C->>C: start debounce timer (1000 ms)
    C-->>MW: PENDING
    MW--xTG: handler is NOT called

    TG->>MW: update (part 2)
    MW->>C: register_part()
    C->>R: EVAL append.lua
    C->>C: restart debounce timer
    C-->>MW: PENDING

    Note over C: no new parts for debounce_ms

    C->>R: SET flush_lock NX EX
    R-->>C: OK (lock uuid)
    C->>R: GET buffer
    R-->>C: AggregatedAlbum (all parts)
    C->>H: on_flush(album, last_message)
    H-->>C: True
    C->>R: SET processed:777 EX 86400
    C->>R: DEL buffer
    C->>R: EVAL release_lock.lua (only if uuid matches)
```

### Step by step

**1. Middleware filter.**
The middleware checks the incoming event. If it is not a `Message`, or `media_group_id` is `None`, it calls the next handler as usual. Single messages, commands and links are not affected at all.

**2. Pre-checks in `register_part`.**
The part is ignored if:
- the message has no sender (`from_user is None`);
- the album is already marked as processed in Redis (a late or re-delivered update);
- the part has no supported media (photo / video / document).

**3. Normalization.**
The `Message` is converted into an immutable `AlbumPart`. It keeps only what is needed later: ids, `file_id`, media type, caption, date and forward metadata. For photos the largest size is taken. This makes the part serializable and independent of aiogram objects.

**4. Atomic append (Lua).**
A single Lua script runs inside Redis:
1. reads the buffer, or creates it from a skeleton;
2. returns `duplicate` if a part with the same `message_id` is already there;
3. appends the part, updates `updated_at` and resets the TTL;
4. returns `flush_immediately = true` if the album reached `max_items` (Telegram's album limit is 10).

Because it is one script, concurrent appends from different workers cannot overwrite each other. A plain `GET` → modify → `SET` would lose parts.

**5. Debounce.**
For each `(chat_id, media_group_id)` the collector keeps one `asyncio.Task` that sleeps for `debounce_ms`. Every new part cancels the previous timer and starts a new one. So the flush happens `debounce_ms` after the **last** part. If `max_items` is reached, the timer is cancelled and the flush starts immediately.

**6. Flush under a distributed lock.**
The flush starts with `SET flush_lock <uuid> NX EX flush_lock_ttl_sec`.
- If the lock is taken, someone else is flushing this album, so the call just returns.
- The buffer is read. If it has expired, a warning is logged and the flush stops.
- `on_flush(aggregated, last_message)` is called. `last_message` is passed so the callback can reply to the user.

**7. Commit or keep.**
- `on_flush` returned `True`: the album is marked `processed` (24 h by default) and the buffer is deleted.
- `on_flush` returned `False` or raised: nothing is committed. The buffer remains until its TTL expires.

**8. Safe lock release.**
In `finally`, the lock is released by a Lua script that deletes the key **only if it still holds our uuid**. If the lock had expired and another worker took it, we will not delete someone else's lock.

### Redis data layout

| Key | Value | TTL | Purpose |
|-----|-------|-----|---------|
| `telegram:album:{chat_id}:{media_group_id}` | JSON `AggregatedAlbum` | `buffer_ttl_sec`, refreshed on each append | parts buffer |
| `telegram:album:flush_lock:{chat_id}:{media_group_id}` | lock owner uuid | `flush_lock_ttl_sec` | one flush at a time |
| `telegram:album:processed:{chat_id}:{media_group_id}` | `"1"` | `processed_ttl_sec` | idempotency marker |

Every key has a TTL, so a crashed worker never leaves garbage in Redis forever.

### Register results

`register_part` returns a `RegisterResult`, and the middleware acts on it:

| Result | Meaning | Middleware |
|--------|---------|------------|
| `PENDING` | part stored, debounce timer (re)started | stop, no handler |
| `FLUSH_SCHEDULED` | `max_items` reached, flush started | stop, no handler |
| `DUPLICATE` | same `message_id` already in the buffer | stop, no handler |
| `IGNORED` | already processed / no media / no sender | log a warning, stop |

### Forwarded albums

When a user forwards an album from a channel, each part has its own forward metadata. `AlbumPart` stores it explicitly (`forward_chat_id`, `forward_chat_username`, `forward_message_id`, `forward_date`), so it survives the round trip through Redis.

When building the result, `AggregatedAlbum` gives deterministic answers regardless of arrival order:

- `caption`: the first non-empty caption, by `message_id`;
- `primary_message_id`: the part with the caption, or the smallest `message_id`;
- `forward_part`: the first forwarded part, by `message_id`.

`extract_post_submission_from_album` then builds a `PostSubmissionInput`:

- **forwarded album**: channel id / username and the post URL (`https://t.me/<username>/<id>` or `https://t.me/c/<id>/<msg>` for private channels) come from the forward source; the caption becomes the post text;
- **album with a link in the caption**: channel and post are parsed from the URL; if the caption is *only* a link, the text is `None`;
- in both cases, the media list is sorted by `message_id`.

Both the legacy `forward_from_chat` fields and the newer `forward_origin` API are supported.

## Guarantees

| Property | How |
|----------|-----|
| No lost parts under concurrency | append + dedup in one Lua script |
| One flush per album | `SET NX` lock with owner uuid |
| No reprocessing of re-delivered updates | `processed` marker checked before append |
| At-least-once handling | the marker is set only after `on_flush` returns `True` |
| No foreign lock release | compare-and-delete Lua script |
| Bounded memory | TTL on every key; timers and `last_message` are removed on flush |
| Order independence | results are derived from parts sorted by `message_id` |

## Edge cases

| Situation | Behaviour |
|-----------|-----------|
| Parts arrive out of order | stored as they come, sorted at read time |
| Same update delivered twice | `DUPLICATE`, ignored |
| Late part after a successful flush | `IGNORED` (album already processed) |
| Album bigger than `max_items` | flushed as soon as the limit is reached |
| Two workers flush simultaneously | one gets the lock, the other returns |
| Callback fails | not marked processed; logged |
| Buffer expired before flush | logged, nothing is called |
| Text-only message or command | not touched by the middleware |

## Configuration

```python
@define
class AlbumCollectorConfig:
    enabled: bool = True
    debounce_ms: int = 1000          # quiet period before flush
    buffer_ttl_sec: int = 30         # buffer lifetime, refreshed on every part
    max_items: int = 10              # flush immediately at this size
    flush_lock_ttl_sec: int = 30     # must be longer than on_flush runtime
    processed_ttl_sec: int = 86400   # how long re-deliveries are ignored
```

How to choose the values:
- `debounce_ms` is a trade-off between latency and completeness. About 1 s is enough for Telegram to deliver all parts in practice.
- `buffer_ttl_sec` must be noticeably larger than `debounce_ms`.
- `flush_lock_ttl_sec` must cover the worst-case duration of `on_flush`.

## Usage

```python
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from redis.asyncio import Redis

from album_collector.collector import AlbumCollector
from album_collector.config import AlbumCollectorConfig
from album_collector.middleware import AlbumCollectorMiddleware
from album_collector.models import AggregatedAlbum
from album_collector.post_submission import extract_post_submission_from_album
from album_collector.redis_store import RedisAlbumBufferStore


async def handle_album(album: AggregatedAlbum, last_message: Message) -> bool:
    submission = extract_post_submission_from_album(aggregated=album)
    await last_message.answer(
        f"Got an album of {len(submission.media)} items, post: {submission.post_url or '-'}"
    )
    return True  # True = processed, do not handle again


config = AlbumCollectorConfig()
store = RedisAlbumBufferStore(redis=Redis.from_url("redis://localhost:6379"), config=config)
collector = AlbumCollector(store=store, config=config, on_flush=handle_album)

dp = Dispatcher()
dp.message.outer_middleware(AlbumCollectorMiddleware(collector))
```

Return `False` from the callback (or raise) when the album could not be handled. It will not be marked as processed.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Redis is emulated with `fakeredis[lua]`, so no server is needed and the real Lua scripts run in tests.

What is covered (18 tests):

- debounce flushes all parts exactly once;
- `max_items` triggers an immediate flush;
- duplicate `message_id` is rejected;
- processed albums are ignored;
- commit only on success: `True` commits, `False` and exceptions do not;
- concurrent appends do not lose parts;
- a second lock attempt fails while the first one holds the lock;
- a worker cannot release a lock it does not own;
- buffer TTL expiry;
- forward metadata survives a Redis round trip;
- caption / link / forward parsing into `PostSubmissionInput`.

## Project structure

```
album_collector/
├── middleware.py         # aiogram outer middleware
├── collector.py          # debounce, flush, Message -> AlbumPart
├── models.py             # AlbumPart, AggregatedAlbum, RegisterResult
├── redis_store.py        # AlbumBufferStore protocol + Redis implementation (Lua)
├── memory_store.py       # in-memory implementation for tests
├── forward_message.py    # forward source extraction, post URL building
├── post_submission.py    # AggregatedAlbum -> PostSubmissionInput
├── telegram_post_url.py  # t.me post URL matching
└── config.py             # AlbumCollectorConfig
tests/
├── test_album_collector.py
└── test_redis_store.py
```

## Design decisions and trade-offs

- **Middleware, not a handler.** Album parts are stopped before routing, so no existing handler has to know about albums. Business logic receives an already complete album.
- **Storage behind a protocol.** The collector depends on `AlbumBufferStore`, not on Redis. Tests use the in-memory store, production uses Redis, and the collector code is the same.
- **Lua instead of `WATCH`/`MULTI`.** One round trip, no retry loops, and the dedup check is atomic with the write.
- **Callback decides success.** The collector does not know what "processed" means. The callback returns a boolean, and that keeps the module reusable.
- **Debounce timers are per process.** The timer lives in the worker that received the part. With several workers, each one may try to flush. The Redis lock and the `processed` marker make sure only one flush wins, and later attempts see the buffer gone. The cost is that a worker may fire its flush slightly before parts that went to another worker have arrived. In practice the debounce window covers this, and the shared Redis buffer means the winner still sees every part appended so far.
