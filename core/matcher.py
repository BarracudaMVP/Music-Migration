"""
Нечёткое сопоставление треков между стриминговыми платформами.

=== АЛГОРИТМ ===

Цель: по метаданным трека-источника (артист + название) найти лучшего кандидата
на целевой платформе из пула результатов поиска.

──────────────────────────────────────────────────
Шаг 1. НОРМАЛИЗАЦИЯ (normalize)
──────────────────────────────────────────────────
Приводит строку к сравнимому виду:
  1. Unicode NFKD: "½" → "1⁄2", "é" → "e" (разложение диакритических знаков)
  2. lowercase
  3. Удаляет суффиксы feat./ft./featuring и всё после них
  4. Удаляет маркеры версий: Remaster, Live, Radio Edit, Deluxe, Acoustic и т.д.
  5. Заменяет пунктуацию пробелами
  6. Схлопывает пробелы

Примеры:
  "Daft Punk - Get Lucky (feat. Pharrell Williams)" → "daft punk get lucky"
  "Bohemian Rhapsody (Remastered 2011)"              → "bohemian rhapsody"

──────────────────────────────────────────────────
Шаг 2. ТРАНСЛИТЕРАЦИЯ (transliterate_variants)
──────────────────────────────────────────────────
Если строка содержит кириллицу — генерируем несколько латинских вариантов:
  - WIKIPEDIA  (Чайковский → Tchaikovsky)
  - YANDEX_MAPS (Чайковский → Chaykovskiy)
  - BGN_PCGN   (официальная US/UK схема)

Цель: компенсировать разные транслитерации одного имени между платформами.
Строки без кириллицы возвращаются как есть.

──────────────────────────────────────────────────
Шаг 3. ПОПАРНОЕ СРАВНЕНИЕ (_score_pair)
──────────────────────────────────────────────────
Для двух уже нормализованных строк вычисляет score 0–100:
  max(WRatio, token_sort_ratio)

  WRatio — rapidfuzz, автоматически выбирает лучшую из метрик:
    - ratio:         посимвольное сравнение двух строк целиком
    - partial_ratio: ищет одну строку как подстроку другой
    - token_sort_ratio: сортирует слова перед сравнением
  Примечание: token_set_ratio намеренно исключён — он давал ложные матчи
  при коротких подстроках ("заря" vs "алая заря" → 100).

  token_sort_ratio — явно, для случаев с переставленными словами:
    "Last Flower" vs "Flower Last" → 100

──────────────────────────────────────────────────
Шаг 4. ИТОГОВЫЙ SCORE (score_track_match)
──────────────────────────────────────────────────
Для каждой комбинации [транслитерации источника] × [варианты]:
  artist_score = _score_pair(norm_src_artist, norm_cand_artist)
  title_score  = _score_pair(norm_src_title,  norm_cand_title)
  combined     = 0.4 × artist_score + 0.6 × title_score

  Бонус: если title_score ≥ 95 (почти точное совпадение названия):
    combined = max(combined, 0.5 × artist_score + 0.5 × title_score)
    (артист может отличаться — кавер, фит, сборник)

Итог = max по всем вариантам транслитерации, округлён до 2 знаков.

Веса 60% title / 40% artist:
  - Название уникально идентифицирует трек внутри дискографии
  - Артист может записываться по-разному: сокращения, feat., псевдонимы

──────────────────────────────────────────────────
Шаг 5. ЗОНЫ SCORE (find_best_match)
──────────────────────────────────────────────────
Из пула кандидатов выбирается один с максимальным score.

  [0,                MATCH_UNCERTAIN_FLOOR) → not_found  (явно чужой трек)
  [MATCH_UNCERTAIN_FLOOR, MATCH_THRESHOLD) → uncertain   (возможно правильный)
  [MATCH_THRESHOLD,   100]                 → matched     (принимается автоматически)

  Пороги задаются в .env: MATCH_THRESHOLD (default 75), MATCH_UNCERTAIN_FLOOR (default 60).

──────────────────────────────────────────────────
ПОЧЕМУ ТРЕК МОЖЕТ НЕ ЗАМАТЧИТЬСЯ
──────────────────────────────────────────────────
  1. Трека нет на целевой платформе (наиболее частая причина)
  2. Артист известен под другим именем/псевдонимом на другой платформе
  3. Кириллическое имя не совпало ни с одним вариантом транслитерации
     → решение MM-74: добавить схемы транслитерации / ручной словарь псевдонимов
  4. Название очень короткое (1–2 слова) → score недостаточно высок при разных артистах
  5. Коллаборация с разным порядком имён: "A feat. B" vs "B & A"
     → частично решается split_artists(): ищем по каждому артисту отдельно
  6. На целевой платформе доступна только другая версия (Remix, Live, Cover)
  7. Трек находится в поиске, но за пределами SEARCH_LIMIT первых результатов
     → увеличить _SEARCH_LIMIT в клиенте целевой платформы
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import iuliia
from rapidfuzz import fuzz

from config import settings


# ---------------------------------------------------------------------------
# Нормализация
# ---------------------------------------------------------------------------

_FEAT_RE = re.compile(r"\(?\b(feat\.?|ft\.?|featuring)\b.*?(\)|$)", re.IGNORECASE)
_REMASTER_RE = re.compile(
    r"\(?\b(remaster(ed)?|reissue|anniversary|deluxe|edition|version|live|acoustic|radio edit)\b.*?(\)|$)",
    re.IGNORECASE,
)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """
    Приводит строку к нормализованному виду для сравнения.
    Шаги: unicode NFKD → lowercase → убрать feat./ремастеры → убрать пунктуацию → схлопнуть пробелы.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower().strip()
    text = _FEAT_RE.sub("", text)
    text = _REMASTER_RE.sub("", text)
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Транслитерация
# ---------------------------------------------------------------------------

