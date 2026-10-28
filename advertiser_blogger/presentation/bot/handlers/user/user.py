import asyncio
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.methods import (
    SendAnimation,
    SendDocument,
    SendMediaGroup,
    SendPhoto,
    SendVideo,
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultDocument,
    InlineQueryResultGif,
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InputMediaPhoto,
    InputMediaVideo,
    InputTextMessageContent,
    Message,
    MessageId,
    URLInputFile,
    WebAppInfo,
)
from aiogram.utils.markdown import hlink
from aiogram.utils.payload import decode_payload
from aiohttp import ClientSession
from dishka import FromDishka
from pydantic import ValidationError
from sqlalchemy.orm import exc

from advertiser_blogger.application.common.bot.collect_start_payload import (
    CollectStartPayloadUnsupportedVersion,
    decode_collect_start_payload,
)
from advertiser_blogger.application.common.cache.models import GetRedisData
from advertiser_blogger.application.common.exceptions.application_error import (
    PostNotFound,
)
from advertiser_blogger.application.interactors_bot.attach_user_from_app.dto import (
    AttachTgUserFromAppDtoInput,
)
from advertiser_blogger.application.interactors_bot.attach_user_from_app.use_case import (
    AttachTgUserFromAppInteractor,
)
from advertiser_blogger.application.interactors_bot.create_actor.dto import (
    CreateActorDtoInput,
)
from advertiser_blogger.application.interactors_bot.create_actor.use_case import (
    CreateActorInteractor,
)
from advertiser_blogger.application.interactors_bot.verify_submission_processor.dto import (
    VerifyContext,
)
from advertiser_blogger.application.interactors_bot.verify_submission_processor.use_case import (
    VerifySubmissionProcessor,
)
from advertiser_blogger.application.read.read_post.dto import ReadPostDtoInput
from advertiser_blogger.application.read.read_post.use_case import ReadPostInteractor
from advertiser_blogger.domain.common.telegram_post_url import resolve_expected_from_tz
from advertiser_blogger.domain.read.constants import Role
from advertiser_blogger.domain.record.order.constants import DeeplinkType
from advertiser_blogger.domain.record.user.entities import User
from advertiser_blogger.infrastructure.bot.deeplink import DeeplinkData
from advertiser_blogger.infrastructure.bot.post_builder import *
from advertiser_blogger.infrastructure.bot.start_payload import (
    StartPayloadMalformed,
    is_compact_start_args,
)
from advertiser_blogger.infrastructure.cache.cache_client import RedisCacheSystem
from advertiser_blogger.infrastructure.db.repositories.bot_repository import (
    BotRepository,
)
from advertiser_blogger.infrastructure.db.repositories.record import UserRepository
from advertiser_blogger.infrastructure.parsers.telegram_public_channel_album_ids import (
    TelegramPublicChannelAlbumIdsProvider,
)
from advertiser_blogger.presentation.bot.common import InlineMessageType
from advertiser_blogger.presentation.bot.common.extract_post_submission import (
    extract_post_submission,
)
from advertiser_blogger.presentation.bot.filters.get_user import GetUserByTelegramId
from advertiser_blogger.presentation.bot.filters.post_submission import IsPostSubmission
from advertiser_blogger.presentation.bot.handlers.user.collect_createorder import (
    begin_collect_createorder_from_start,
    handle_collect_start_decode_error,
)
from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard
from advertiser_blogger.presentation.bot.keyboards.reply import ReplyKeyboard
from configuration.common import CommonConfig


UserRouter = Router(name="UserRouter")

_BLOGIX_POSTS_USERNAME = "blogix_posts"


def extract_post_id(url: str, channel_username: str) -> int | None:
    path_parts = urlparse(url).path.strip("/").split("/")

    if len(path_parts) != 2:
        return None

    username, post_id = path_parts

    if username != channel_username:
        return None

    if not post_id.isdigit():
        return None

    return int(post_id)


