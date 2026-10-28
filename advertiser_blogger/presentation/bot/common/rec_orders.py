from aiogram.fsm.context import FSMContext

from advertiser_blogger.application.read.read_orders_tariff_approval.dto import ReadOrderTariff
from advertiser_blogger.presentation.bot.models.publisher import ShowOrderModel, PublisherProject


async def record_orders(orders: list[ReadOrderTariff], state: FSMContext) -> None:
    orders_to_rec = []
    for order in orders:
        orders_to_rec.append(
            ShowOrderModel(
                id=order.id, name=order.name, url=order.url, format=order.format.big,
                must_publish_date=order.publish_date, must_publish_time=order.publish_time,
                published=order.published, published_post=order.post_url,
                post_url=order.post_url, status=order.api_status,
            )
        )
    project = PublisherProject(orders=orders_to_rec)
    await state.update_data(publisher_project=project.model_dump_json())
