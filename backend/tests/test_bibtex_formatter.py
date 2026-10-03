"""
Phase 5.14 — BibTeX formatter.

The formatter is pure, so these tests build plain objects with the attributes it reads instead
of database rows. They pin the entry types, the citation key rule and its collision suffixes,
LaTeX escaping, the brace-protected title, author order, missing data, and byte-identical output
for identical input in any order.
"""
from __future__ import annotations

from types import SimpleNamespace
import uuid

import pytest

from app.services.bibtex_formatter import escape_latex, format_entries


def _author(name: str, position: str | None, researcher_id: int) -> SimpleNamespace:
    rid = uuid.UUID(int=researcher_id)
    return SimpleNamespace(
        author_position=position,
        researcher_id=rid,
        researcher=SimpleNamespace(id=rid, display_name=name),
    )


def _work(
    title: str = "A Sketch of the Analytical Engine",
    *,
    authors: list[SimpleNamespace] | None = None,
    year: int | None = 1843,
    work_type: str | None = "article",
    venue: str | None = "Scientific Memoirs",
    source_type: str | None = "journal",
    work_id: int = 1,
    **extra,
) -> SimpleNamespace:
    source = (
        SimpleNamespace(display_name=venue, source_type=source_type)
        if venue is not None or source_type is not None
        else None
    )
    fields = dict(
        id=uuid.UUID(int=work_id),
        title=title,
        publication_year=year,
        work_type=work_type,
        primary_source=source,
        author_links=authors if authors is not None else [_author("Ada Lovelace", "first", 1)],
        doi=None,
        landing_page_url=None,
        volume=None,
        issue=None,
        page=None,
    )
    fields.update(extra)
    return SimpleNamespace(**fields)


def test_a_complete_article_entry():
    work = _work(
        authors=[_author("Charles Babbage", "last", 2), _author("Ada Lovelace", "first", 1)],
        volume="3",
        issue="2",
        page="666-731",
        doi="10.1000/sketch",
        landing_page_url="https://example.org/sketch",
    )

    assert format_entries([work]) == (
        "@article{lovelace1843sketch,\n"
        "  author = {{Ada Lovelace} and {Charles Babbage}},\n"
        "  title = {{A Sketch of the Analytical Engine}},\n"
        "  journal = {Scientific Memoirs},\n"
        "  year = {1843},\n"
        "  volume = {3},\n"
        "  number = {2},\n"
        "  pages = {666--731},\n"
        "  doi = {10.1000/sketch},\n"
        "  url = {https://example.org/sketch}\n"
        "}\n"
    )


@pytest.mark.parametrize(
    ("work_type", "source_type", "entry_type", "venue_field"),
    [
        ("article", "journal", "@article{", "journal"),
        ("journal-article", "journal", "@article{", "journal"),
        ("journal_article", "journal", "@article{", "journal"),
        ("proceedings-article", "journal", "@inproceedings{", "booktitle"),
        ("conference-paper", None, "@inproceedings{", "booktitle"),
        ("article", "conference", "@inproceedings{", "booktitle"),
        ("book-chapter", "book series", "@incollection{", "booktitle"),
        ("book", "book series", "@book{", None),
        ("monograph", None, "@book{", None),
        ("dissertation", "repository", "@phdthesis{", None),
        ("preprint", "repository", "@misc{", "howpublished"),
        ("posted-content", "repository", "@misc{", "howpublished"),
        ("dataset", "repository", "@misc{", "howpublished"),
        (None, None, "@misc{", "howpublished"),
    ],
)
def test_entry_types(work_type, source_type, entry_type, venue_field):
    output = format_entries([_work(work_type=work_type, source_type=source_type, venue="Venue")])

    assert output.startswith(entry_type)
    for field in ("journal", "booktitle", "howpublished"):
        assert (f"  {field} = {{Venue}}" in output) == (field == venue_field)


def test_preprints_carry_a_note():
    output = format_entries([_work(work_type="preprint", venue="arXiv", source_type="repository")])
    assert output.endswith("  note = {Preprint}\n}\n")
    assert "note" not in format_entries([_work(work_type="article")])


def test_key_folds_accents_and_cuts_the_title_word():
    work = _work("Transformational grammars", authors=[_author("Kurt Gödel", "first", 1)], year=1931)
    assert format_entries([work]).startswith("@article{godel1931transforma,")