async def send_error_message(
    exc_message: str,
    message: Message,
    method: Any,
    bot: Bot,
    post: TelegramMessage,
    count: int = 1,
) -> Message | None:
    msg: Message | None = None
    try:
        await bot.send_message(
            chat_id=message.from_user.id, text="❗️Не удалось загрузить пост"
        )
        if type(method) is SendPhoto:
            photo: SendPhoto = method
            if exc_message == "Bad Request: failed to get HTTP URL content":
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на фото: {hlink(url=photo.photo, title='Скачать')}",
                )
            elif exc_message == "Bad Request: message caption is too long":
                msg = await bot.send_photo(
                    chat_id=message.from_user.id, photo=photo.photo
                )
            else:
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на фото: {hlink(url=photo.photo, title='Скачать')}",
                )
        elif type(method) is SendDocument:
            document: SendDocument = method
            if exc_message == "Bad Request: failed to get HTTP URL content":
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на документ: {hlink(url=document.document, title='Скачать')}",
                )
            elif exc_message == "Bad Request: message caption is too long":
                msg = await bot.send_document(
                    chat_id=message.from_user.id, document=document.document
                )
            else:
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на документ: {hlink(url=document.document, title='Скачать')}",
                )
        elif type(method) is SendVideo:
            video: SendVideo = method
            if exc_message == "Bad Request: failed to get HTTP URL content":
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на видео: {hlink(url=video.video, title='Скачать')}",
                )
            elif exc_message == "Bad Request: message caption is too long":
                msg = await bot.send_video(
                    chat_id=message.from_user.id, video=video.video
                )
            else:
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на видео: {hlink(url=video.video, title='Скачать')}",
                )
        elif type(method) is SendAnimation:
            animation: SendAnimation = method
            if exc_message == "Bad Request: failed to get HTTP URL content":
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на анимацию: {hlink(url=animation.animation, title='Скачать')}",
                )
            elif exc_message == "Bad Request: message caption is too long":
                msg = await bot.send_animation(
                    chat_id=message.from_user.id, animation=animation.animation
                )
            else:
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=f"Ссылка на анимацию: {hlink(url=animation.animation, title='Скачать')}",
                )
        elif type(method) is SendMediaGroup:
            mediagroup: SendMediaGroup = method
            await bot.send_message(
                chat_id=message.from_user.id, text="❗️Не удалось загрузить медиагруппу"
            )
        if post.text is not None:
            msg = await bot.send_message(
                chat_id=message.from_user.id,
                text=post.text,
                reply_markup=post_markup(buttons=post.buttons),
            )
    except TelegramBadRequest as ex:
        method_name = type(method).__name__
        meta_parts: list[str] = []
        for attr in ("chat_id", "from_chat_id", "message_id"):
            if hasattr(method, attr):
                meta_parts.append(f"{attr}={getattr(method, attr)}")
        meta = (" " + " ".join(meta_parts)) if meta_parts else ""
        print(
            f"[send_error_message] bad_request={ex.message} method={method_name}{meta}",
            flush=True,
        )
        if "chat not found" in ex.message.lower():
            return None
        if count < 4:
            count += 1
            await asyncio.sleep(1)
            msg = await send_error_message("", message, method, bot, post, count=count)
        else:
            msg = None
    return msg


