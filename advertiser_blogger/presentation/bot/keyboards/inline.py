import calendar
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from advertiser_blogger.application.read.project_agency.dto import ProjectAgencyDto
from advertiser_blogger.application.read.read_orders_tariff_approval.dto import ReadOrderTariff
from advertiser_blogger.domain.read.order.entities.blogger import BloggerProjectView
from advertiser_blogger.domain.record.order.constants import OrderStatus

BP_DAY_TODAY = "bp_day:today"
BP_DAY_TOMORROW = "bp_day:tomorrow"
BP_DAY_PICK = "bp_day:pick"
BP_CAL_BACK = "bp_cal:back"
BP_CAL_NAV_PREFIX = "bp_cal:nav:"
BP_CAL_DAY_PREFIX = "bp_cal:day:"
BP_CAL_IGNORE = "bp_cal:ignore"
BP_PROJ_PREFIX = "bp_proj:"

_RU_MONTHS = (
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


class InlineKeyboard:
    def show_projects(self, projects: list[ProjectAgencyDto]) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i.project_name, callback_data=str(i.id),
                    )
                ] for i in projects
            ]
        )

    def show_orders(self, orders: list[ReadOrderTariff]) -> InlineKeyboardMarkup:
        inline_keyboard = []
        for i in orders:
            if i.api_status in [OrderStatus.canceled, OrderStatus.rejected]:
                text = f"❌ {i.name}"
            elif i.api_status in [OrderStatus.completed]:
                text = f"✅ {i.name}"
            elif i.api_status == OrderStatus.frozen:
                text = f"❄️ {i.name}"
            else:
                text = f"{i.name}"
            inline_keyboard.append(
                [
                    InlineKeyboardButton(
                        text=text, callback_data=str(i.id),
                    )
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    def publisher_order(
            self, deeplink_post_url: str, is_active: bool, order_id: UUID, published_post: Optional[str],
    ) -> InlineKeyboardMarkup:
        inline_keyboard = [
            [InlineKeyboardButton(text="Посмотреть пост", url=deeplink_post_url)],
        ]
        if is_active:
            inline_keyboard.append(
                [InlineKeyboardButton(text="Отправить ссылку на пост", callback_data=f"s_{order_id}")]
            )
            inline_keyboard.append(
                [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"c_{order_id}")]
            )
        else:
            inline_keyboard.append(
                [InlineKeyboardButton(text="Посмотреть пост в канале", url=published_post)]
            )
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    def show_blogger_projects(
            self,
            projects: list[BloggerProjectView],
            selected_date: date,
            today: date,
    ) -> InlineKeyboardMarkup:
        tomorrow = today + timedelta(days=1)
        if selected_date == today:
            today_label, tomorrow_label, date_label = "• Сегодня", "Завтра", "Дата"
        elif selected_date == tomorrow:
            today_label, tomorrow_label, date_label = "Сегодня", "• Завтра", "Дата"
        else:
            today_label, tomorrow_label = "Сегодня", "Завтра"
            date_label = f"• {selected_date.strftime('%d.%m')}"
        buttons = [
            [
                InlineKeyboardButton(text=today_label, callback_data=BP_DAY_TODAY),
                InlineKeyboardButton(text=tomorrow_label, callback_data=BP_DAY_TOMORROW),
                InlineKeyboardButton(text=date_label, callback_data=BP_DAY_PICK),
            ]
        ]
        for i in projects:
            if i.completed:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=f"✅ {i.project_name}",
                            callback_data=f"{BP_PROJ_PREFIX}{i.id}",
                        )
                    ]
                )
            else:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=f"{i.project_name}",
                            callback_data=f"{BP_PROJ_PREFIX}{i.id}",
                        )
                    ]
                )
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def blogger_date_calendar(self, year: int, month: int) -> InlineKeyboardMarkup:
        month_title = f"{_RU_MONTHS[month]} {year}"
        rows: list[list[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text=month_title, callback_data=BP_CAL_IGNORE)],
            [
                InlineKeyboardButton(text=day, callback_data=BP_CAL_IGNORE)
                for day in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
            ],
        ]
        for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(text=" ", callback_data=BP_CAL_IGNORE))
                else:
                    day_date = date(year, month, day)
                    row.append(
                        InlineKeyboardButton(
                            text=str(day),
                            callback_data=f"{BP_CAL_DAY_PREFIX}{day_date.isoformat()}",
                        )
                    )
            rows.append(row)
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1
        rows.append(
            [
                InlineKeyboardButton(
                    text="‹",
                    callback_data=f"{BP_CAL_NAV_PREFIX}{prev_year:04d}-{prev_month:02d}",
                ),
                InlineKeyboardButton(text="Назад", callback_data=BP_CAL_BACK),
                InlineKeyboardButton(
                    text="›",
                    callback_data=f"{BP_CAL_NAV_PREFIX}{next_year:04d}-{next_month:02d}",
                ),
            ]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def project_create_entry(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data="pc_cancel")],
            ]
        )

    def project_create_mode_choice(
            self,
            *,
            copy_text: str,
            forward_text: str,
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=copy_text, callback_data="pc_mode_copy")],
                [InlineKeyboardButton(text=forward_text, callback_data="pc_mode_forward")],
                [InlineKeyboardButton(text="Отмена", callback_data="pc_cancel")],
            ]
        )

    def project_create_orphan_leave_empty(self, *, button_text: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=button_text, callback_data="pc_orphan_leave_empty")],
                [InlineKeyboardButton(text="Отмена", callback_data="pc_cancel")],
            ]
        )

    def project_create_channel_mode_choice(
            self,
            *,
            to_above_text: str,
            own_creative_text: str,
            leave_empty_text: str,
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=to_above_text, callback_data="pc_to_above")],
                [InlineKeyboardButton(text=own_creative_text, callback_data="pc_batch_creative")],
                [InlineKeyboardButton(text=leave_empty_text, callback_data="pc_channel_leave_empty")],
                [InlineKeyboardButton(text="Отмена", callback_data="pc_cancel")],
            ]
        )

    def project_create_preview(
            self,
            channel_count: int,
            *,
            page: int = 1,
            confirm_enabled: bool = True,
            page_size: int = 10,
    ) -> InlineKeyboardMarkup:
        total_pages = max(1, (channel_count + page_size - 1) // page_size) if channel_count else 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = min(start + page_size, channel_count)

        rows: list[list[InlineKeyboardButton]] = []
        channel_row: list[InlineKeyboardButton] = []
        for i in range(start + 1, end + 1):
            channel_row.append(InlineKeyboardButton(text=str(i), callback_data=f"pc_ch:{i}"))
            if len(channel_row) == 5:
                rows.append(channel_row)
                channel_row = []
        if channel_row:
            rows.append(channel_row)

        if total_pages > 1:
            prev_page = page - 1 if page > 1 else total_pages
            next_page = page + 1 if page < total_pages else 1
            rows.append([
                InlineKeyboardButton(text="‹", callback_data=f"pc_page:{prev_page}"),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="pc_page_noop"),
                InlineKeyboardButton(text="›", callback_data=f"pc_page:{next_page}"),
            ])

        if confirm_enabled:
            rows.append(
                [InlineKeyboardButton(text="Подтвердить сохранение", callback_data="pc_confirm")]
            )
        rows.append(
            [InlineKeyboardButton(text="Отмена", callback_data="pc_cancel")]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def project_create_channel_menu(self, channel_index: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Показать пост",
                        callback_data=f"pc_show_post:{channel_index}",
                    ),
                    InlineKeyboardButton(
                        text="Заменить пост",
                        callback_data=f"pc_replace_post:{channel_index}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Сброс даты/времени",
                        callback_data=f"pc_reset_time:{channel_index}",
                    ),
                    InlineKeyboardButton(
                        text="Заменить дату/время",
                        callback_data=f"pc_edit_time:{channel_index}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Сброс коммент",
                        callback_data=f"pc_reset_comment:{channel_index}",
                    ),
                    InlineKeyboardButton(
                        text="Заменить коммент",
                        callback_data=f"pc_edit_comment:{channel_index}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Удалить канал",
                        callback_data=f"pc_delete:{channel_index}",
                    ),
                    InlineKeyboardButton(
                        text="Заменить канал",
                        callback_data=f"pc_replace:{channel_index}",
                    ),
                ],
                [InlineKeyboardButton(text="Назад", callback_data="pc_back")],
            ]
        )

    def project_create_back_to_channel(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Назад", callback_data="pc_back_channel")],
            ]
        )

    def project_create_saved(self, project_url: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть проект", url=project_url)],
            ]
        )

    def collect_createorder_accept(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Принять", callback_data="cco_accept"),
                    InlineKeyboardButton(text="Заменить пост", callback_data="cco_replace"),
                ],
                [InlineKeyboardButton(text="Отмена", callback_data="cco_cancel")],
            ]
        )

    def collect_createorder_cancel(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data="cco_cancel")],
            ]
        )

    def collect_createorder_success(self, project_url: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Продолжить на сайте", url=project_url)],
            ]
        )
