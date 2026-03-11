"""
Нечёткое сопоставление треков между стриминговыми платформами.

Стратегия:
1. Нормализация: lowercase, убираем пунктуацию, feat., ремастеры и т.д.
2. Транслитерация: генерируем несколько латинских вариантов кириллических строк
3. Scoring: взвешенная комбинация artist_score (40%) + title_score (60%)
4. Порог: score >= threshold → match, иначе not_found
"""
import re
import unicodedata
from dataclasses import dataclass

import iuliia
from rapidfuzz import fuzz

from config import settings


# ---------------------------------------------------------------------------
# Нормализация
# ---------------------------------------------------------------------------

# Паттерны для удаления лишнего из названий
_FEAT_RE = re.compile(r"\(?\b(feat\.?|ft\.?|featuring)\b.*?(\)|$)", re.IGNORECASE)
_REMASTER_RE = re.compile(
    r"\(?\b(remaster(ed)?|reissue|anniversary|deluxe|edition|version|live|acoustic|radio edit)\b.*?(\)|$)",
    re.IGNORECASE,
)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """
    Приводит строку к нормализованному виду для сравнения:
    - unicode NFKD
    - lowercase
    - убирает feat./ft., ремастеры, скобки
    - убирает пунктуацию
    - схлопывает пробелы
    """
    if not text:
        return ""
    # Нормализация unicode
    text = unicodedata.normalize("NFKD", text)
    text = text.lower().strip()
    # Убираем feat. и ремастеры
    text = _FEAT_RE.sub("", text)
    text = _REMASTER_RE.sub("", text)
    # Убираем пунктуацию
    text = _PUNCTUATION_RE.sub(" ", text)
    # Схлопываем пробелы
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
    Вычисляет схожесть двух уже нормализованных строк.
    Использует максимум из нескольких метрик rapidfuzz.
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
    Возвращает итоговый score (0-100) совпадения двух треков.
    Работает для любых пар сервисов (YM, Spotify, SC, File).

    Алгоритм:
    - Генерируем варианты транслитерации для строк источника
    - Для каждого варианта считаем artist_score и title_score
    - Итог = max по всем вариантам (0.4 * artist + 0.6 * title)
    """
    norm_sc_artist = normalize(cand_artist)
    norm_sc_title = normalize(cand_title)

    best = 0.0
    for ym_art_variant in transliterate_variants(source_artist):
        for ym_ttl_variant in transliterate_variants(source_title):
            norm_art = normalize(ym_art_variant)
            norm_ttl = normalize(ym_ttl_variant)

            artist_score = _score_pair(norm_art, norm_sc_artist)
            title_score = _score_pair(norm_ttl, norm_sc_title)
            combined = 0.4 * artist_score + 0.6 * title_score

            # Бонус: если название совпадает идеально — поднимаем оценку
            if title_score >= 95:
                combined = max(combined, 0.5 * artist_score + 0.5 * title_score)

            best = max(best, combined)

    return round(best, 2)


# ---------------------------------------------------------------------------
# Выбор лучшего кандидата
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    sc_id: int
    sc_url: str
    sc_artist: str
    sc_title: str
    score: float
    matched: bool           # score >= threshold
    uncertain: bool         # score в зоне [match_uncertain_floor, match_threshold) — стоит проверить вручную


@dataclass
class SCCandidate:
    """
    Кандидат для сравнения с треком-источником.
    Используется для всех целевых платформ (SC, YM, Spotify) — название исторически SC-specific,
    но логика и поля универсальны.
    """
    sc_id: int
    sc_url: str
    artist: str
    title: str


# ---------------------------------------------------------------------------
# Разбивка составных артистов
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring|при\s+уч\.?|при\s+участии|&|x)\s+", re.IGNORECASE)


def split_artists(artist: str) -> list[str]:
    """
    Разбивает строку артиста по паттернам: feat., ft., &, x (регистронезависимо).
    Возвращает список уникальных частей без лишних пробелов.

    Примеры:
      "Земфира feat. Океан Ельзи"  → ["Земфира", "Океан Ельзи"]
      "Joji & Rex Orange County"   → ["Joji", "Rex Orange County"]
      "A ft. B x C"                → ["A", "B", "C"]
      "Solo Artist"                → ["Solo Artist"]
    """
    parts = _SPLIT_RE.split(artist)
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.append(p)
    return seen if seen else [artist]


def find_best_match(
    source_artist: str,
    source_title: str,
    candidates: list[SCCandidate],
    threshold: float | None = None,
) -> MatchResult | None:
    """
    Выбирает лучшего кандидата из списка.
    Работает для любых пар платформ (YM→SC, Spotify→YM, File→Spotify и т.д.).

    Возвращает MatchResult или None если кандидатов нет.
    matched=True  если score >= threshold (по умолчанию из конфига)
    uncertain=True если score в диапазоне [uncertain_floor, threshold)
    """
    if not candidates:
        return None

    effective_threshold = threshold if threshold is not None else settings.match_threshold
    uncertain_floor = settings.match_uncertain_floor

    best_score = -1.0
    best_candidate: SCCandidate | None = None

    for cand in candidates:
        score = score_track_match(source_artist, source_title, cand.artist, cand.title)
        if score > best_score:
            best_score = score
            best_candidate = cand

    if best_candidate is None:
        return None

    return MatchResult(
        sc_id=best_candidate.sc_id,
        sc_url=best_candidate.sc_url,
        sc_artist=best_candidate.artist,
        sc_title=best_candidate.title,
        score=best_score,
        matched=best_score >= effective_threshold,
        uncertain=uncertain_floor <= best_score < effective_threshold,
    )
