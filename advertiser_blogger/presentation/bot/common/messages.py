from advertiser_blogger.application.interactors_bot.publish_post_broadcast.dto import PublishPostFailureReason

PUBLISH_FAILURE_MESSAGES: dict[PublishPostFailureReason, str] = {
    PublishPostFailureReason.order_not_found: "Заказ не найден",
    PublishPostFailureReason.channel_not_found: "Канал не найден",
    PublishPostFailureReason.access_denied: "Нет доступа к этому заказу",
    PublishPostFailureReason.invalid_status: "Заказ не готов к публикации",
    PublishPostFailureReason.already_published: "Пост уже размещён",
    PublishPostFailureReason.order_expired: "Срок размещения истёк",
    PublishPostFailureReason.date_out_of_interval: "Текущая дата не входит в допустимый интервал",
    PublishPostFailureReason.date_or_time_not_setup: "Не настроена дата или время публикации",
    PublishPostFailureReason.outside_time_window: "Сейчас не время публикации (отправьте ссылку в указанном окне)",
    PublishPostFailureReason.post_not_found: "Не удалось получить информацию о посте по ссылке",
}