async def send_post(
    post: TelegramMessage,
    message: Message | CallbackQuery,
    bot: Bot,
    repo: UserRepository,
    post_id: UUID,
    album_ids_provider: TelegramPublicChannelAlbumIdsProvider,
    tz_channel_id: int,
) -> int | None:
    msg = None
    try:
        if post.type == MessageType.TEXT:
            post_url, _ = resolve_expected_from_tz(tz_text=post.text or "")
            post_telegram_id = (
                extract_post_id(url=post_url, channel_username=_BLOGIX_POSTS_USERNAME)
                if post_url is not None
                else None
            )
            if post_telegram_id is not None and post_url is not None:
                message_ids = await album_ids_provider.fetch_album_message_ids(post_url)
                if not message_ids:
                    message_ids = [post_telegram_id]
                if len(message_ids) == 1:
                    msg = await bot.copy_message(
                        chat_id=message.from_user.id,
                        from_chat_id=tz_channel_id,
                        message_id=message_ids[0],
                    )
                else:
                    msg = await bot.copy_messages(
                        chat_id=message.from_user.id,
                        from_chat_id=tz_channel_id,
                        message_ids=message_ids,
                    )
            else:
                msg = await bot.send_message(
                    chat_id=message.from_user.id,
                    text=post.text,
                    reply_markup=post_markup(buttons=post.buttons),
                )
        elif post.type == MessageType.PHOTO:
            msg = await bot.send_photo(
                chat_id=message.from_user.id,
                photo=post.photo[0],
                reply_markup=post_markup(buttons=post.buttons),
            )
        elif post.type == MessageType.VIDEO:
            msg = await bot.send_video(
                chat_id=message.from_user.id,
                video=post.video[0],
                reply_markup=post_markup(buttons=post.buttons),
            )
        elif post.type == MessageType.DOCUMENT:
            msg = await bot.send_document(
                chat_id=message.from_user.id,
                document=post.documents[0],
                reply_markup=post_markup(buttons=post.buttons),
            )
        elif post.type == MessageType.PHOTO_WITH_CAPTION:
            msg = await bot.send_photo(
                chat_id=message.from_user.id,
                photo=post.photo[0],
                caption=post.text,
                reply_markup=post_markup(buttons=post.buttons),
            )
        elif post.type == MessageType.VIDEO_WITH_CAPTION:
            msg = await bot.send_video(
                chat_id=message.from_user.id,
                video=post.video[0],
                caption=post.text,
                reply_markup=post_markup(buttons=post.buttons),
            )
        elif post.type == MessageType.DOCUMENT_WITH_CAPTION:
            msg = await bot.send_document(
                chat_id=message.from_user.id,
                document=post.documents[0],
                caption=post.text,
            )
        elif post.type == MessageType.MEDIA_GROUP:
            photo: list[InputMediaPhoto | InputMediaVideo] = [
                InputMediaPhoto(media=i) for i in post.photo
            ]
            video: list[InputMediaPhoto | InputMediaVideo] = [
                InputMediaVideo(media=i) for i in post.video
            ]
            photo.extend(video)
            msg = await bot.send_media_group(chat_id=message.from_user.id, media=photo)
        elif post.type == MessageType.MEDIA_GROUP_CAPTION:
            media: list[InputMediaPhoto | InputMediaVideo] = []
            is_first = True
            for i in post.photo:
                media.append(
                    InputMediaPhoto(media=i, caption=post.text if is_first else None)
                )
                is_first = False
            for i in post.video:
                media.append(
                    InputMediaVideo(media=i, caption=post.text if is_first else None)
                )
                is_first = False
            msg = await bot.send_media_group(chat_id=message.from_user.id, media=media)
        elif post.type == MessageType.GIF:
            msg = await bot.send_animation(
                chat_id=message.from_user.id,
                animation=post.gif[0],
                reply_markup=post_markup(buttons=post.buttons),
            )
        elif post.type == MessageType.GIF_WITH_CAPTION:
            msg = await bot.send_animation(
                chat_id=message.from_user.id,
                animation=post.gif[0],
                caption=post.text,
                reply_markup=post_markup(buttons=post.buttons),
            )
        if (
            msg is not None
            and post.type
            in [
                MessageType.TEXT,
                MessageType.PHOTO,
                MessageType.PHOTO_WITH_CAPTION,
                MessageType.VIDEO,
                MessageType.VIDEO_WITH_CAPTION,
                MessageType.DOCUMENT,
                MessageType.DOCUMENT_WITH_CAPTION,
                MessageType.GIF,
                MessageType.GIF_WITH_CAPTION,
            ]
            and len(post.buttons) > 0
        ):
            post_identificator = await repo.get_post_identificator(post_id=post_id)
            if post_identificator is not None:
                bot_acc = await bot.me()
                await bot.send_message(
                    chat_id=message.from_user.id,
                    reply_to_message_id=msg.message_id,
                    text=f"☑️ Post has been saved. your post number is: {post_identificator}"
                    f" to send it via inline mode use:\n\n <code>@{bot_acc.username} {post_identificator}</code>",
                )
        if post.type not in [MessageType.DOCUMENT, MessageType.DOCUMENT_WITH_CAPTION]:
            for i in post.documents:
                try:
                    msg = await bot.send_document(
                        chat_id=message.from_user.id, document=i
                    )
                except TelegramBadRequest as ex:
                    if ex.message == "Bad Request: failed to get HTTP URL content":
                        if type(ex.method) is SendDocument:
                            document: SendDocument = ex.method
                            await bot.send_message(
                                chat_id=message.from_user.id,
                                text=f"Ссылка на документ: {hlink(url=document.document, title='Скачать')}",
                            )
    except TelegramBadRequest as ex:
        msg = await send_error_message(ex.message, message, ex.method, bot, post)

    if post.comment is not None:
        comment_msg = await bot.send_message(
            chat_id=message.from_user.id, text=f"Комментарий: {post.comment}"
        )
        if msg is None:
            msg = comment_msg
    if msg is None:
        return None
    if isinstance(msg, Message):
        return msg.message_id
    elif isinstance(msg, MessageId):
        return msg.message_id
    elif isinstance(msg, list):
        return msg[0].message_id


