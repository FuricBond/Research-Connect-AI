from scrapers.sources.sample_source import RawOpportunity


def normalize_opportunity(raw: RawOpportunity) -> dict[str, str]:
    return {
        "title": raw.title.strip(),
        "source": raw.source.strip(),
        "url": raw.url.strip(),
        "opportunity_type": "conference",
    }
