from advertiser_blogger.application.common.exceptions.application_error import ManagerNotFound
from advertiser_blogger.application.common.exceptions.bot_error import DeeplinkError
from advertiser_blogger.application.common.use_case import UseCase
from advertiser_blogger.application.interactors_bot.create_actor.dto import CreateActorDtoInput
from advertiser_blogger.application.interactors_bot.create_actor.interface import DbGateway
from advertiser_blogger.domain.record.order.constants import Subrole
from advertiser_blogger.domain.record.user.user_service import UserService


class CreateActorInteractor(UseCase[CreateActorDtoInput, None]):
    def __init__(self, db_gateway: DbGateway, user_service: UserService):
        self.db_gateway = db_gateway
        self.user_service = user_service

    async def __call__(self, data: CreateActorDtoInput) -> None:
        if data.subrole == Subrole.publisher:
            manager_id = await self.db_gateway.get_user_by_project_id(project_id=data.project_id)
            if manager_id is None:
                await self.db_gateway.close()
                raise ManagerNotFound(message="Manager not Found")
            is_exist = await self.db_gateway.get_telegram_account_publisher(
                user_id=manager_id.id, telegram_id=data.telegram_id,
            )
            if is_exist is not None:
                await self.db_gateway.close()
                return
            publisher = self.user_service.create_telegram_account_publisher(
                user_id=manager_id.id, telegram_id=data.telegram_id
            )
            await self.db_gateway.create_telegram_account_publisher(publisher=publisher)
            await self.db_gateway.commit()
        elif data.subrole == Subrole.customer:
            is_exist = await self.db_gateway.get_telegram_account_customer(
                project_id=data.project_id, telegram_id=data.telegram_id,
            )
            if is_exist is not None:
                await self.db_gateway.close()
                return
            customer = self.user_service.create_telegram_account_customer(
                project_id=data.project_id, telegram_id=data.telegram_id,
            )
            await self.db_gateway.create_telegram_account_customer(customer=customer)
            await self.db_gateway.commit()
        else:
            await self.db_gateway.close()
            raise DeeplinkError()