async def send_inline_query(
    post: TelegramMessage, message: InlineQuery, bot: Bot, identifier: int
) -> int | None:
    msg = None
    try:
        if post.type == MessageType.TEXT:
            await bot.answer_inline_query(
                inline_query_id=message.id,
                results=[
                    InlineQueryResultArticle(
                        id=str(identifier),
                        title=f"{post.text[:20]} ...",
                        input_message_content=InputTextMessageContent(
                            message_text=post.text
                        ),
                        reply_markup=post_markup(buttons=post.buttons),
                    )
                ],
            )
        elif post.type in [MessageType.PHOTO, MessageType.PHOTO_WITH_CAPTION]:
            await bot.answer_inline_query(
                inline_query_id=message.id,
                results=[
                    InlineQueryResultPhoto(
                        id=str(identifier),
                        title="P",
                        photo_url=post.photo[0],
                        thumbnail_url=post.photo[0],
                        caption=post.text,
                        reply_markup=post_markup(buttons=post.buttons),
                    )
                ],
            )
        elif post.type in [MessageType.VIDEO, MessageType.VIDEO_WITH_CAPTION]:
            await bot.answer_inline_query(
                inline_query_id=message.id,
                results=[
                    InlineQueryResultVideo(
                        type=InlineMessageType.video,
                        id=str(identifier),
                        video_width=640,
                        video_height=360,
                        title="V",
                        mime_type="video/mp4",
                        video_url=post.video[0],
                        thumbnail_url=post.video[0],
                        caption=post.text,
                        reply_markup=post_markup(buttons=post.buttons),
                    )
                ],
            )
        elif post.type in [MessageType.DOCUMENT, MessageType.DOCUMENT_WITH_CAPTION]:
            await bot.answer_inline_query(
                inline_query_id=message.id,
                results=[
                    InlineQueryResultDocument(
                        type=InlineMessageType.document,
                        id=str(identifier),
                        title="D",
                        mime_type="application/pdf",
                        document_url=post.documents[0],
                        thumbnail_url=post.documents[0],
                        caption=post.text,
                        reply_markup=post_markup(buttons=post.buttons),
                    )
                ],
            )
        elif post.type in [MessageType.GIF, MessageType.GIF_WITH_CAPTION]:
            await bot.answer_inline_query(
                inline_query_id=message.id,
                results=[
                    InlineQueryResultGif(
                        type=InlineMessageType.gif,
                        id=str(identifier),
                        title="G",
                        gif_url=post.gif[0],
                        thumbnail_url=post.gif[0],
                        caption=post.text,
                        reply_markup=post_markup(buttons=post.buttons),
                    )
                ],
            )
    except TelegramBadRequest as ex:
        print(f"Ошибка при отправке поста в режиме inline_mode: {ex}")

    if post.comment is not None:
        await bot.send_message(
            chat_id=message.from_user.id, text=f"Комментарий: {post.comment}"
        )
    if msg is None:
        return None
    if isinstance(msg, Message):
        return msg.message_id
    elif isinstance(msg, list):
        return msg[0].message_id


@UserRouter.message(Command(commands="topic"), F.reply_to_message.forum_topic_created)
async def receive_message(message: Message, bot: FromDishka[Bot]) -> None:
    await bot.send_message(
        chat_id=message.chat.id,
        message_thread_id=message.message_thread_id,
        text=f"TopicName: {message.reply_to_message.forum_topic_created.name}\n"
        f"TopicId: <code>{message.message_thread_id}</code>\n",
    )


