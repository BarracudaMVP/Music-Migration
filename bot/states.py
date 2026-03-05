from aiogram.fsm.state import State, StatesGroup


class AuthFlow(StatesGroup):
    waiting_yandex_token     = State()   # ждём OAuth-код от Яндекса
    waiting_soundcloud_token = State()   # ждём токен из куки SC
    confirming               = State()   # показываем статистику, ждём подтверждения


class MigrationFlow(StatesGroup):
    in_progress = State()
