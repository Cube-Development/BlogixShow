from datetime import date, time, datetime

from advertiser_blogger.domain.read.common.entities.date_time import DatePeriod, TimePeriod


def convert_order_date_to_string(order_date: DatePeriod | date, order_time: TimePeriod) -> str:
    if isinstance(order_date, DatePeriod):
        publish_date = (
            f"{datetime.strftime(order_date.date_from, '%d.%m.%Y')} - "
            f"{datetime.strftime(order_date.date_to, '%d.%m.%Y')}"
        )
    elif isinstance(order_date, date):
        publish_date = f"{datetime.strftime(order_date, '%d.%m.%Y')}"
    else:
        publish_date = ""
    publish_time = (
        f"{time.strftime(order_time.time_from, '%H:%M')} - "
        f"{time.strftime(order_time.time_to, '%H:%M')}"
    )
    return f"{publish_date} | {publish_time}"


def format_price(obj: int | float) -> str:
    return "{0:,}".format(int(obj)).replace(",", " ")
