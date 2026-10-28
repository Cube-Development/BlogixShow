from advertiser_blogger.application.common.db_interface.record import (
    Commit,
    CreateOrder,
    CreateOrderIdentifier,
    CreateProject,
    CreateProjectIdentifier,
    Flush,
    GetChannelFormats,
    GetOrderExecutorId,
    GetCommonCart,
)


class DbGateway(
    GetCommonCart,
    GetOrderExecutorId,
    GetChannelFormats,
    CreateProject,
    CreateProjectIdentifier,
    CreateOrder,
    CreateOrderIdentifier,
    Flush,
    Commit,
):
    pass
