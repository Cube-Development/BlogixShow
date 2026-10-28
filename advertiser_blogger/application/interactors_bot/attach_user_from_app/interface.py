from advertiser_blogger.application.common.db_interface.record import (
    GetAttachedTelegramUserById, ActivateAttachTelegramUser, Commit, Close, GetUserById, IsExistTelegramId,
    DeleteAttachTelegramUser, Flush,
)


class DbGateway(
    GetAttachedTelegramUserById, ActivateAttachTelegramUser, Commit, Close,
    GetUserById, IsExistTelegramId, DeleteAttachTelegramUser, Flush,
):
    pass
