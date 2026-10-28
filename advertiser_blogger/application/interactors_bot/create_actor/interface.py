from advertiser_blogger.application.common.db_interface.record import (
    GetUserByProjectId, Close, Commit, CreateTelegramAccountPublisher, CreateTelegramAccountCustomer,
    GetTelegramAccountPublisher, GetTelegramAccountCustomer,
)


class DbGateway(
    GetUserByProjectId, Close, Commit, CreateTelegramAccountPublisher, CreateTelegramAccountCustomer,
    GetTelegramAccountPublisher, GetTelegramAccountCustomer,
):
    pass
