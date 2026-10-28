from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


class ReplyKeyboard:
    def publisher_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [KeyboardButton(text="Активные проекты")],
                [KeyboardButton(text="Завершенные проекты")],
                [KeyboardButton(text="Отправить ссылку на пост")],
                [KeyboardButton(text="Создать РК")],
            ]
        )

    def blogger_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [KeyboardButton(text="🚀 Активные проекты")],
                [KeyboardButton(text="☑️ Завершенные проекты")],
                [KeyboardButton(text="📑 Скачать эксель отчет")],
                [KeyboardButton(text="Создать РК")],
            ]
        )
