from dataclasses import dataclass


@dataclass(frozen=True)
class RawOpportunity:
    title: str
    source: str
    url: str


def fetch_sample_opportunities() -> list[RawOpportunity]:
    return [
        RawOpportunity(
            title="International Conference on AI Research",
            source="Sample CFP feed",
            url="https://example.com/cfp/ai-research",
        )
    ]
