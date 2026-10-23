"""Name normalisation, Levenshtein similarity and watchlist screening (case §6.1, design §8.4–8.5)."""
import re
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

_NON_LETTERS = re.compile(r"[^A-Z ]")


def normalise(name: str | None, titles: set[str]) -> str:
    """Upper case, '.'/'-' to space, keep A–Z and space, drop titles, sort tokens."""
    s = (name or "").upper().replace(".", " ").replace("-", " ")
    s = _NON_LETTERS.sub("", s)
    tokens = [t for t in s.split() if t not in titles]
    return " ".join(sorted(tokens))


def similarity(a: str, b: str) -> float:
    """1 - Levenshtein distance / length of the longer string (inputs already normalised)."""
    if not a and not b:
        return 1.0
    return 1 - Levenshtein.distance(a, b) / max(len(a), len(b))


@dataclass
class WatchlistEntry:
    list_type: str          # SANCTIONS | PEP
    entry_id: str
    name: str
    alias: str
    dob: str                # YYYY-MM-DD or ""
    extra: str = ""         # program (sanctions) or position (PEP)


@dataclass
class ScreeningHit:
    list_type: str
    entry_id: str
    entry_name: str
    matched_on: str         # NAME | ALIAS
    similarity: float
    result: str             # MATCH | POSSIBLE
    dob_comparison: str     # SAME | DIFFERENT | LIST_DOB_EMPTY
    list_dob: str

    def as_dict(self) -> dict:
        return {**self.__dict__, "similarity": round(self.similarity, 4)}


def screen(declared_name: str, declared_dob: str, entries: list[WatchlistEntry],
           titles: set[str], match_at: float, possible_at: float) -> tuple[str, ScreeningHit | None]:
    """Screen one name against one list. Returns (MATCH | POSSIBLE | NONE, best hit)."""
    target = normalise(declared_name, titles)
    best: dict[str, ScreeningHit] = {}
    for e in entries:
        candidates = [("NAME", e.name)] + ([("ALIAS", e.alias)] if e.alias else [])
        on, sim = max(((on, similarity(target, normalise(v, titles))) for on, v in candidates),
                      key=lambda x: x[1])
        if sim < possible_at:
            continue
        if not e.dob:
            dob_cmp = "LIST_DOB_EMPTY"
        else:
            dob_cmp = "SAME" if e.dob == declared_dob else "DIFFERENT"
        result = "MATCH" if sim >= match_at and dob_cmp != "DIFFERENT" else "POSSIBLE"
        hit = ScreeningHit(e.list_type, e.entry_id, e.name, on, sim, result, dob_cmp, e.dob)
        if result not in best or sim > best[result].similarity:
            best[result] = hit
    for result in ("MATCH", "POSSIBLE"):
        if result in best:
            return result, best[result]
    return "NONE", None
