from advertiser_blogger.application.common.db_interface.record import (
    ClearCommonCart,
    Commit,
    RecordCommonCart,
)


class DbGateway(ClearCommonCart, RecordCommonCart, Commit):
    pass
