"""
Phase 5.14 — BibTeX formatter for reading list exports.

Pure and deterministic: `format_entries(works)` turns research works into BibTeX text with no
database access, no network and no clock. The same works always produce byte-identical output,
whatever order they arrive in, because entries are written in citation-key order.

Only bibliographic fields are read. A reading list item's status and private notes are never
passed in, so they can never appear in an export.

Entry types, from `work_type` (lowercased, `_` read as `-`):

  book-chapter                     @incollection   booktitle = venue
  book, monograph                  @book
  dissertation                     @phdthesis
  preprint, posted-content         @misc           howpublished = venue, note = {Preprint}
  proceedings-article,
  conference-paper, or any other
  work in a conference source      @inproceedings  booktitle = venue
  article, journal-article         @article        journal = venue
  anything else                    @misc           howpublished = venue

`conference-paper` is OpenAlex's current name for a proceedings article. A conference source is
checked before `article` because OpenAlex types many conference papers as articles.

Citation keys are the ASCII-folded family name of the first author (the last word of their
display name; `anon` without one), the year (`nd` without one) and the first title word that is
not a stopword, cut to 10 characters (the first 8 hex digits of the work id when there is none):
`lovelace1843sketch`. Works that share a key get the suffixes a, b, c ... ordered by title, then
work id.

Author order: only each author's position (first, middle or last) is recorded, not their place
in the byline, so authors are ordered first, then middle, then last, then unknown, and within a
position by display name, then researcher id. Middle authors are therefore listed
alphabetically, which is not necessarily the order printed on the paper.

Fields are written in a fixed order, each only when present: author, title, journal / booktitle
/ howpublished, year, volume, number, pages, doi, url, note. Text fields have LaTeX specials
escaped and whitespace collapsed; the title is wrapped in a second pair of braces so styles keep
its capitalisation. Entries use a two-space indent, are separated by a blank line, and the output
ends with a newline (an empty export is an empty string).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence

TITLE_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is",
        "it", "its", "of", "on", "or", "the", "to", "toward", "towards", "via", "with",
    }
)

_POSITION_RANK = {"first": 0, "middle": 1, "last": 2}
_UNKNOWN_POSITION = 3

_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

_WORD = re.compile(r"[a-z0-9]+")
_PAGE_RANGE = re.compile(r"\s*[-‐-―]+\s*")


def _collapse(text: Any) -> str:
    """The text with runs of whitespace reduced to single spaces and the ends trimmed."""
    return " ".join(str(text).split()) if text is not None else ""


def _ascii_words(text: str) -> list[str]:
    """Lowercase ASCII words of the text, accents folded: 'Gödel' becomes ['godel']."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return _WORD.findall(folded.lower())


def escape_latex(text: Any) -> str:
    """Collapses whitespace, then escapes every LaTeX special in one pass (no double escaping)."""
    return "".join(_LATEX_SPECIALS.get(char, char) for char in _collapse(text))


def _identifier(value: Any) -> str | None:
    """A DOI or URL with whitespace and braces removed (braces would break the entry)."""
    cleaned = re.sub(r"[\s{}]", "", str(value)) if value else ""
    return cleaned or None


def ordered_author_names(work: Any) -> list[str]:
    """Author display names: first, middle, last, unknown; then by name, then researcher id."""
    ranked: list[tuple[int, str, str]] = []
    for link in getattr(work, "author_links", None) or ():
        researcher = getattr(link, "researcher", None)
        name = _collapse(getattr(researcher, "display_name", None))
        if not name:
            continue
        position = _collapse(getattr(link, "author_position", None)).lower()
        researcher_id = getattr(link, "researcher_id", None) or getattr(researcher, "id", None)
        ranked.append(
            (_POSITION_RANK.get(position, _UNKNOWN_POSITION), name, str(researcher_id or ""))
        )
    ranked.sort()
    return [name for _, name, _ in ranked]


def _venue_name(work: Any) -> str | None:
    return _collapse(getattr(getattr(work, "primary_source", None), "display_name", None)) or None


