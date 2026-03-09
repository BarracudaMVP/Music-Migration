"""
Internationalization — EN/RU string catalog.
Usage:
    from core.i18n import t, detect_lang_web, detect_lang_tg
    text = t("welcome_title", lang="en")
"""
from __future__ import annotations

_S: dict[str, dict[str, str]] = {

    # ------------------------------------------------------------------ #
    # Navigation / base
    # ------------------------------------------------------------------ #
    "nav_home":    {"ru": "Главная",  "en": "Home"},
    "nav_history": {"ru": "История",  "en": "History"},
    "nav_import":  {"ru": "Импорт",   "en": "Import"},
    "nav_export":  {"ru": "Экспорт",  "en": "Export"},
    "nav_account": {"ru": "Аккаунт",  "en": "Account"},
    "nav_logout":  {"ru": "Выйти",    "en": "Log out"},

    # ------------------------------------------------------------------ #
    # Index
    # ------------------------------------------------------------------ #
    "index_title":       {"ru": "Перенос музыки",                          "en": "Music transfer"},
    "index_subtitle":    {"ru": "Переноси треки и плейлисты между сервисами.", "en": "Move tracks and playlists between streaming services."},
    "index_from":        {"ru": "Откуда",                                  "en": "From"},
    "index_to":          {"ru": "Куда",                                    "en": "To"},
    "index_what":        {"ru": "Что переносить",                          "en": "What to transfer"},
    "index_mode_tracks": {"ru": "Только треки",                            "en": "Tracks only"},
    "index_mode_full":   {"ru": "Треки + плейлисты",                       "en": "Tracks + playlists"},
    "index_start_btn":   {"ru": "Начать перенос",                          "en": "Start transfer"},
    "index_not_authed":  {"ru": "Войдите, чтобы начать перенос",           "en": "Sign in to start transferring"},
    "index_login_btn":   {"ru": "Войти",                                   "en": "Sign in"},
    "index_import_hint": {"ru": "Или загрузи файл со списком треков.",      "en": "Or upload a file with your track list."},
    "index_no_routes":   {"ru": "Нет доступных направлений для переноса.", "en": "No transfer directions available."},
    "index_track_limit": {"ru": "Лимит треков",       "en": "Track limit"},
    "index_limit_all":   {"ru": "Все треки",           "en": "All tracks"},
    "index_limit_first": {"ru": "Первые {n}",          "en": "First {n}"},

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    "auth_title":          {"ru": "Авторизация",                           "en": "Connect accounts"},
    "auth_subtitle":       {"ru": "Подключи сервисы, чтобы начать перенос.", "en": "Connect your services to start transferring."},
    "auth_step1_title":    {"ru": "1. Яндекс Музыка",                      "en": "1. Yandex Music"},
    "auth_step2_title":    {"ru": "2. SoundCloud",                         "en": "2. SoundCloud"},
    "auth_connected":      {"ru": "Подключено",                            "en": "Connected"},
    "auth_source_label":   {"ru": "Откуда переносить",                     "en": "Transfer from"},
    "auth_dest_label":     {"ru": "Куда переносить",                       "en": "Transfer to"},
    "auth_spotify_hint":   {"ru": "Нажми кнопку ниже, чтобы войти через Spotify и разрешить доступ к библиотеке.", "en": "Click the button below to sign in with Spotify and grant access to your library."},
    "auth_spotify_btn":    {"ru": "Подключить Spotify",                    "en": "Connect Spotify"},
    "auth_step1_desc":     {"ru": "Откройте ссылку, войдите в Яндекс, скопируйте код и вставьте ниже.", "en": "Open the link, sign in to Yandex, copy the code and paste it below."},
    "auth_open_yandex":    {"ru": "Открыть страницу Яндекса",              "en": "Open Yandex"},
    "auth_code_hint":      {"ru": "Код авторизации",                       "en": "Authorization code"},
    "auth_confirm_btn":    {"ru": "Подтвердить",                           "en": "Confirm"},
    "auth_step2_desc1":    {"ru": "Откройте",                              "en": "Open"},
    "auth_step2_desc2":    {"ru": ", войдите в аккаунт.",                  "en": ", sign in to your account."},
    "auth_step2_devtools": {"ru": "DevTools → Application → Cookies → значение", "en": "DevTools → Application → Cookies → value of"},
    "auth_sc_hint":        {"ru": "oauth_token (2-... или 3-...)",         "en": "oauth_token (2-... or 3-...)"},
    "auth_save_btn":       {"ru": "Сохранить",                             "en": "Save"},
    "auth_sc_oauth_hint":  {"ru": "Нажми кнопку ниже, чтобы войти через SoundCloud и разрешить доступ к аккаунту.", "en": "Click the button below to sign in with SoundCloud and grant access to your account."},
    "auth_sc_oauth_btn":   {"ru": "Подключить SoundCloud",                 "en": "Connect SoundCloud"},

    # ------------------------------------------------------------------ #
    # Progress page
    # ------------------------------------------------------------------ #
    "progress_back":    {"ru": "← История",    "en": "← History"},
    "progress_loading": {"ru": "Загрузка...",  "en": "Loading..."},

    # ------------------------------------------------------------------ #
    # Status fragment
    # ------------------------------------------------------------------ #
    "status_waiting":     {"ru": "Ожидаем данные...",   "en": "Waiting for data..."},
    "status_transferred": {"ru": "Перенесено",          "en": "Transferred"},
    "status_not_found":   {"ru": "Не найдено",          "en": "Not found"},
    "status_errors":      {"ru": "Ошибок",              "en": "Errors"},
    "status_in_queue":    {"ru": "В очереди",           "en": "In queue"},
    "status_report_btn":  {"ru": "Подробный отчёт",     "en": "Detailed report"},
    "status_csv_btn":     {"ru": "Скачать CSV",         "en": "Download CSV"},
    "status_progress":      {"ru": "Перенесено",  "en": "Transferred"},
    "status_current_track": {"ru": "Сейчас",      "en": "Now"},

    # Status labels (migration status)
    "mstatus_pending":   {"ru": "В очереди",    "en": "Queued"},
    "mstatus_running":   {"ru": "Выполняется",  "en": "Running"},
    "mstatus_done":      {"ru": "Завершён",     "en": "Completed"},
    "mstatus_failed":    {"ru": "Ошибка",       "en": "Failed"},
    "mstatus_cancelled": {"ru": "Отменён",      "en": "Cancelled"},

    # Track status labels
    "tstatus_liked":     {"ru": "Перенесено",   "en": "Transferred"},
    "tstatus_not_found": {"ru": "Не найдено",   "en": "Not found"},
    "tstatus_error":     {"ru": "Ошибка",       "en": "Error"},
    "tstatus_pending":   {"ru": "В очереди",    "en": "Queued"},

    # ------------------------------------------------------------------ #
    # Result
    # ------------------------------------------------------------------ #
    "result_back":         {"ru": "← История",       "en": "← History"},
    "result_progress":     {"ru": "Успешно перенесено", "en": "Successfully transferred"},
    "result_liked":        {"ru": "Перенесено",       "en": "Transferred"},
    "result_not_found":    {"ru": "Не найдено",       "en": "Not found"},
    "result_errors":       {"ru": "Ошибок",           "en": "Errors"},
    "result_total":        {"ru": "Всего",            "en": "Total"},
    "result_tracks_btn":   {"ru": "Треки",            "en": "Tracks"},
    "result_new_btn":      {"ru": "Новый перенос",    "en": "New transfer"},

    # ------------------------------------------------------------------ #
    # History
    # ------------------------------------------------------------------ #
    "history_title":    {"ru": "История переносов",    "en": "Transfer history"},
    "history_new_btn":  {"ru": "+ Новый",              "en": "+ New"},
    "history_empty":    {"ru": "Переносов пока нет.",  "en": "No transfers yet."},
    "history_start":    {"ru": "Начать первый",        "en": "Start your first"},
    "history_transfer": {"ru": "Перенос",              "en": "Transfer"},

    # ------------------------------------------------------------------ #
    # Tracks list
    # ------------------------------------------------------------------ #
    "tracks_back":        {"ru": "← Результат",   "en": "← Result"},
    "tracks_filter_all":  {"ru": "Все",            "en": "All"},
    "tracks_liked":       {"ru": "Перенесены",     "en": "Transferred"},
    "tracks_not_found":   {"ru": "Не найдены",     "en": "Not found"},
    "tracks_errors":      {"ru": "Ошибки",         "en": "Errors"},
    "tracks_pending":     {"ru": "В очереди",      "en": "Queued"},
    "tracks_col_artist":  {"ru": "Исполнитель",    "en": "Artist"},
    "tracks_col_title":   {"ru": "Название",       "en": "Title"},
    "tracks_col_status":  {"ru": "Статус",         "en": "Status"},
    "tracks_col_score":   {"ru": "Score",          "en": "Score"},
    "tracks_col_sc":      {"ru": "SC",             "en": "SC"},
    "tracks_empty":       {"ru": "Треков не найдено.", "en": "No tracks found."},
    "tracks_page_of":     {"ru": "стр.",           "en": "p."},
    "tracks_of":          {"ru": "из",             "en": "of"},
    "tracks_back_btn":    {"ru": "← Назад",        "en": "← Back"},
    "tracks_next_btn":    {"ru": "Вперёд →",       "en": "Next →"},

    # ------------------------------------------------------------------ #
    # Import
    # ------------------------------------------------------------------ #
    "import_title":       {"ru": "Импорт из файла",          "en": "Import from file"},
    "import_subtitle":    {"ru": "CSV или JSON со списком треков", "en": "CSV or JSON with your track list"},
    "import_back":        {"ru": "← Главная",                "en": "← Home"},
    "import_csv_title":   {"ru": "CSV",                      "en": "CSV"},
    "import_csv_desc":    {"ru": "Разделитель — запятая. Первая строка — заголовки.", "en": "Comma-separated. First row is headers."},
    "import_json_title":  {"ru": "JSON",                     "en": "JSON"},
    "import_json_desc":   {"ru": "Массив объектов.",         "en": "Array of objects."},
    "import_upload_btn":  {"ru": "Загрузить",                "en": "Upload"},
    "import_processing":  {"ru": "Обрабатываю...",           "en": "Processing..."},

    # Import preview
    "preview_first_rows":    {"ru": "первые",             "en": "first"},
    "preview_rows":          {"ru": "строк",              "en": "rows"},
    "preview_artist_col":    {"ru": "Исполнитель",        "en": "Artist column"},
    "preview_title_col":     {"ru": "Название",           "en": "Title column"},
    "preview_start_btn":     {"ru": "Начать перенос",     "en": "Start transfer"},
    "preview_empty":         {"ru": "Файл пуст.",         "en": "File is empty."},

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    "export_title":        {"ru": "Экспорт библиотеки",                       "en": "Export library"},
    "export_subtitle":     {"ru": "Скачай список треков из Яндекс Музыки в CSV или JSON.", "en": "Download your track list from Yandex Music as CSV or JSON."},
    "export_back":         {"ru": "← Главная",                                "en": "← Home"},
    "export_content":      {"ru": "Что экспортировать",                       "en": "What to export"},
    "export_liked_tracks": {"ru": "Лайкнутые треки",                          "en": "Liked tracks"},
    "export_playlists":    {"ru": "Плейлисты (все треки)",                    "en": "Playlists (all tracks)"},
    "export_format":       {"ru": "Формат файла",                             "en": "File format"},
    "export_btn":          {"ru": "Скачать файл",                             "en": "Download file"},
    "export_note":         {"ru": "Файл совместим с разделом «Импорт».",      "en": "File is compatible with the Import section."},
    "export_no_ym_token":  {"ru": "Нет токена Яндекс Музыки. Войди в аккаунт.", "en": "No Yandex Music token. Please sign in."},

    # Export (missing hints/loading)
    "export_csv_hint":   {"ru": "Совместим с Excel и Google Sheets.", "en": "Compatible with Excel and Google Sheets."},
    "export_json_hint":  {"ru": "Удобен для разработчиков.",          "en": "Developer-friendly format."},
    "export_loading":    {"ru": "Готовлю файл...",                     "en": "Preparing file..."},

    # ------------------------------------------------------------------ #
    # Bot — language selection
    # ------------------------------------------------------------------ #
    "bot_lang_choose":   {"ru": "Выбери язык / Choose your language:", "en": "Выбери язык / Choose your language:"},
    "bot_lang_set_ru":   {"ru": "Язык изменён: Русский 🇷🇺",           "en": "Язык изменён: Русский 🇷🇺"},
    "bot_lang_set_en":   {"ru": "Language changed: English 🇬🇧",       "en": "Language changed: English 🇬🇧"},

    # ------------------------------------------------------------------ #
    # Error messages (web)
    # ------------------------------------------------------------------ #
    "err_rate_limit":  {"ru": "Слишком много переносов. Попробуй через час.", "en": "Too many transfers. Try again in an hour."},
    "err_no_routes":   {"ru": "Направление не поддерживается.",              "en": "This transfer direction is not supported."},

    # ------------------------------------------------------------------ #
    # Bot strings
    # ------------------------------------------------------------------ #
    "bot_welcome": {
        "ru": (
            "Привет! Я перенесу твои треки из Яндекс Музыки в SoundCloud.\n\n"
            "Нажми /migrate чтобы начать."
        ),
        "en": (
            "Hi! I'll transfer your tracks from Yandex Music to SoundCloud.\n\n"
            "Press /migrate to get started."
        ),
    },
    "bot_help": {
        "ru": (
            "<b>Команды:</b>\n"
            "/migrate — начать перенос музыки\n"
            "/status — статус текущего переноса\n"
            "/cancel — отменить текущее действие\n"
            "/help — эта справка"
        ),
        "en": (
            "<b>Commands:</b>\n"
            "/migrate — start music transfer\n"
            "/status — current transfer status\n"
            "/cancel — cancel current action\n"
            "/help — this help message"
        ),
    },
    "bot_already_running":   {"ru": "Перенос уже запущен. Используй /status для проверки.",        "en": "Transfer already running. Use /status to check progress."},
    "bot_cancel_nothing":    {"ru": "Нечего отменять.",                                             "en": "Nothing to cancel."},
    "bot_cancelled":         {"ru": "Отменено. Напиши /migrate чтобы начать заново.",              "en": "Cancelled. Send /migrate to start again."},

    "bot_ym_expired":        {"ru": "Токен Яндекс Музыки истёк. Нужно авторизоваться заново.",     "en": "Yandex Music token expired. Please sign in again."},
    "bot_sc_expired":        {"ru": "Токен SoundCloud истёк. Нужно ввести новый.",                 "en": "SoundCloud token expired. Please enter a new one."},

    "bot_ym_step1": {
        "ru": (
            "<b>Шаг 1 из 2 — Яндекс Музыка</b>\n\n"
            "1. Нажми кнопку ниже и войди в свой аккаунт Яндекса\n"
            "2. После входа Яндекс покажет короткий код — скопируй его\n"
            "3. Отправь код сюда"
        ),
        "en": (
            "<b>Step 1 of 2 — Yandex Music</b>\n\n"
            "1. Click the button below and sign in to your Yandex account\n"
            "2. Yandex will show you a short code — copy it\n"
            "3. Send the code here"
        ),
    },
    "bot_ym_login_btn":      {"ru": "Войти через Яндекс",  "en": "Sign in with Yandex"},
    "bot_code_empty":        {"ru": "Код не должен быть пустым. Попробуй ещё раз:", "en": "Code cannot be empty. Try again:"},
    "bot_checking":          {"ru": "Проверяю...",         "en": "Checking..."},
    "bot_ym_ok":             {"ru": "Яндекс Музыка подключена!",  "en": "Yandex Music connected!"},
    "bot_ym_error":          {"ru": "Ошибка: {detail}\n\nПопробуй войти через кнопку снова:", "en": "Error: {detail}\n\nTry signing in again:"},

    "bot_sc_step2": {
        "ru": "<b>Шаг 2 из 2 — SoundCloud</b>\n\n{instructions}",
        "en": "<b>Step 2 of 2 — SoundCloud</b>\n\n{instructions}",
    },
    "bot_sc_instructions": {
        "ru": (
            "<b>Как получить токен SoundCloud:</b>\n\n"
            "1. Открой <a href='https://soundcloud.com'>soundcloud.com</a> в браузере\n"
            "2. Войди в аккаунт\n"
            "3. Нажми <b>F12</b> → вкладка <b>Application</b>\n"
            "4. Слева: <b>Cookies → https://soundcloud.com</b>\n"
            "5. Найди <code>oauth_token</code>, скопируй значение\n"
            "   (начинается с <code>2-</code> или <code>3-</code>)\n\n"
            "Сообщение с токеном сразу удалится из чата."
        ),
        "en": (
            "<b>How to get your SoundCloud token:</b>\n\n"
            "1. Open <a href='https://soundcloud.com'>soundcloud.com</a> in your browser\n"
            "2. Sign in to your account\n"
            "3. Press <b>F12</b> → <b>Application</b> tab\n"
            "4. On the left: <b>Cookies → https://soundcloud.com</b>\n"
            "5. Find <code>oauth_token</code> and copy its value\n"
            "   (starts with <code>2-</code> or <code>3-</code>)\n\n"
            "Your message with the token will be deleted immediately."
        ),
    },
    "bot_sc_token_empty":   {"ru": "Токен не должен быть пустым. Попробуй ещё раз:",            "en": "Token cannot be empty. Try again:"},
    "bot_sc_token_invalid": {
        "ru": "Токен выглядит неверно — должен начинаться с <code>2-</code> или <code>3-</code>.\nПопробуй скопировать снова:",
        "en": "Token looks invalid — should start with <code>2-</code> or <code>3-</code>.\nTry copying again:",
    },
    "bot_sc_checking":      {"ru": "Проверяю токен SoundCloud...", "en": "Checking SoundCloud token..."},
    "bot_sc_ok":            {"ru": "SoundCloud подключён! Сессия сохранена.", "en": "SoundCloud connected! Session saved."},
    "bot_sc_error":         {"ru": "Не удалось подключиться к SoundCloud: {detail}\n\nПопробуй ещё раз:", "en": "Could not connect to SoundCloud: {detail}\n\nTry again:"},
    "bot_sc_no_token": {
        "ru": (
            "Для SoundCloud нужна авторизация через веб-интерфейс.\n\n"
            "1. Открой: <a href=\"{url}\">{url}</a>\n"
            "2. Нажми «Подключить SoundCloud»\n"
            "3. Вернись сюда и отправь /migrate снова."
        ),
        "en": (
            "SoundCloud requires web authorization.\n\n"
            "1. Open: <a href=\"{url}\">{url}</a>\n"
            "2. Click «Connect SoundCloud»\n"
            "3. Return here and send /migrate again."
        ),
    },

    "bot_select_from": {
        "ru": "Выбери источник переноса:",
        "en": "Select transfer source:",
    },
    "bot_service_yandex":  {"ru": "Яндекс Музыка 🎵", "en": "Yandex Music 🎵"},
    "bot_service_spotify": {"ru": "Spotify 🟢",        "en": "Spotify 🟢"},
    "bot_spotify_no_token": {
        "ru": (
            "Для Spotify нужна авторизация через веб-интерфейс.\n\n"
            "1. Открой: <a href=\"{url}\">{url}</a>\n"
            "2. Нажми «Подключить Spotify»\n"
            "3. Вернись сюда и отправь /migrate снова."
        ),
        "en": (
            "Spotify requires web authorization.\n\n"
            "1. Open: <a href=\"{url}\">{url}</a>\n"
            "2. Click «Connect Spotify»\n"
            "3. Return here and send /migrate again."
        ),
    },
    "bot_confirm_spotify": {
        "ru": "<b>Spotify подключён! Перенести треки в SoundCloud?</b>\n\nТреков в Spotify: <b>{tracks}</b>\n\n{eta}. Бот пришлёт уведомление когда закончит.",
        "en": "<b>Spotify connected! Transfer tracks to SoundCloud?</b>\n\nSpotify tracks: <b>{tracks}</b>\n\n{eta}. The bot will notify you when done.",
    },
    "bot_migration_started_spotify": {
        "ru": "Перенос запущен (Spotify → SoundCloud)...\nЗагружаю треки из Spotify, подожди немного.",
        "en": "Transfer started (Spotify → SoundCloud)...\nFetching tracks from Spotify, please wait.",
    },

    "bot_loading_account":  {"ru": "Получаю информацию об аккаунте...", "en": "Fetching account info..."},
    "bot_confirm_ready": {
        "ru": "<b>Готово! Что перенести из {service}?</b>",
        "en": "<b>Ready! What to transfer from {service}?</b>",
    },
    "bot_confirm": {
        "ru": (
            "<b>Всё готово! Что перенести?</b>\n\n"
            "Лайкнутых треков:   <b>{tracks}</b>\n"
            "Плейлистов:         <b>{playlists}</b>\n"
            "Лайкнутых артистов: <b>{artists}</b>\n\n"
            "{eta}. Бот пришлёт уведомление когда закончит."
        ),
        "en": (
            "<b>Ready! What would you like to transfer?</b>\n\n"
            "Liked tracks:   <b>{tracks}</b>\n"
            "Playlists:      <b>{playlists}</b>\n"
            "Liked artists:  <b>{artists}</b>\n\n"
            "{eta}. The bot will notify you when done."
        ),
    },
    "bot_btn_tracks_only":  {"ru": "Только треки",                    "en": "Tracks only"},
    "bot_btn_full":         {"ru": "Треки + плейлисты + артисты",     "en": "Tracks + playlists + artists"},
    "bot_btn_cancel":       {"ru": "Отмена",                          "en": "Cancel"},
    "bot_select_limit":     {"ru": "Сколько треков перенести?",        "en": "How many tracks to transfer?"},
    "bot_btn_limit_all":    {"ru": "Все треки",                        "en": "All tracks"},
    "bot_btn_limit_n":      {"ru": "Первые {n}",                       "en": "First {n}"},
    "bot_btn_detach":       {"ru": "Отключиться от переноса",         "en": "Detach from transfer"},
    "bot_btn_not_found":    {"ru": "Ненайденные треки ({n})",         "en": "Not found tracks ({n})"},
    "bot_btn_open_browser": {"ru": "Открыть в браузере",              "en": "Open in browser"},
    "bot_btn_new_transfer": {"ru": "Новый перенос",                   "en": "New transfer"},

    "bot_migration_started_tracks": {"ru": "Перенос запущен (только треки)...\nЗагружаю треки из Яндекс Музыки, подожди немного.", "en": "Transfer started (tracks only)...\nFetching tracks from Yandex Music, please wait."},
    "bot_migration_started_full":   {"ru": "Перенос запущен (треки + плейлисты + артисты)...\nЗагружаю треки из Яндекс Музыки, подожди немного.", "en": "Transfer started (tracks + playlists + artists)...\nFetching tracks from Yandex Music, please wait."},
    "bot_migration_fail_start":     {"ru": "Не удалось запустить перенос:\n<code>{e}</code>\n\nПопробуй /migrate снова.", "en": "Could not start transfer:\n<code>{e}</code>\n\nTry /migrate again."},
    "bot_cancel_confirm":           {"ru": "Отменено. Напиши /migrate чтобы начать заново.", "en": "Cancelled. Send /migrate to start again."},
    "bot_detach_msg":               {"ru": "Отключились от переноса. Задача продолжит работу на сервере.\nИспользуй /status или /history в браузере для проверки.", "en": "Detached from transfer. The job continues on the server.\nUse /status or check history in the browser."},
    "bot_detach_no_active":         {"ru": "Активного переноса нет.", "en": "No active transfer."},
    "bot_already_in_progress":      {"ru": "Перенос уже идёт. Используй /status для проверки прогресса.", "en": "Transfer is in progress. Use /status to check."},
    "bot_progress_loading":         {"ru": "Идёт перенос... Загружаю треки.",  "en": "Transfer in progress... Loading tracks."},
    "bot_progress_bar":             {"ru": "Идёт перенос...\n\n{bar} {pct}%\n{done} / {total} треков\n\nПеренесено: {liked} | Не найдено: {nf} | Ошибок: {err}", "en": "Transferring...\n\n{bar} {pct}%\n{done} / {total} tracks\n\nTransferred: {liked} | Not found: {nf} | Errors: {err}"},

    "bot_done_tracks": {
        "ru": "Перенос завершён!\n\n<b>Треки:</b>\n  Перенесено:  <b>{liked}</b>\n  Не найдено:  <b>{nf}</b>\n  Ошибок:      <b>{err}</b>\n  Всего:       <b>{total}</b>\n",
        "en": "Transfer complete!\n\n<b>Tracks:</b>\n  Transferred: <b>{liked}</b>\n  Not found:   <b>{nf}</b>\n  Errors:      <b>{err}</b>\n  Total:       <b>{total}</b>\n",
    },
    "bot_done_artists": {
        "ru": "\n<b>Артисты:</b>\n  Подписок:   <b>{followed}</b>\n  Не найдено: <b>{nf}</b>\n",
        "en": "\n<b>Artists:</b>\n  Followed:   <b>{followed}</b>\n  Not found:  <b>{nf}</b>\n",
    },

    "bot_status_not_running":  {"ru": "Перенос сейчас не запущен. Напиши /migrate чтобы начать.", "en": "No transfer running. Send /migrate to start."},
    "bot_status_no_stats":     {"ru": "Перенос запущен, статистика пока недоступна.", "en": "Transfer started, stats not yet available."},
    "bot_status_fail":         {"ru": "Не удалось получить статус: {e}", "en": "Could not get status: {e}"},
    "bot_status_msg":          {"ru": "Прогресс переноса #{id}:\n\nОбработано: {done}/{total} ({pct}%)\nПеренесено: {liked}\nНе найдено: {nf}\nВ очереди:  {pending}\nОшибок:     {err}", "en": "Transfer #{id} progress:\n\nProcessed: {done}/{total} ({pct}%)\nTransferred: {liked}\nNot found: {nf}\nQueued: {pending}\nErrors: {err}"},

    "bot_not_found_list":      {"ru": "<b>Ненайденные треки ({n}):</b>\n\n", "en": "<b>Not found tracks ({n}):</b>\n\n"},
    "bot_not_found_more":      {"ru": "\n\n<i>...и ещё {n} треков.</i>\nПолный список: <a href=\"{url}\">в браузере</a>", "en": "\n\n<i>...and {n} more tracks.</i>\nFull list: <a href=\"{url}\">in browser</a>"},
    "bot_not_found_none":      {"ru": "Ненайденных треков нет.", "en": "No unfound tracks."},
    "bot_not_found_error":     {"ru": "Не удалось загрузить список: {e}", "en": "Could not load list: {e}"},

    # ------------------------------------------------------------------ #
    # Worker notifications
    # ------------------------------------------------------------------ #
    "notif_done": {
        "ru": "Перенос #{id} завершён!\n\nПеренесено:  <b>{liked}</b>\nНе найдено:  <b>{nf}</b>\nОшибок:      <b>{err}</b>\nВсего:       <b>{total}</b>",
        "en": "Transfer #{id} complete!\n\nTransferred: <b>{liked}</b>\nNot found:   <b>{nf}</b>\nErrors:      <b>{err}</b>\nTotal:       <b>{total}</b>",
    },
    "notif_done_artists": {
        "ru": "\nАртистов подписок: <b>{followed}</b>, не найдено: <b>{nf}</b>",
        "en": "\nArtists followed: <b>{followed}</b>, not found: <b>{nf}</b>",
    },
    "notif_done_link":    {"ru": "Открыть результат",   "en": "View result"},
    "notif_failed":       {"ru": "Перенос #{id} завершился с ошибкой.\n\nПопробуй запустить снова через /migrate", "en": "Transfer #{id} failed.\n\nTry again with /migrate"},

    # ETA
    "eta_approx":         {"ru": "⏱ ~{n} мин",         "en": "⏱ ~{n} min"},
    "eta_approx_hours":   {"ru": "⏱ ~{h} ч {m} мин",   "en": "⏱ ~{h} h {m} min"},
    "eta_label":          {"ru": "Примерное время",      "en": "Estimated time"},
}


