from advertiser_blogger.application.common.broker_interface import CreateScreenshotEvent
from advertiser_blogger.application.common.social_network.client import GetPostInfo
from advertiser_blogger.application.common.db_interface.record import (
    GetPostDate, GetPostTimeInterval, DeleteDateInterval, CreateOrderDate,
    CreatePublishedPost, Close, Commit, ChangeOrderStatus, IsExistPost, GetBloggerOrder, GetUserByProjectId,
    CreateEvent, GetExecutor, GetProjectOrderIdChannelStatus, AttachScreenshot, Flush, AttachTelegramIdToOrder,
    GetPlatformFromOrder, CreateCommonEvent, CreateCommonRetry, GetOrderDate, GetOrderDates, GetOrderDateIntervalMax,
)
from advertiser_blogger.application.common.didox_api.autoclicker_gateway import CreateScreenshot


class DbGateway(
    GetPostDate, GetPostTimeInterval, CreatePublishedPost, ChangeOrderStatus, IsExistPost, GetBloggerOrder,
    Close, Commit, GetUserByProjectId, CreateEvent, GetExecutor, GetProjectOrderIdChannelStatus,
    AttachScreenshot, Flush, AttachTelegramIdToOrder, GetPlatformFromOrder, CreateCommonEvent, CreateCommonRetry,
    GetOrderDate, GetOrderDates, DeleteDateInterval, CreateOrderDate, GetOrderDateIntervalMax,
):
    pass


class AutoclickerGateway(CreateScreenshot):
    pass


class SocialGateway(GetPostInfo):
    pass


class BrokerGateway(CreateScreenshotEvent):
    pass
