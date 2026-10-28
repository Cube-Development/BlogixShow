from typing import Protocol

from advertiser_blogger.application.common.db_interface.record import (
    Close, Commit, GetOrderStatus, GetProjectOrderIds, ProjectExist,
)


class DbGateway(ProjectExist, GetProjectOrderIds, GetOrderStatus, Commit, Close, Protocol):
    pass
