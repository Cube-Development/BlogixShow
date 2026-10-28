from advertiser_blogger.presentation.bot.handlers.agency.blogger import BloggerRouter
from advertiser_blogger.presentation.bot.handlers.agency.freeze_ack import FreezeAckRouter
from advertiser_blogger.presentation.bot.handlers.agency.publisher import PublisherRouter
from advertiser_blogger.presentation.bot.handlers.channel.channel_post import ChannelRouter
from advertiser_blogger.presentation.bot.handlers.channel.my_chat_member import MyChatMemberRouter
from advertiser_blogger.presentation.bot.handlers.errors import error_catcher
from advertiser_blogger.presentation.bot.handlers.user.bot_membership import BotMembershipRouter
from advertiser_blogger.presentation.bot.handlers.user.post_checking import PostCheckingRouter
from advertiser_blogger.presentation.bot.handlers.user.collect_createorder import CollectCreateorderRouter
from advertiser_blogger.presentation.bot.handlers.user.project_create import ProjectCreateRouter
from advertiser_blogger.presentation.bot.handlers.user.test_copy_album import TestCopyAlbumRouter
from advertiser_blogger.presentation.bot.handlers.user.user import UserRouter
from advertiser_blogger.presentation.bot.handlers.group.self_connect import GroupSelfEmployedRouter

main_router = [
    FreezeAckRouter,
    ChannelRouter,
    MyChatMemberRouter,
    BotMembershipRouter,
    PostCheckingRouter,
    TestCopyAlbumRouter,
    CollectCreateorderRouter,
    ProjectCreateRouter,
    UserRouter,
    GroupSelfEmployedRouter,
    PublisherRouter,
    BloggerRouter,
    error_catcher,
]