def test_key_without_author_year_or_title_word():
    work = _work("The Of And", authors=[], year=None, work_id=0xABCDEF12 << 96)
    assert format_entries([work]).startswith("@article{anonndabcdef12,")


def test_colliding_keys_get_suffixes_in_title_then_id_order():
    shared = dict(authors=[_author("Ada Lovelace", "first", 1)], year=1843)
    zebra = _work("Sketch zebra", work_id=1, doi="10.1/one", **shared)
    alpha = _work("Sketch alpha", work_id=2, doi="10.1/two", **shared)
    alpha_twin = _work("Sketch alpha", work_id=3, doi="10.1/three", **shared)

    output = format_entries([zebra, alpha_twin, alpha])

    keys = [line.split("{", 1)[1].rstrip(",") for line in output.splitlines() if line.startswith("@")]
    assert keys == ["lovelace1843sketcha", "lovelace1843sketchb", "lovelace1843sketchc"]
    entries = output.split("\n\n")
    # Same title: the lower work id takes the earlier suffix. Then titles in order.
    assert "10.1/two" in entries[0]
    assert "10.1/three" in entries[1]
    assert "Sketch zebra" in entries[2]


def test_a_unique_key_is_not_suffixed():
    output = format_entries([_work("Sketch", work_id=1), _work("Engine", work_id=2)])
    keys = [line for line in output.splitlines() if line.startswith("@")]
    assert keys == ["@article{lovelace1843engine,", "@article{lovelace1843sketch,"]


def test_latex_specials_are_escaped_and_whitespace_collapsed():
    assert escape_latex("50%  of R&D_costs {x}\n#1 $5 ~ ^ \\") == (
        r"50\% of R\&D\_costs \{x\} \#1 \$5 \textasciitilde{} \textasciicircum{} \textbackslash{}"
    )

    output = format_entries([_work("Costs & Benefits of 100%   Recall", venue="Journal of R&D")])
    assert "  title = {{Costs \\& Benefits of 100\\% Recall}},\n" in output
    assert "  journal = {Journal of R\\&D},\n" in output


def test_the_title_is_brace_protected():
    output = format_entries([_work("BERT for IR")])
    assert "  title = {{BERT for IR}}," in output


def test_authors_are_ordered_first_middle_last_unknown_then_by_name():
    authors = [
        _author("Zed Unknown", None, 9),
        _author("Last Author", "last", 5),
        _author("Bea Middle", "middle", 4),
        _author("Abe Middle", "middle", 3),
        _author("Same Name", "middle", 7),
        _author("Same Name", "middle", 6),
        _author("First Author", "first", 1),
    ]
    output = format_entries([_work(authors=authors)])

    assert (
        "  author = {{First Author} and {Abe Middle} and {Bea Middle} and {Same Name} and "
        "{Same Name} and {Last Author} and {Zed Unknown}},\n"
    ) in output
    assert output.startswith("@article{author1843sketch,")


def test_a_missing_year_is_omitted():
    output = format_entries([_work(year=None)])
    assert output.startswith("@article{lovelacendsketch,")
    assert "year" not in output


def test_doi_becomes_the_url_without_a_landing_page():
    output = format_entries([_work(doi="10.1000/x_y")])
    assert "  doi = {10.1000/x_y},\n" in output, "identifiers are not LaTeX-escaped"
    assert "  url = {https://doi.org/10.1000/x_y}\n" in output

    no_ids = format_entries([_work()])
    assert "doi" not in no_ids and "url" not in no_ids


def test_entries_are_separated_by_a_blank_line_and_end_with_a_newline():
    output = format_entries([_work("First paper", work_id=1), _work("Second paper", work_id=2)])
    assert output.count("\n\n") == 1
    assert output.endswith("}\n")
    assert format_entries([]) == ""


def test_identical_input_gives_byte_identical_output_in_any_order():
    works = [
        _work("Second paper", authors=[_author("Bo Li", "first", 2)], year=2024, work_id=2, doi="10.1/b"),
        _work("First paper", work_id=1, page="1 - 9"),
        _work("Third paper", authors=[], year=None, work_id=3, work_type="preprint"),
    ]

    first = format_entries(works)
    again = format_entries(works)
    reversed_order = format_entries(list(reversed(works)))

    assert first.encode("utf-8") == again.encode("utf-8") == reversed_order.encode("utf-8")
    assert "  pages = {1--9}\n}" in first, "the last field has no trailing comma"
