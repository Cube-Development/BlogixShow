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
    "channel_bot": "bot ushladi",
    "db_scheduled": "DBda bor edi, scheduler tekshirdi",
    "userbot_scheduled": "havola yoq edi — userbot topib yozdi",
}

class UzBotNotifications(BotTemplate):
    language = Language.uz

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
                <u>Kanalni qayta moderatsiyaga yuborish so'rovi:</u>
                <b>Kanalni qayta moderatsiyaga yuborish bo'yicha yangi so'rov!</b>
                Akkaunt: {email}
                Kanal: {channel_url}
            """
        )

    def must_publish_post_button(self) -> str:
        return "🌠 Reklama posti"

    def telegram_publish_reminder_before_1h(self, channel_url: str, order_datetime: str, format: str) -> str:
        return (
            f"⏰ <b>Nashr vaqti 1 soatdan keyin boshlanadi!</b>\n\n"
            f"Kanal: {channel_url}\n"
            f"Vaqt: 🕘 {order_datetime}\n"
            f"Format: {format}"
        )

    def telegram_publish_reminder_at_start(self, channel_url: str, order_datetime: str, format: str) -> str:
        return (
            f"🚀 <b>Nashr vaqti boshlandi!</b>\n\n"
            f"Kanal: {channel_url}\n"
            f"Vaqt: 🕘 {order_datetime}\n"
            f"Format: {format}"
        )

    def telegram_publish_reminder_before_45min(self, channel_url: str, order_datetime: str, format: str) -> str:
        return (
            f"⚠️ <b>Nashr vaqti tugashiga 45 daqiqa qoldi!</b>\n\n"
            f"Kanal: {channel_url}\n"
            f"Vaqt: 🕘 {order_datetime}\n"
            f"Format: {format}"
        )

    def order_blogger_rejected(
            self, project_name: str, channel_url: str, order_datetime: str, reason: Optional[str],
    ) -> str:
        text = (
            f"🚫 Bloger buyurtmani rad etdi\n\n"
            f"{project_name}\n"
            f"{channel_url}\n"
            f"🕘 {order_datetime}"
        )
        if reason:
            text += f"\n\n👉 Sabab: {reason}"
        return text

    def post_changed_to_blogger(self, project_name: str, channel_url: str, order_datetime: str) -> str:
        return (
            f"📝 <b>Reklama posti oʻzgartirildi</b>\n\n"
            f"{project_name}\n"
            f"{channel_url}\n"
            f"🕘 {order_datetime}\n\n"
            f"Iltimos, postning yangi versiyasini joylang — eskisi endi amal qilmaydi. Postni olish uchun quyidagi tugmani bosing."
        )

    def new_chat_message(self, chat_title: str, message: Optional[str]) -> str:
        message = message if message is not None else "📎 Ilova"
        return (
            f"💬 <b>Chatda yangi xabar</b>\n\n"
            f"{chat_title}\n\n"
            f"<blockquote>{message}</blockquote>\n\n"
            f"Javob berish uchun Blogix platformasiga o‘ting."
        )

    def advertiser_project_report_ready(self, project_name: str) -> str:
        return (
            f"📊 Kampaniya hisoboti tayyor!\n\n"
            f"Kampaniya: <b>{project_name}</b>\n\n"
            f"Hisobot muvaffaqiyatli yaratildi va \"Mening loyihalarim\" bo‘limida mavjud."
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
            f"Buyurtma_id: <code>{order_id}</code>\n\n"
            f"@AbddSsh, @corenavigator, @blogix_uz, @blogiix_uz\n"
            f"KTO U APPARAT ATMEN ZAKAZ❗️"
        )

    def post_not_found(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
    ) -> str:
        return (
            f"Post topilmadi\n"
            f"Kanal: {channel_url}\n"
            f"Buyurtma_id: <code>{order_id}</code>\n"
            f"Sana: {publish_date}\n"
            f"Vaqt: {publish_time}"
        )

    def post_deleted(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            format_name: str, blogix_published: str, social_published: str,
    ) -> str:
        return (
            f"Post O'CHIRILGAN❗️❗️❗️\n"
            f"Kanal: {channel_url}\n"
            f"Buyurtma_id: <code>{order_id}</code>\n"
            f"Sana: {publish_date}\n"
            f"Vaqt: {publish_time}\n"
            f"Format: {format_name}\n"
            f"Blogixga joylangan: {blogix_published}\n"
            f"Ijtimoiy tarmoqqa joylangan: {social_published}\n"
            f"@AbddSsh, @corenavigator, @ifyouareswift, @blogix_uz, @blogiix_uz"
        )

    def post_verify_ok(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            score: float, post_url: str, source: str,
    ) -> str:
        return (
            f"Post TZ bilan mos ({score:.0f}%)\n"
            f"Holat: {_POST_VERIFY_STATUS[source]}\n"
            f"Kanal: {channel_url}\n"
            f"Post: {post_url}\n"
            f"Buyurtma_id: <code>{order_id}</code>\n"
            f"Sana: {publish_date}\n"
            f"Vaqt: {publish_time}"
        )

    def post_verify_mismatch(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            score: float, post_url: str,
    ) -> str:
        return (
            f"Post TZ bilan mos emas ({score:.0f}%)\n"
            f"Kanal: {channel_url}\n"
            f"Post: {post_url}\n"
            f"Buyurtma_id: <code>{order_id}</code>\n"
            f"Sana: {publish_date}\n"
            f"Vaqt: {publish_time}"
        )

    def didox_search_failed(self, name: str, doc_type: str, partner_tin: str) -> str:
        return (
            f"⛔️ Didox hujjat qidiruviga javob bermadi, hujjat yuborilmadi\n"
            f"Raqam: <code>{name}</code>\n"
            f"Turi: {doc_type}\n"
            f"Kontragent: <code>{partner_tin}</code>"
        )

    def didox_duplicate_documents(
            self, name: str, doc_type: str, partner_tin: str, doc_ids: list[str],
    ) -> str:
        doc_lines = "\n".join(f"<code>{doc_id}</code>" for doc_id in doc_ids)
        return (
            f"⚠️ Didoxda takroriy hujjatlar\n"
            f"Raqam: <code>{name}</code>\n"
            f"Turi: {doc_type}\n"
            f"Kontragent: <code>{partner_tin}</code>\n"
            f"Hujjatlar:\n{doc_lines}"
        )