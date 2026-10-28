from uuid import UUID
from datetime import datetime, date, time
from typing import Optional

from advertiser_blogger.domain.read.common.entities.date_time import DatePeriod
from advertiser_blogger.domain.record.channel.entities.group_event import OrderGrTgEvent
from advertiser_blogger.domain.record.wallet.constants import WayType
from advertiser_blogger.domain.read.constants import Role
from advertiser_blogger.domain.read.constants import Language
from advertiser_blogger.domain.record.order.constants import DesireType
from advertiser_blogger.infrastructure.bot.templates.template_factory import BotTemplate

desire_text = {
    DesireType.replace_channel_request: "Замена канала",
    DesireType.replace_post_request: "Замена поста",
}

role_resource = {Role.blogger: "блогер", Role.advertiser: "рекламодатель"}
payment_method = {WayType.payme: "Payme", WayType.click: "Click"}
_POST_VERIFY_STATUS = {
    "channel_bot": "caught by bot",
    "db_scheduled": "already in DB, verified by scheduler",
    "userbot_scheduled": "no link — userbot found and attached",
}

class EnBotNotifications(BotTemplate):
    language = Language.en

    def new_order_blogger(
            self, project_name: str, channel_url: str, order_datetime: str,
            format: str, price: str, order_id: UUID,
    ) -> str:
        return (
            f"🚀 <b>Новый рекламный заказ!</b>\n\n"
            f"<b>{project_name}</b>\n"
            f"order_id: <code>{order_id}</code>\n"
            f"{channel_url}\n🕘 {order_datetime}\nФормат: {format}\n"
            f"💵 <b>{price} сум</b>"
        )
    
    def new_user_registration(self, email: str, role: Role) -> str:
        return (
            f"""
            <u>Регистрация нового пользователя:</u>\n
            "<b>Новый пользователь!</b>\n
            Аккаунт: {email}\n
            Роль: {role_resource.get(role)}"
            """
        )
    
    def create_organization(self, email: str, tin_pinfl: str) -> str:
        return (
            f"""
            <u>Добавление организации:</u>\n
            "<b>Пользователь добавил организацию!</b>\n
            Аккаунт: {email}\n
            ИНН/ПИНФЛ: {tin_pinfl}"
            """
        )
    
    def create_deposit(self, email: str, tin_pinfl: str, amount: int) -> str:
        return (
            f"""
            <u>Новая заявка на пополнение баланса перечислением:</u>\n
            "<b>Заявка на пополнение баланса!</b>\n
            Аккаунт: {email}\n
            ИНН/ПИНФЛ: {tin_pinfl}\n
            Сумма: {amount} сум"
            """
        )
    
    def create_payment_payme_click(self, email: str, way_type: WayType, amount: int) -> str:
        return (
            f"""
            <u>Пополнение баланса {payment_method.get(way_type)}:</u>\n
            "<b>Пользователь пополнил баланс!</b>\n
            Аккаунт: {email}\n
            Метод: {payment_method.get(way_type)}\n
            Сумма: {amount} сум"
            """
        )
    
    def create_withdrawal_request(self, email: str, tin_pinfl: str, amount: int) -> str:
        return (
            f"""
                <u>Заявка на вывод средств:</u>
                "<b>Новая заявка на вывод средств!</b>
                Аккаунт: {email}
                ИНН/ПИНФЛ: {tin_pinfl}
                Сумма: {amount} сум"
            """
        )
    
    def create_advance_withdrawal_request(self, email: str, tin_pinfl: str, amount: float, balance: float) -> str:
        return (
            f"<u>Авансовый вывод средств:</u>\n"
            "<b>Блогеру выдан аванс!</b>\n"
            f"Аккаунт: {email}\n"
            f"ИНН/ПИНФЛ: {tin_pinfl}\n"
            f"Сумма: {amount} сум\n"
            f"Баланс после аванса: {balance} сум\n"
            "Долг закроют следующие выполненные заказы"
        )
    
    def create_withdrawal_refund_request(self, email: str, tin_pinfl: str, amount: int) -> str:
        return (
            f"""
                <u>Заявка на возврат средств:</u>
                "<b>Новая заявка на возврат средств!</b>
                Аккаунт: {email}
                ИНН/ПИНФЛ: {tin_pinfl}
                Сумма: {amount} сум"
            """
        )
    
    def launch_advertiser_project(
            self, email: str, budget: int, orders: list[OrderGrTgEvent], project_id: UUID, project_name: str,
        ) -> str:
        orders = str()
        for count, order in enumerate(orders, start=1):
            if isinstance(order.publish_date, DatePeriod):
                publish_date = (
                    f"{datetime.strftime(order.publish_date.date_from, '%d.%m.%Y')} - "
                    f"{datetime.strftime(order.publish_date.date_to, '%d.%m.%Y')}"
                )
            elif isinstance(order.publish_date, date):
                publish_date = f"{datetime.strftime(order.publish_date, '%d.%m.%Y')}"
            else:
                publish_date = ""
            publish_time = (
                f"{time.strftime(order.publish_time.time_from, '%H:%M')} - "
                f"{time.strftime(order.publish_time.time_to, '%H:%M')}"
            )
            prefix = f"{order.order_marker} " if order.order_marker else ""
            orders += f"{count}. {prefix}{order.channel_url} | {publish_date} | {publish_time}\n"

        return (
            f"""
                <u>Запуск РК:</u>
                "<b>Запущена новая рекламная кампания!</b>"
                f"project_id: <code>{project_id}</code>\n"
                f"Название проекта: <b>{project_name}</b>\n"
                Аккаунт: {email}
                Бюджет РК: {budget} сум
                Каналы: \n{orders}
            """
        )
    
    def create_channel_request(self, email: str, channel_url: str) -> str:
        return (
            f"""
                <u>Заявка на добавление канала:</u>
                "<b>Новая заявка на добавление канала!</b>"
                Аккаунт: {email}
                Канал: {channel_url}"
            """
        )

    def remoderation_channel_request(self, email: str, channel_url: str) -> str:
        return (
            f"""
                <u>Channel remoderation request:</u>
                <b>New channel remoderation request!</b>
                Account: {email}
                Channel: {channel_url}
            """
        )

    def must_publish_post_button(self) -> str:
        return "🌠 Advertising post"

    def telegram_publish_reminder_before_1h(self, channel_url: str, order_datetime: str, format: str) -> str:
        return (
            f"⏰ <b>Publishing starts in 1 hour!</b>\n\n"
            f"Channel: {channel_url}\n"
            f"Time: 🕘 {order_datetime}\n"
            f"Format: {format}"
        )

    def telegram_publish_reminder_at_start(self, channel_url: str, order_datetime: str, format: str) -> str:
        return (
            f"🚀 <b>Publishing time has started!</b>\n\n"
            f"Channel: {channel_url}\n"
            f"Time: 🕘 {order_datetime}\n"
            f"Format: {format}"
        )

    def telegram_publish_reminder_before_45min(self, channel_url: str, order_datetime: str, format: str) -> str:
        return (
            f"⚠️ <b>45 minutes left until publishing ends!</b>\n\n"
            f"Channel: {channel_url}\n"
            f"Time: 🕘 {order_datetime}\n"
            f"Format: {format}"
        )

    def order_blogger_rejected(
            self, project_name: str, channel_url: str, order_datetime: str, reason: Optional[str],
    ) -> str:
        text = (
            f"🚫 Blogger rejected the order\n\n"
            f"{project_name}\n"
            f"{channel_url}\n"
            f"🕘 {order_datetime}"
        )
        if reason:
            text += f"\n\n👉 Reason: {reason}"
        return text

    def post_changed_to_blogger(self, project_name: str, channel_url: str, order_datetime: str) -> str:
        return (
            f"📝 <b>The advertising post has been changed</b>\n\n"
            f"{project_name}\n"
            f"{channel_url}\n"
            f"🕘 {order_datetime}\n\n"
            f"Please publish the new version of the post — the old one is no longer valid. Tap the button below to get the post."
        )

    def new_chat_message(self, chat_title: str, message: Optional[str]) -> str:
        message = message if message is not None else "📎 Attachment"
        return (
            f"💬 <b>New chat message</b>\n\n"
            f"{chat_title}\n\n"
            f"<blockquote>{message}</blockquote>\n\n"
            f"You can reply on the Blogix platform."
        )

    def advertiser_project_report_ready(self, project_name: str) -> str:
        return (
            f"📊 Campaign report is ready!\n\n"
            f"Campaign: <b>{project_name}</b>\n\n"
            f"The report has been successfully created and is available in the \"My Projects\" section."
        )

    def order_blogger_rejected_group(
            self, order_id: UUID, project_name: str, channel_url: str, order_datetime: str,
            reason: Optional[str],
    ) -> str:
        text = self.order_blogger_rejected(
            project_name=project_name, channel_url=channel_url,
            order_datetime=order_datetime, reason=reason,
        )
        return (
            f"{text}\n\n"
            f"Order_id: <code>{order_id}</code>\n\n"
            f"@AbddSsh, @corenavigator, @blogix_uz, @blogiix_uz\n"
            f"KTO U APPARAT ATMEN ZAKAZ❗️"
        )

    def post_not_found(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
    ) -> str:
        return (
            f"Post not found\n"
            f"Channel: {channel_url}\n"
            f"Order_id: <code>{order_id}</code>\n"
            f"Date: {publish_date}\n"
            f"Time: {publish_time}"
        )

    def post_deleted(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            format_name: str, blogix_published: str, social_published: str,
    ) -> str:
        return (
            f"Post deleted❗️❗️❗️\n"
            f"Channel: {channel_url}\n"
            f"Order_id: <code>{order_id}</code>\n"
            f"Date: {publish_date}\n"
            f"Time: {publish_time}\n"
            f"Format: {format_name}\n"
            f"Placed in Blogix: {blogix_published}\n"
            f"Placed in social network: {social_published}\n"
            f"@AbddSsh, @corenavigator, @ifyouareswift, @blogix_uz, @blogiix_uz"
        )

    def post_verify_ok(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            score: float, post_url: str, source: str,
    ) -> str:
        return (
            f"Post matches brief ({score:.0f}%)\n"
            f"Status: {_POST_VERIFY_STATUS[source]}\n"
            f"Channel: {channel_url}\n"
            f"Post: {post_url}\n"
            f"Order_id: <code>{order_id}</code>\n"
            f"Date: {publish_date}\n"
            f"Time: {publish_time}"
        )

    def post_verify_mismatch(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            score: float, post_url: str,
    ) -> str:
        return (
            f"Post does not match brief ({score:.0f}%)\n"
            f"Channel: {channel_url}\n"
            f"Post: {post_url}\n"
            f"Order_id: <code>{order_id}</code>\n"
            f"Date: {publish_date}\n"
            f"Time: {publish_time}"
        )

    def didox_search_failed(self, name: str, doc_type: str, partner_tin: str) -> str:
        return (
            f"⛔️ Didox document search failed, document was not sent\n"
            f"Number: <code>{name}</code>\n"
            f"Type: {doc_type}\n"
            f"Partner: <code>{partner_tin}</code>"
        )

    def didox_duplicate_documents(
            self, name: str, doc_type: str, partner_tin: str, doc_ids: list[str],
    ) -> str:
        doc_lines = "\n".join(f"<code>{doc_id}</code>" for doc_id in doc_ids)
        return (
            f"⚠️ Duplicate documents in Didox\n"
            f"Number: <code>{name}</code>\n"
            f"Type: {doc_type}\n"
            f"Partner: <code>{partner_tin}</code>\n"
            f"Documents:\n{doc_lines}"
        )