def _entry_type(work: Any) -> tuple[str, str | None, str | None]:
    """(entry type, the field that names the venue, note)."""
    kind = _collapse(getattr(work, "work_type", None)).lower().replace("_", "-")
    source_type = _collapse(
        getattr(getattr(work, "primary_source", None), "source_type", None)
    ).lower()
    if kind == "book-chapter":
        return "incollection", "booktitle", None
    if kind in ("book", "monograph"):
        return "book", None, None
    if kind == "dissertation":
        return "phdthesis", None, None
    if kind in ("preprint", "posted-content"):
        return "misc", "howpublished", "Preprint"
    if kind in ("proceedings-article", "conference-paper") or source_type == "conference":
        return "inproceedings", "booktitle", None
    if kind in ("article", "journal-article"):
        return "article", "journal", None
    return "misc", "howpublished", None


def _base_key(work: Any, authors: Sequence[str]) -> str:
    family = "anon"
    if authors:
        family = "".join(_ascii_words(authors[0].split()[-1])) or "anon"
    year = getattr(work, "publication_year", None)
    word = next(
        (w for w in _ascii_words(_collapse(getattr(work, "title", None))) if w not in TITLE_STOPWORDS),
        None,
    )
    if word is None:
        word = str(getattr(work, "id", "")).replace("-", "")[:8]
    return f"{family}{year if year else 'nd'}{word[:10]}"


def _suffix(index: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa: letters only, so a suffixed key still reads as a key."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("a") + remainder) + letters
    return letters


def _fields(work: Any, authors: Sequence[str]) -> list[tuple[str, str]]:
    entry_fields: list[tuple[str, str]] = []
    if authors:
        entry_fields.append(("author", " and ".join("{" + escape_latex(a) + "}" for a in authors)))
    title = escape_latex(getattr(work, "title", None))
    if title:
        entry_fields.append(("title", "{" + title + "}"))
    _, venue_field, note = _entry_type(work)
    venue = _venue_name(work)
    if venue_field and venue:
        entry_fields.append((venue_field, escape_latex(venue)))
    year = getattr(work, "publication_year", None)
    if year:
        entry_fields.append(("year", str(year)))
    volume = escape_latex(getattr(work, "volume", None))
    if volume:
        entry_fields.append(("volume", volume))
    number = escape_latex(getattr(work, "issue", None))
    if number:
        entry_fields.append(("number", number))
    pages = _collapse(getattr(work, "page", None))
    if pages:
        entry_fields.append(("pages", escape_latex(_PAGE_RANGE.sub("--", pages))))
    doi = _identifier(getattr(work, "doi", None))
    if doi:
        entry_fields.append(("doi", doi))
    url = _identifier(getattr(work, "landing_page_url", None)) or (
        f"https://doi.org/{doi}" if doi else None
    )
    if url:
        entry_fields.append(("url", url))
    if note:
        entry_fields.append(("note", note))
    return entry_fields


def _render(key: str, work: Any, authors: Sequence[str]) -> str:
    entry_type, _, _ = _entry_type(work)
    entry_fields = _fields(work, authors)
    lines = [f"@{entry_type}{{{key},"]
    for index, (name, value) in enumerate(entry_fields):
        comma = "," if index < len(entry_fields) - 1 else ""
        lines.append(f"  {name} = {{{value}}}{comma}")
    lines.append("}")
    return "\n".join(lines)


def format_entries(works: Sequence[Any]) -> str:
    """BibTeX for the works, one entry each, in citation-key order. Empty input gives ''."""
    groups: dict[str, list[tuple[Any, list[str]]]] = {}
    for work in works:
        authors = ordered_author_names(work)
        groups.setdefault(_base_key(work, authors), []).append((work, authors))

    keyed: list[tuple[str, Any, list[str]]] = []
    used: set[str] = set()
    for base, members in groups.items():
        if len(members) == 1:
            keyed.append((base, *members[0]))
            used.add(base)
    for base in sorted(b for b, members in groups.items() if len(members) > 1):
        members = sorted(
            groups[base],
            key=lambda m: (_collapse(getattr(m[0], "title", None)).lower(), str(getattr(m[0], "id", ""))),
        )
        index = 0
        for work, authors in members:
            while base + _suffix(index) in used:
                index += 1
            key = base + _suffix(index)
            used.add(key)
            keyed.append((key, work, authors))
            index += 1

    keyed.sort(key=lambda entry: entry[0])
    if not keyed:
        return ""
    return "\n\n".join(_render(key, work, authors) for key, work, authors in keyed) + "\n"