@UserRouter.message(CommandStart(deep_link=True))
async def command_start_deep_link(
    message: Message,
    command: CommandObject,
    bot: FromDishka[Bot],
    repo: FromDishka[UserRepository],
    cache: FromDishka[RedisCacheSystem],
    activate_attach_user: FromDishka[AttachTgUserFromAppInteractor],
    create_actor: FromDishka[CreateActorInteractor],
    reply: FromDishka[ReplyKeyboard],
    get_post: FromDishka[ReadPostInteractor],
    album_ids_provider: FromDishka[TelegramPublicChannelAlbumIdsProvider],
    config: FromDishka[CommonConfig],
    state: FSMContext,
    bot_repo: FromDishka[BotRepository],
) -> None:
    args = command.args or ""
    if is_compact_start_args(args):
        try:
            collect_payload = decode_collect_start_payload(args)
        except CollectStartPayloadUnsupportedVersion:
            await handle_collect_start_decode_error(message=message, bot=bot)
            return
        except StartPayloadMalformed:
            await handle_collect_start_decode_error(message=message, bot=bot)
            return
        user = await bot_repo.get_user_by_telegram_id(telegram_id=message.from_user.id)
        if user is None:
            await bot.send_message(
                chat_id=message.from_user.id,
                text="Свяжите Telegram с аккаунтом Blogix на сайте, затем откройте ссылку снова.",
            )
            return
        await begin_collect_createorder_from_start(
            message=message,
            state=state,
            user=user,
            payload=collect_payload,
            bot=bot,
            db_gateway=repo,
        )
        return

    payload = decode_payload(args)
    payload_json = await cache.get(payload=GetRedisData(name=payload, user_id=""))
    try:
        payload_data = DeeplinkData.model_validate_json(payload_json)
    except ValidationError:
        await bot.send_message(
            chat_id=message.from_user.id, text="Устаревшая ссылка, получите новую"
        )
        return
    if payload_data.type == DeeplinkType.post:
        try:
            response = await get_post(
                data=ReadPostDtoInput(order_id=payload_data.payload.order_id)
            )
        except PostNotFound:
            await bot.send_message(
                chat_id=message.from_user.id, text="Пост не существует для этого заказа"
            )
            return
        post_builder = PostBuilder(
            post=PostResponse(
                id=response.id,
                platform=response.platform,
                post_type=response.post_type,
                comment=response.comment,
                files=[
                    FileViewWithUrl(
                        content_type=i.content_type,
                        content=i.content,
                        name=i.name,
                        url=i.url,
                    )
                    for i in response.files
                ],
            )
        )
        try:
            post = post_builder.execute()
        except PostBuildError:
            await bot.send_message(
                chat_id=message.from_user.id, text="Ошибка в формировании поста ⛔️"
            )
            return
        await send_post(
            post=post,
            message=message,
            bot=bot,
            repo=repo,
            post_id=response.id,
            album_ids_provider=album_ids_provider,
            tz_channel_id=config.bot_project.tz_channel_id,
        )
    elif payload_data.type == DeeplinkType.attach_user:
        user = await activate_attach_user(
            data=AttachTgUserFromAppDtoInput(
                attach_id=payload_data.payload.attach_id,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
            )
        )
        if user.role in [Role.blogger, Role.advertiser]:
            await message.answer(
                text="Ваш телеграм аккаунт связан с аккаунтом BLOGIX",
                reply_markup=reply.blogger_keyboard(),
            )
        elif user.role in [Role.manager]:
            await message.answer(
                text="Ваш телеграм аккаунт связан с аккаунтом BLOGIX",
            )
    elif payload_data.type in [
        DeeplinkType.attach_customer,
        DeeplinkType.attach_publisher,
    ]:
        await create_actor(
            data=CreateActorDtoInput(
                project_id=payload_data.payload.project_id,
                subrole=payload_data.payload.subrole,
                telegram_id=message.from_user.id,
            )
        )
        if payload_data.type == DeeplinkType.attach_publisher:
            await message.answer(
                text="Пользователь связан ✅", reply_markup=reply.publisher_keyboard()
            )
    else:
        await message.answer(text="Диплинк, не найден либо аргумент не распознан ⛔️")


