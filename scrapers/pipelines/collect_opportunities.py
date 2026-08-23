from scrapers.parsers.opportunity_parser import normalize_opportunity
from scrapers.sources.sample_source import fetch_sample_opportunities


def collect_opportunities() -> list[dict[str, str]]:
    return [
        normalize_opportunity(raw_opportunity)
        for raw_opportunity in fetch_sample_opportunities()
    ]
