from aiogram.fsm.state import State, StatesGroup


class AuthFlow(StatesGroup):
    selecting_from           = State()   # выбор сервиса-источника
    selecting_to             = State()   # выбор сервиса-назначения
    waiting_yandex_token     = State()   # ждём OAuth-код от Яндекса
    waiting_soundcloud_token = State()   # ждём токен из куки SC
    confirming               = State()   # показываем статистику, ждём выбора режима
    selecting_limit          = State()   # выбор лимита треков


class MigrationFlow(StatesGroup):
    in_progress = State()
