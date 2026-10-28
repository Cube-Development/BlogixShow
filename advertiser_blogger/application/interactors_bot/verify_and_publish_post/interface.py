from typing import Protocol


class PostTextProvider(Protocol):
    async def fetch_text(self, post_url: str) -> str | None: ...


class VerifyReadGateway(Protocol):
    async def resolve_channel_ident_in_db(self, channel_ident: int) -> int | None:
        raise NotImplementedError

    async def get_channel_ident_by_username(self, username: str) -> int | None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError
