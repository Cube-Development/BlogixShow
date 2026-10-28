from advertiser_blogger.application.common.exceptions.application_error import (
    AttachTgUserNotFound,
)
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.attach_user_from_app.dto import (
    AttachTgUserFromAppDtoInput,
)
from advertiser_blogger.application.interactors_bot.attach_user_from_app.interface import (
    DbGateway,
)
from advertiser_blogger.domain.record.user.entities import User


class AttachTgUserFromAppInteractor(UseCase[AttachTgUserFromAppDtoInput, User]):
    def __init__(self, db_gateway: DbGateway):
        self.db_gateway = db_gateway

    async def __call__(self, data: AttachTgUserFromAppDtoInput) -> User:
        attached_user = await self.db_gateway.get_attached_telegram_user_by_id(attach_id=data.attach_id)
        if attached_user is not None and attached_user.telegram_id == data.telegram_id:
            user = await self.db_gateway.get_user_by_id(user_id=attached_user.user_id)
            await self.db_gateway.close()
            return user
        if attached_user is None:
            await self.db_gateway.close()
            raise AttachTgUserNotFound()
        is_exist = await self.db_gateway.is_exist_telegram_id(telegram_id=data.telegram_id)
        if is_exist is not None and is_exist.id != attached_user.id:
            await self.db_gateway.delete_attach_telegram_user(attach_id=is_exist.id)
            await self.db_gateway.flush()
        if attached_user.telegram_id is None:
            await self.db_gateway.activate_attach_telegram_user(
                attach_id=data.attach_id, telegram_id=data.telegram_id, username=data.username,
            )
        user = await self.db_gateway.get_user_by_id(user_id=attached_user.user_id)
        await self.db_gateway.commit()
        return user