@UserRouter.inline_query()
async def inline_query(
    message: InlineQuery,
    bot: FromDishka[Bot],
    get_post: FromDishka[ReadPostInteractor],
    user_repository: FromDishka[UserRepository],
) -> None:
    try:
        post_identificator = int(message.query)
    except ValueError:
        return None
    order_id = await user_repository.get_order_id_by_post_identificator(
        identificator=post_identificator
    )
    if order_id is None:
        return None
    try:
        response = await get_post(data=ReadPostDtoInput(order_id=order_id))
    except PostNotFound:
        return
    post_builder = PostBuilder(
        post=PostResponse(
            id=response.id,
            platform=response.platform,
            post_type=response.post_type,
            comment=response.comment,
            files=[
                FileViewWithUrl(
                    content_type=i.content_type,
                    content=i.content,
                    name=i.name,
                    url=i.url,
                )
                for i in response.files
            ],
        )
    )
    try:
        post = post_builder.execute()
    except PostBuildError:
        await bot.send_message(
            chat_id=message.from_user.id, text="Ошибка в формировании поста ⛔️"
        )
    await send_inline_query(
        post=post, message=message, bot=bot, identifier=post_identificator
    )


@UserRouter.message(
    GetUserByTelegramId(),
    IsPostSubmission(),
)
async def verify_and_publish_post(
    message: Message,
    processor: FromDishka[VerifySubmissionProcessor],
    state: FSMContext,
    user: User,
) -> None:
    print(
        f"[verify.handler] "
        f"{json.dumps(message.model_dump(mode='python', exclude_none=True), default=str, ensure_ascii=False)}",
        flush=True,
    )
    submission = extract_post_submission(message=message)
    context = VerifyContext(
        user=user,
        telegram_id=message.from_user.id,
        chat_id=message.chat.id,
        message=message,
        state=state,
    )
    await processor.process(submission=submission, context=context)


@UserRouter.message(CommandStart())
async def command_start(
    message: Message,
    state: FSMContext,
    config: FromDishka[CommonConfig],
    bot: FromDishka[Bot],
) -> None:
    await state.clear()
    async with ClientSession() as session:
        response = await session.post(
            url=f"{config.bot.frontend_domain}/advblog/api/users/telegram-bot",
            json={
                "first_name": message.from_user.first_name,
                "username": message.from_user.username,
                "telegram_id": message.from_user.id,
            },
        )
    await message.answer(
        text=(
            "<b>Эффективные рекламные интеграции в социальных сетях</b>\n\n"
            "Blogix - рекламная биржа для размещения рекламы в Telegram, "
            "Instagram и YouTube. Эффективные инструменты для покупки и "
            "продажи рекламных размещений."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚀 Я рекламодатель",
                        web_app=WebAppInfo(
                            url=f"{config.bot.frontend_domain}/?telegram_role=advertiser"
                        ),
                    ),
                    InlineKeyboardButton(
                        text="✍️ Я блогер",
                        web_app=WebAppInfo(
                            url=f"{config.bot.frontend_domain}/?telegram_role=blogger"
                        ),
                    ),
                ]
            ]
        ),
    )
    async with ClientSession() as session:
        response = await session.post(
            url=f"{config.bot.frontend_domain}/advblog/api/users/telegram-bot",
            json={
                "first_name": message.from_user.first_name,
                "username": message.from_user.username,
                "telegram_id": message.from_user.id,
            },
        )
    await message.answer(
        text=(
            "<b>Эффективные рекламные интеграции в социальных сетях</b>\n\n"
            "Blogix - рекламная биржа для размещения рекламы в Telegram, "
            "Instagram и YouTube. Эффективные инструменты для покупки и "
            "продажи рекламных размещений."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚀 Я рекламодатель",
                        web_app=WebAppInfo(
                            url=f"{config.bot.frontend_domain}/?telegram_role=advertiser"
                        ),
                    ),
                    InlineKeyboardButton(
                        text="✍️ Я блогер",
                        web_app=WebAppInfo(
                            url=f"{config.bot.frontend_domain}/?telegram_role=blogger"
                        ),
                    ),
                ]
            ]
        ),
    )
