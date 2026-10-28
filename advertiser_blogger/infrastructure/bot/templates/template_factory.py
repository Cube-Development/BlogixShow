from uuid import UUID
from abc import ABC, abstractmethod
from typing import Optional

from advertiser_blogger.domain.record.channel.entities.group_event import OrderGrTgEvent
from advertiser_blogger.domain.record.wallet.constants import WayType
from advertiser_blogger.domain.read.constants import Role
from advertiser_blogger.domain.read.constants import Language


class BotTemplate(ABC):
    language: Language

    @abstractmethod
    def new_order_blogger(
            self, project_name: str, channel_url: str, order_datetime: str,
            format: str, price: str, order_id: UUID,
    ) -> str: pass

    @abstractmethod
    def new_user_registration(self, email: str, role: Role) -> str: pass

    @abstractmethod
    def create_organization(self, email: str, tin_pinfl: str) -> str: pass

    @abstractmethod
    def create_deposit(self, email: str, tin_pinfl: str, amount: int) -> str: pass

    @abstractmethod
    def create_payment_payme_click(self, email: str, way_type: WayType, amount: int) -> str: pass

    @abstractmethod
    def create_withdrawal_request(self, email: str, tin_pinfl: str, amount: int) -> str: pass

    @abstractmethod
    def create_advance_withdrawal_request(self, email: str, tin_pinfl: str, amount: float, balance: float) -> str: pass

    @abstractmethod
    def create_withdrawal_refund_request(self, email: str, tin_pinfl: str, amount: int) -> str: pass

    @abstractmethod
    def launch_advertiser_project(self, email: str, budget: int, channels: list[OrderGrTgEvent], project_id: UUID, project_name: str,) -> str: pass

    @abstractmethod
    def create_channel_request(self, email: str, channel_url: str) -> str: pass

    @abstractmethod
    def remoderation_channel_request(self, email: str, channel_url: str) -> str: pass

    @abstractmethod
    def must_publish_post_button(self) -> str: pass

    @abstractmethod
    def telegram_publish_reminder_before_1h(self, channel_url: str, order_datetime: str, format: str) -> str: pass

    @abstractmethod
    def telegram_publish_reminder_at_start(self, channel_url: str, order_datetime: str, format: str) -> str: pass

    @abstractmethod
    def telegram_publish_reminder_before_45min(self, channel_url: str, order_datetime: str, format: str) -> str: pass

    @abstractmethod
    def order_blogger_rejected(
            self, project_name: str, channel_url: str, order_datetime: str, reason: Optional[str],
    ) -> str: pass

    @abstractmethod
    def advertiser_project_report_ready(self, project_name: str) -> str: pass

    @abstractmethod
    def new_chat_message(self, chat_title: str, message: Optional[str]) -> str: pass

    @abstractmethod
    def post_changed_to_blogger(self, project_name: str, channel_url: str, order_datetime: str) -> str: pass

    @abstractmethod
    def order_blogger_rejected_group(
            self, order_id: UUID, project_name: str, channel_url: str, order_datetime: str,
            reason: Optional[str],
    ) -> str: pass

    @abstractmethod
    def post_not_found(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
    ) -> str: pass

    @abstractmethod
    def post_deleted(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            format_name: str, blogix_published: str, social_published: str,
    ) -> str: pass

    @abstractmethod
    def post_verify_ok(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            score: float, post_url: str, source: str,
    ) -> str: pass

    @abstractmethod
    def post_verify_mismatch(
            self, order_id: UUID, channel_url: str, publish_date: str, publish_time: str,
            score: float, post_url: str,
    ) -> str: pass

    @abstractmethod
    def didox_search_failed(self, name: str, doc_type: str, partner_tin: str) -> str: pass

    @abstractmethod
    def didox_duplicate_documents(
            self, name: str, doc_type: str, partner_tin: str, doc_ids: list[str],
    ) -> str: pass


class BotTemplateFactory:
    def __init__(self, templates: list[BotTemplate]):
        self.templates = templates

    def __call__(self, language: Language = Language.ru) -> BotTemplate:
        for template in self.templates:
            if template.language == language:
                return template
        else:
            return self.templates[0]