# Seconds per track by destination service (conservative estimates)
_SECS_PER_TRACK: dict[str, float] = {
    "yandex_music": 1.5,  # no strict rate limit
    "spotify":      0.8,  # generous Spotify API limits
}


def format_eta(track_count: int, to_service: str, lang: str = "ru",
               sc_rate_limit_sleep: float = 2.0) -> str:
    """Return localised ETA string, e.g. '⏱ ~5 мин' or '⏱ ~2 ч 30 мин'."""
    import math
    if to_service == "soundcloud":
        secs = sc_rate_limit_sleep + 1.5
    else:
        secs = _SECS_PER_TRACK.get(to_service, 3.0)
    total_min = max(1, math.ceil(track_count * secs / 60))
    if total_min < 60:
        return t("eta_approx", lang).format(n=total_min)
    h, m = divmod(total_min, 60)
    return t("eta_approx_hours", lang).format(h=h, m=m)


def t(key: str, lang: str = "ru") -> str:
    """Return translated string. Falls back to Russian, then to key itself."""
    entry = _S.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get("ru") or key


def detect_lang_web(request) -> str:
    """
    Detect language for web request.
    Priority: session["lang"] > Accept-Language header > "ru"
    """
    lang = request.session.get("lang")
    if lang in ("ru", "en"):
        return lang

    accept = request.headers.get("accept-language", "")
    # e.g. "en-US,en;q=0.9,ru;q=0.8"
    for part in accept.split(","):
        code = part.strip().split(";")[0].split("-")[0].lower()
        if code in ("ru",):
            return "ru"
        if code in ("en",):
            return "en"
    return "ru"


_CIS_LANG_CODES = {
    "ru",  # Russian
    "uk",  # Ukrainian
    "be",  # Belarusian
    "kk",  # Kazakh
    "uz",  # Uzbek
    "az",  # Azerbaijani
    "hy",  # Armenian
    "ka",  # Georgian
    "ky",  # Kyrgyz
    "tg",  # Tajik
    "tk",  # Turkmen
    "mn",  # Mongolian
}


def detect_lang_tg(language_code: str | None) -> str:
    """Detect language from Telegram user.language_code.
    CIS country codes map to Russian; everything else maps to English.
    Returns 'ru' if language_code is None (can't determine).
    """
    if not language_code:
        return "ru"
    code = language_code.split("-")[0].lower()
    return "ru" if code in _CIS_LANG_CODES else "en"
