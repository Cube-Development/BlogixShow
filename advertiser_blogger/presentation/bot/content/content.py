from datetime import datetime, time

from advertiser_blogger.domain.read.common.entities.date_time import DatePeriod
from advertiser_blogger.presentation.bot.models.publisher import ShowOrderModel


class Content:
    def show_order(self, order: ShowOrderModel) -> str:
        time_from = time.strftime(order.must_publish_time.time_from, "%H:%M")
        time_to = time.strftime(order.must_publish_time.time_to, "%H:%M")
        if order.published is not None:
            publish_datetime = datetime.strftime(order.published, "%d.%m.%Y %H:%M")
        elif isinstance(order.must_publish_date, DatePeriod):
            date_from = datetime.strftime(order.must_publish_date.date_from, "%d.%m.%Y")
            date_to = datetime.strftime(order.must_publish_date.date_to, "%d.%m.%Y")
            publish_datetime = f"{date_from} - {date_to} | {time_from} - {time_to}"
        else:
            must_publish_date = datetime.strftime(order.must_publish_date, "%d.%m.%Y")
            publish_datetime = f"{must_publish_date} | {time_from} - {time_to}"
        string = ""
        string += f"<b>Название канала</b>: {order.name}\n"
        string += f"<b>Ссылка на канал</b>: {order.url}\n"
        string += f"<b>Формат размещения</b>: {order.format}\n"
        string += f"<b>Дата и время создания/размещения</b>: {publish_datetime}"
        return string