def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04FF" for ch in text)


def transliterate_variants(text: str) -> list[str]:
    """
    Если текст содержит кириллицу — возвращает оригинал + несколько
    латинских вариантов через разные схемы iuliia.
    Если кириллицы нет — возвращает только оригинал.
    """
    if not _has_cyrillic(text):
        return [text]

    variants = [text]
    for schema in (iuliia.WIKIPEDIA, iuliia.YANDEX_MAPS, iuliia.BGN_PCGN):
        try:
            transliterated = iuliia.translate(text, schema)
            if transliterated and transliterated not in variants:
                variants.append(transliterated)
        except Exception:
            pass
    return variants


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_pair(source: str, candidate: str) -> float:
    """
    Сравнивает две уже нормализованных строки. Возвращает score 0–100.
    Использует max(WRatio, token_sort_ratio).
    token_set_ratio исключён намеренно — давал ложные матчи при коротких подстроках.
    """
    if not source or not candidate:
        return 0.0
    return max(
        fuzz.WRatio(source, candidate),
        fuzz.token_sort_ratio(source, candidate),
    )


def score_track_match(
    source_artist: str,
    source_title: str,
    cand_artist: str,
    cand_title: str,
) -> float:
    """
    Возвращает итоговый score (0–100) совпадения двух треков.
    Платформонезависим: работает для любой пары источник → цель.

    Алгоритм: транслитерационные варианты × scoring → max.
    Веса: 40% artist + 60% title. При title ≥ 95 — бонусное выравнивание весов.
    """
    norm_cand_artist = normalize(cand_artist)
    norm_cand_title = normalize(cand_title)

    best = 0.0
    for src_art_variant in transliterate_variants(source_artist):
        for src_ttl_variant in transliterate_variants(source_title):
            norm_art = normalize(src_art_variant)
            norm_ttl = normalize(src_ttl_variant)

            artist_score = _score_pair(norm_art, norm_cand_artist)
            title_score  = _score_pair(norm_ttl, norm_cand_title)
            combined = 0.4 * artist_score + 0.6 * title_score

            # Бонус: при почти точном совпадении названия артист может отличаться (кавер, фит)
            if title_score >= 95:
                combined = max(combined, 0.5 * artist_score + 0.5 * title_score)

            best = max(best, combined)

    return round(best, 2)


# ---------------------------------------------------------------------------
# Типы данных
# ---------------------------------------------------------------------------

@dataclass
class TrackCandidate:
    """
    Кандидат с целевой платформы для сравнения с треком-источником.
    Платформонезависим: используется для SC, YM, Spotify и любых других.

    track_id:  числовой ID (или хэш строкового ID) — ключ дедупликации
    track_url: строковый ID/URL для фактического API-вызова (like, follow и т.д.)
    """
    track_id: int
    track_url: str
    artist: str
    title: str


@dataclass
class MatchResult:
    """Результат матчинга: лучший найденный кандидат + метаданные совпадения."""
    track_id: int
    track_url: str
    cand_artist: str
    cand_title: str
    score: float
    matched: bool    # score >= MATCH_THRESHOLD
    uncertain: bool  # score в зоне [MATCH_UNCERTAIN_FLOOR, MATCH_THRESHOLD)


# ---------------------------------------------------------------------------
# Разбивка составных артистов
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(
    r"\s+(?:feat\.?|ft\.?|featuring|при\s+уч\.?|при\s+участии|&|x)\s+",
    re.IGNORECASE,
)


def split_artists(artist: str) -> list[str]:
    """
    Разбивает строку артиста по разделителям: feat., ft., &, x и др.
    Возвращает список уникальных частей.

    Примеры:
      "Земфира feat. Океан Ельзи"  → ["Земфира", "Океан Ельзи"]
      "Joji & Rex Orange County"   → ["Joji", "Rex Orange County"]
      "A ft. B x C"                → ["A", "B", "C"]
      "Solo Artist"                → ["Solo Artist"]

    Используется перед поиском: запрос по каждому артисту отдельно даёт больший
    пул кандидатов, повышая шанс найти трек с составным артистом.
    """
    parts = _SPLIT_RE.split(artist)
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.append(p)
    return seen if seen else [artist]


# ---------------------------------------------------------------------------
# Выбор лучшего кандидата
# ---------------------------------------------------------------------------

def find_best_match(
    source_artist: str,
    source_title: str,
    candidates: list[TrackCandidate],
    threshold: float | None = None,
) -> MatchResult | None:
    """
    Выбирает лучшего кандидата из пула по score_track_match.
    Платформонезависим: работает для любых пар платформ.

    Возвращает MatchResult или None если кандидатов нет.
      matched=True   если score >= threshold (автоматический матч)
      uncertain=True если score в [uncertain_floor, threshold) (стоит проверить вручную)
    """
    if not candidates:
        return None

    effective_threshold = threshold if threshold is not None else settings.match_threshold
    uncertain_floor = settings.match_uncertain_floor

    best_score = -1.0
    best_candidate: TrackCandidate | None = None

    for cand in candidates:
        score = score_track_match(source_artist, source_title, cand.artist, cand.title)
        if score > best_score:
            best_score = score
            best_candidate = cand

    if best_candidate is None:
        return None

    return MatchResult(
        track_id=best_candidate.track_id,
        track_url=best_candidate.track_url,
        cand_artist=best_candidate.artist,
        cand_title=best_candidate.title,
        score=best_score,
        matched=best_score >= effective_threshold,
        uncertain=uncertain_floor <= best_score < effective_threshold,
    )
