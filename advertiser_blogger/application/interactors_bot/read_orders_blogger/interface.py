from advertiser_blogger.application.common.db_interface.read import (
    Close, ReadPostByPostId, CountProjectPosts, ReadUUIDProjectPosts,
)
from advertiser_blogger.application.common.obj_storage.obj_storage_interface import CreateReadLink


class DbGateway(
    Close, ReadPostByPostId, CountProjectPosts, ReadUUIDProjectPosts,
):
    pass


class ObjStorage(CreateReadLink):
    pass
