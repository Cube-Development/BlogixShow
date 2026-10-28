from advertiser_blogger.application.interactors_bot.verify_and_publish_post.dto import (
    LowSimilarity, NoOrders, PublishFailed, Success, TextUnavailable, VerifyResult,
)
from advertiser_blogger.domain.common.text_similarity import POST_SIMILARITY_TOKEN_SET_THRESHOLD
from advertiser_blogger.presentation.bot.common.messages import PUBLISH_FAILURE_MESSAGES

VERIFY_STARTED_MESSAGE = (
    "🔍 Tekshiruv boshlandi\n"
    "Проверка начата\n\n"
    "📎 Post linki yoki kanaldan forward yuboring\n"
    "Отправьте ссылку на пост или forward из канала\n\n"
    "❗️ Repost bo'lsa — kanaldan link yuboring (t.me/.../...)\n"
    "Если repost — отправьте ссылку из канала (t.me/.../...)"
)

NO_ORDERS_MESSAGE = (
    "Не нашли заказ на этот канал на сегодня.\n\n"
    "Убедитесь, что пост опубликован именно в этом канале как нативный пост "
    "(не forward из другого канала).\n\n"
    "Если публикация была через пересылку сообщения — отправьте ссылку на пост "
    "в вашем канале (t.me/канал/id)."
)

NO_ORDERS_SHORT_MESSAGE = (
    "⛔️ Buyurtma topilmadi\n"
    "Заказ не найден"
)

ALBUM_NO_CAPTION_MESSAGE = (
    "❗️ Albomga matn qo'shing\n"
    "Добавьте текст к альбому (caption) — reklama matnini tekshirish uchun kerak"
)


def format_low_similarity_in_project_message(score: float) -> str:
    return (
        f"❌ Matn mos kelmadi ({score:.0f}%, kerak ≥{POST_SIMILARITY_TOKEN_SET_THRESHOLD:.0f}%)\n"
        f"Текст не совпадает с ТЗ ({score:.0f}%, нужно ≥{POST_SIMILARITY_TOKEN_SET_THRESHOLD:.0f}%)"
    )


def format_verify_result(result: VerifyResult) -> str:
    match result:
        case Success(score=score):
            return f"Пост опубликован ✅ (совпадение: {score:.0f}%)"
        case LowSimilarity(best_score=score):
            return (
                f"Текст не совпадает с ТЗ ({score:.0f}%, "
                f"нужно ≥{POST_SIMILARITY_TOKEN_SET_THRESHOLD:.0f}%)"
            )
        case NoOrders():
            return NO_ORDERS_MESSAGE
        case TextUnavailable():
            return "Не удалось получить текст по ссылке. Отправьте форвард поста"
        case PublishFailed(reason=reason):
            if reason is None:
                return "Не удалось разместить пост"
            return PUBLISH_FAILURE_MESSAGES.get(reason, "Не удалось разместить пост")
        case _:
            return "Не удалось обработать сообщение"
