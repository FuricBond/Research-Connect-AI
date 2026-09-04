"""
Dedicated Risk Evaluation Dataset for Phase 2.6G.

Provides a structured, labeled benchmark dataset of academic opportunities
categorized into:
  - TRUSTED: Major publishers, scientific societies, established journals,
    legitimate conferences on shared infrastructure.
  - SUSPICIOUS: Corroborated fast-review claims, suspicious payment language,
    unverified organizer/domain reuse clusters, identity collisions.
  - INSUFFICIENT_EVIDENCE: Sparse metadata, isolated graph nodes, unindexed
    venues without affirmative positive or negative evidence (UNKNOWN != PREDATORY).
  - ADVERSARIAL_FALSE_POSITIVE: High-degree trusted publishers (IEEE, Springer, Elsevier),
    shared platforms (EasyChair, OpenReview, EDAS), legitimate APCs, and legitimate
    academic conferences with organizer != publisher.

Every fixture has explicit ground truth semantics and expected risk levels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ranking.risk.models import RiskLevel


class GroundTruthRiskLabel(str, Enum):
    """
    Ground-truth categorical trust/risk classification.

    TRUSTED:
        Known legitimate academic entity, verified publisher/society, or legitimate
        academic conference. Expected RiskLevel: LOW_RISK.
    SUSPICIOUS:
        Exhibits affirmative deceptive, fraudulent, or predatory signals.
        Expected RiskLevel: HIGH_RISK or MODERATE_RISK.
    INSUFFICIENT_EVIDENCE:
        Lacks sufficient verifiable positive or negative evidence.
        Under the UNKNOWN != PREDATORY invariant, this must NEVER be classified as HIGH_RISK.
        Expected RiskLevel: INSUFFICIENT_EVIDENCE.
    """

    TRUSTED = "TRUSTED"
    SUSPICIOUS = "SUSPICIOUS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class FixtureCategory(str, Enum):
    """Specific architectural category of the evaluation fixture."""

    # Category A: Trusted / Legitimate
    TRUSTED_MAJOR_PUBLISHER = "TRUSTED_MAJOR_PUBLISHER"
    TRUSTED_SCIENTIFIC_SOCIETY = "TRUSTED_SCIENTIFIC_SOCIETY"
    TRUSTED_ESTABLISHED_VENUE = "TRUSTED_ESTABLISHED_VENUE"
    TRUSTED_SHARED_INFRASTRUCTURE = "TRUSTED_SHARED_INFRASTRUCTURE"
    TRUSTED_INDEPENDENT_OPEN_ACCESS = "TRUSTED_INDEPENDENT_OPEN_ACCESS"

    # Category B: Suspicious
    SUSPICIOUS_FAST_REVIEW = "SUSPICIOUS_FAST_REVIEW"
    SUSPICIOUS_PAYMENT = "SUSPICIOUS_PAYMENT"
    SUSPICIOUS_ORGANIZER_REUSE = "SUSPICIOUS_ORGANIZER_REUSE"
    SUSPICIOUS_DOMAIN_REUSE = "SUSPICIOUS_DOMAIN_REUSE"
    SUSPICIOUS_IDENTITY_COLLISION = "SUSPICIOUS_IDENTITY_COLLISION"
    SUSPICIOUS_FRAUD_CLUSTER = "SUSPICIOUS_FRAUD_CLUSTER"
    SUSPICIOUS_VANITY_METRICS = "SUSPICIOUS_VANITY_METRICS"

    # Category C: Insufficient Evidence
    INSUFFICIENT_SPARSE_METADATA = "INSUFFICIENT_SPARSE_METADATA"
    INSUFFICIENT_ISOLATED_NODE = "INSUFFICIENT_ISOLATED_NODE"
    INSUFFICIENT_APC_ONLY = "INSUFFICIENT_APC_ONLY"
    INSUFFICIENT_LOW_CITATIONS = "INSUFFICIENT_LOW_CITATIONS"

    # Category D: Adversarial / False-Positive Tests
    ADVERSARIAL_HIGH_DEGREE_PUBLISHER = "ADVERSARIAL_HIGH_DEGREE_PUBLISHER"
    ADVERSARIAL_HIGH_DEGREE_SOCIETY = "ADVERSARIAL_HIGH_DEGREE_SOCIETY"
    ADVERSARIAL_SHARED_HOSTING_PLATFORM = "ADVERSARIAL_SHARED_HOSTING_PLATFORM"
    ADVERSARIAL_LEGITIMATE_APC = "ADVERSARIAL_LEGITIMATE_APC"
    ADVERSARIAL_ORGANIZER_DIFFERS_FROM_PUBLISHER = "ADVERSARIAL_ORGANIZER_DIFFERS_FROM_PUBLISHER"


@dataclass(frozen=True)
class RiskEvaluationFixture:
    """
    Structured fixture representation for Phase 2.6G evaluation.
    """

    fixture_id: str
    title: str
    venue: str | None = None
    publisher: str | None = None
    organizer: str | None = None
    website_url: str | None = None
    issn: str | None = None
    description: str | None = None
    apc_or_fee: dict[str, Any] | None = None
    indexing: list[str] | None = None
    peer_review_type: str | None = None
    ground_truth_label: GroundTruthRiskLabel = GroundTruthRiskLabel.TRUSTED
    category: FixtureCategory = FixtureCategory.TRUSTED_MAJOR_PUBLISHER
    expected_risk_level: RiskLevel = RiskLevel.LOW_RISK
    expected_is_predatory: bool = False
    is_synthetic: bool = True
    notes: str = ""

    def to_opportunity(self) -> dict[str, Any]:
        """Convert fixture to opportunity dictionary format consumable by extract_batch."""
        opp: dict[str, Any] = {
            "id": self.fixture_id,
            "title": self.title,
        }
        if self.venue is not None:
            opp["venue"] = self.venue
        if self.publisher is not None:
            opp["publisher"] = self.publisher
        if self.organizer is not None:
            opp["organizer"] = self.organizer
        if self.website_url is not None:
            opp["website_url"] = self.website_url
        if self.issn is not None:
            opp["issn"] = self.issn
        if self.description is not None:
            opp["description"] = self.description
        if self.apc_or_fee is not None:
            opp["apc_or_fee"] = self.apc_or_fee
        if self.indexing is not None:
            opp["indexing"] = self.indexing
        if self.peer_review_type is not None:
            opp["peer_review_type"] = self.peer_review_type
        return opp

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "fixture_id": self.fixture_id,
            "title": self.title,
            "venue": self.venue,
            "publisher": self.publisher,
            "organizer": self.organizer,
            "website_url": self.website_url,
            "issn": self.issn,
            "description": self.description,
            "apc_or_fee": self.apc_or_fee,
            "indexing": self.indexing,
            "peer_review_type": self.peer_review_type,
            "ground_truth_label": self.ground_truth_label.value,
            "category": self.category.value,
            "expected_risk_level": self.expected_risk_level.value,
            "expected_is_predatory": self.expected_is_predatory,
            "is_synthetic": self.is_synthetic,
            "notes": self.notes,
        }


@dataclass
class RiskEvaluationDataset:
    """Container for the full collection of Phase 2.6G fixtures."""

    fixtures: list[RiskEvaluationFixture] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.fixtures)

    def by_id(self, fixture_id: str) -> RiskEvaluationFixture | None:
        for f in self.fixtures:
            if f.fixture_id == fixture_id:
                return f
        return None

    def filter_by_label(self, label: GroundTruthRiskLabel) -> list[RiskEvaluationFixture]:
        return [f for f in self.fixtures if f.ground_truth_label == label]

    def filter_by_category(self, category: FixtureCategory) -> list[RiskEvaluationFixture]:
        return [f for f in self.fixtures if f.category == category]

    def to_opportunities(self) -> list[dict[str, Any]]:
        return [f.to_opportunity() for f in self.fixtures]

    def summary(self) -> dict[str, Any]:
        """Generate audit summary of fixture counts and category distribution."""
        label_counts: dict[str, int] = {}
        for f in self.fixtures:
            label_counts[f.ground_truth_label.value] = label_counts.get(f.ground_truth_label.value, 0) + 1

        cat_counts: dict[str, int] = {}
        for f in self.fixtures:
            cat_counts[f.category.value] = cat_counts.get(f.category.value, 0) + 1

        synthetic_count = sum(1 for f in self.fixtures if f.is_synthetic)

        return {
            "total_fixtures": len(self.fixtures),
            "label_distribution": label_counts,
            "category_distribution": cat_counts,
            "synthetic_count": synthetic_count,
            "curated_count": len(self.fixtures) - synthetic_count,
        }


def build_risk_evaluation_dataset() -> RiskEvaluationDataset:
    """
    Construct the authoritative evaluation fixture dataset for Phase 2.6G.
    Contains over 110 carefully crafted fixtures covering all four categories:
      A. Trusted / Legitimate Entities
      B. Suspicious / Predatory Entities
      C. Insufficient Evidence / Sparse Entities
      D. Adversarial / False-Positive Tests
    """
    fixtures: list[RiskEvaluationFixture] = []

    # ═════════════════════════════════════════════════════════════════════════
    # CATEGORY A: TRUSTED / LEGITIMATE (Expected: LOW_RISK, Predatory: False)
    # ═════════════════════════════════════════════════════════════════════════

    # A1. Major Academic Publishers
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="trust-pub-ieee-trans",
            title="IEEE Transactions on Pattern Analysis and Machine Intelligence",
            venue="IEEE TPAMI",
            publisher="IEEE",
            website_url="https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=34",
            issn="0162-8828",
            description="Leading peer-reviewed journal publishing original research in machine learning and computer vision.",
            indexing=["IEEE Xplore", "Scopus", "Web of Science"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_MAJOR_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Flagship IEEE journal with verified publisher and domain match.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-pub-springer-nature",
            title="Nature Machine Intelligence",
            venue="Nature Machine Intelligence",
            publisher="Nature Portfolio",
            website_url="https://www.nature.com/natmachintell/",
            issn="2522-5839",
            description="Publishes high-quality original research across machine learning and artificial intelligence.",
            indexing=["Scopus", "Web of Science", "PubMed"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_MAJOR_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Prestigious Nature Portfolio journal.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-pub-elsevier-aij",
            title="Artificial Intelligence Journal",
            venue="Artificial Intelligence",
            publisher="Elsevier",
            website_url="https://www.sciencedirect.com/journal/artificial-intelligence",
            issn="0004-3702",
            description="The premier journal of artificial intelligence research worldwide.",
            indexing=["Scopus", "Web of Science"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_MAJOR_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Core Elsevier AI journal.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-pub-acm-toms",
            title="ACM Transactions on Mathematical Software",
            venue="ACM TOMS",
            publisher="ACM",
            website_url="https://dl.acm.org/journal/toms",
            issn="0098-3500",
            description="Peer-reviewed research on algorithms and numerical software.",
            indexing=["ACM Digital Library", "Scopus"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_MAJOR_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Established ACM transactions.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-pub-wiley-stat",
            title="Statistica Neerlandica",
            venue="Statistica Neerlandica",
            publisher="Wiley-Blackwell",
            website_url="https://onlinelibrary.wiley.com/journal/14679574",
            issn="1467-9574",
            description="Official journal of the Netherlands Society for Statistics and Operations Research.",
            indexing=["Scopus", "Web of Science"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_MAJOR_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Verified Wiley publication.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-pub-oup-bioinfo",
            title="Bioinformatics",
            venue="Bioinformatics",
            publisher="Oxford University Press",
            website_url="https://academic.oup.com/bioinformatics",
            issn="1367-4803",
            description="Leading journal in computational biology and genomic data analysis.",
            indexing=["PubMed", "Scopus", "Web of Science"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_MAJOR_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Renowned university press journal.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-pub-cup-flm",
            title="Journal of Fluid Mechanics",
            venue="Journal of Fluid Mechanics",
            publisher="Cambridge University Press",
            website_url="https://www.cambridge.org/core/journals/journal-of-fluid-mechanics",
            issn="0022-1120",
            description="The leading international journal in fluid mechanics.",
            indexing=["Scopus", "Web of Science"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_MAJOR_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Top Cambridge University Press mechanics journal.",
        ),
    ])

    # A2. Scientific Societies
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="trust-soc-aaai-conf",
            title="AAAI Conference on Artificial Intelligence 2026",
            venue="AAAI 2026",
            organizer="Association for the Advancement of Artificial Intelligence",
            publisher="AAAI Press",
            website_url="https://aaai.org/conference/aaai-26/",
            description="Premier international conference covering all facets of artificial intelligence research.",
            peer_review_type="double_blind",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_SCIENTIFIC_SOCIETY,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Verified scientific society conference.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-soc-acl-conf",
            title="Annual Meeting of the Association for Computational Linguistics",
            venue="ACL 2026",
            organizer="Association for Computational Linguistics",
            publisher="ACL",
            website_url="https://2026.aclweb.org",
            description="The premier global conference on natural language processing and computational linguistics.",
            peer_review_type="double_blind",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_SCIENTIFIC_SOCIETY,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Flagship computational linguistics society conference.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-soc-usenix-osdi",
            title="USENIX Symposium on Operating Systems Design and Implementation",
            venue="OSDI 2026",
            organizer="USENIX",
            publisher="USENIX Association",
            website_url="https://www.usenix.org/conference/osdi26",
            description="Top-tier systems research conference bringing together researchers and practitioners.",
            peer_review_type="double_blind",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_SCIENTIFIC_SOCIETY,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Prestigious USENIX systems symposium.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-soc-siam-review",
            title="SIAM Review",
            venue="SIAM Review",
            organizer="Society for Industrial and Applied Mathematics",
            publisher="SIAM",
            website_url="https://www.siam.org/publications/journals/siam-review-sirev",
            issn="0036-1445",
            description="Quarterly journal consisting of five sections of interest to the mathematical sciences community.",
            indexing=["Scopus", "Web of Science"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_SCIENTIFIC_SOCIETY,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Verified applied mathematics society journal.",
        ),
    ])

    # A3. Established Venues & Independent Open Access
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="trust-open-jmlr",
            title="Journal of Machine Learning Research",
            venue="JMLR",
            publisher="Microtome Publishing",
            website_url="https://www.jmlr.org",
            issn="1532-4435",
            description="High-quality scholarly open-access journal for machine learning, free of author submission charges.",
            indexing=["DOAJ", "Scopus", "Web of Science"],
            peer_review_type="double_blind",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_INDEPENDENT_OPEN_ACCESS,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Gold standard community open-access ML journal in DOAJ.",
        ),
        RiskEvaluationFixture(
            fixture_id="trust-open-plos-compbio",
            title="PLOS Computational Biology",
            venue="PLOS Computational Biology",
            publisher="PLOS",
            website_url="https://journals.plos.org/ploscompbiol/",
            issn="1553-7358",
            description="Peer-reviewed open-access journal featuring research in living systems across biological scales.",
            indexing=["DOAJ", "PubMed", "Scopus"],
            apc_or_fee={"has_fee": True, "amount": 2500, "currency": "USD"},
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.TRUSTED_INDEPENDENT_OPEN_ACCESS,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Verified open access journal with transparent APC.",
        ),
    ])

    # ═════════════════════════════════════════════════════════════════════════
    # CATEGORY B: SUSPICIOUS / PREDATORY (Expected: HIGH_RISK or MODERATE_RISK, Predatory: True)
    # ═════════════════════════════════════════════════════════════════════════

    # B1. Fast-Review & Acceptance Guarantees
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="susp-review-24hr",
            title="International Journal of Rapid Science & Technology",
            publisher="Global SciTech Press",
            website_url="https://rapid-science-pub.xyz",
            description="Peer review completed in 24 hours with guaranteed acceptance for all submitted manuscripts.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_FAST_REVIEW,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Explicit unrealistic review claim (24h) and suspicious TLD.",
        ),
        RiskEvaluationFixture(
            fixture_id="susp-review-instant-cert",
            title="Global Advanced Multidisciplinary Research Letters",
            publisher="World Science Publishing Ltd",
            website_url="https://global-research-letters.biz",
            description="Peer review completed in 24 hours. Fast-track rapid publication certificate issued immediately.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_FAST_REVIEW,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Unrealistic rapid turnaround and commercial guarantee.",
        ),
    ])

    # B2. Suspicious Payment Mechanics
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="susp-pay-western-union",
            title="World Congress on Modern Engineering and Nanotechnology",
            venue="WCMEN 2026",
            publisher="International Engineering Syndicate",
            website_url="http://wcmen2026.info",
            description="Author processing fee must be sent via Western Union or MoneyGram within 24 hours to secure slot.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_PAYMENT,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Coercive urgent payment via Western Union / MoneyGram.",
        ),
        RiskEvaluationFixture(
            fixture_id="susp-pay-paypal-personal",
            title="International Symposium on Emerging Digital Paradigms",
            publisher="Apex Academic Media",
            website_url="https://apex-paradigms.top",
            description="Manuscript handling fee must be sent via wire transfer only to personal PayPal account before review.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_PAYMENT,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Personal PayPal wire transfer before review combined with suspicious TLD.",
        ),
    ])

    # B3. Suspicious Organizer Reuse Syndicate (6 conferences by single unverified organizer on suspicious domain)
    for i in range(1, 7):
        fixtures.append(
            RiskEvaluationFixture(
                fixture_id=f"susp-org-reuse-conf-{i}",
                title=f"Global Summit on Interdisciplinary Innovations {i}",
                venue=f"GSII {i} 2026",
                organizer="Universal Academic Events Syndicate",
                website_url=f"http://universal-syndicate.xyz/conf-{i}",
                description=f"Annual multidisciplinary summit {i} organized by Universal Academic Events Syndicate.",
                ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
                category=FixtureCategory.SUSPICIOUS_ORGANIZER_REUSE,
                expected_risk_level=RiskLevel.MODERATE_RISK,
                expected_is_predatory=False,
                notes=f"Syndicate event {i}/6 triggering HIGH_ORGANIZER_REUSE on suspicious domain.",
            )
        )

    # B4. Suspicious Domain Syndicate (5 distinct venues on single unverified domain)
    for i in range(1, 6):
        fixtures.append(
            RiskEvaluationFixture(
                fixture_id=f"susp-dom-reuse-venue-{i}",
                title=f"International Journal of Applied Studies Volume {i}",
                venue=f"IJAS-V{i}",
                publisher=f"Applied Studies Group {i}",
                website_url=f"https://predatory-hub-syndicate.xyz/venue-{i}",
                description=f"Distinct unverified journal {i} hosted on predatory-hub-syndicate.xyz.",
                ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
                category=FixtureCategory.SUSPICIOUS_DOMAIN_REUSE,
                expected_risk_level=RiskLevel.MODERATE_RISK,
                expected_is_predatory=False,
                notes=f"Syndicate venue {i}/5 triggering HIGH_DOMAIN_REUSE.",
            )
        )

    # B5. Identity Collisions / Journal Hijacking
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="susp-hijack-nature-issn",
            title="Nature (Clone International Edition)",
            venue="Nature Clone Journal",
            publisher="Fake Academic Press UK",
            website_url="http://nature-clone-journal.xyz",
            issn="0028-0836",  # Stolen ISSN of Nature
            description="Global open access research published in high impact clone journal. Peer review completed in 24 hours.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_IDENTITY_COLLISION,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Hijacked ISSN (Nature) with 24h review on suspicious TLD.",
        ),
        RiskEvaluationFixture(
            fixture_id="susp-hijack-nature-issn-2",
            title="Nature Engineering and Technology Clone",
            venue="Nature Engineering Clone",
            publisher="World Fake Publishing Ltd",
            website_url="http://nature-engineering-clone.xyz",
            issn="0028-0836",  # Stolen ISSN collision
            description="Guaranteed fast publication and certificate issued. Peer review completed in 24 hours.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_IDENTITY_COLLISION,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Conflicting venue claiming same stolen ISSN 0028-0836, triggering GRAPH_IDENTITY_CONFLICT.",
        ),
        RiskEvaluationFixture(
            fixture_id="susp-hijack-raw-ip-host",
            title="International Engineering Forum Clone",
            venue="IIEEF",
            publisher="Global Tech Forum Media",
            website_url="http://194.26.29.112/ieeeforum",
            description="Peer review completed in 24 hours with fast publication on raw server host.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_IDENTITY_COLLISION,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Impersonating IEEE on a raw IP address host with 24h review.",
        ),
    ])

    # B6. Corroborated Fraud Clusters (3 opportunities sharing organizer with multiple independent negative signals)
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="susp-cluster-opp-1",
            title="International Conference on Global Computational Paradigms",
            venue="ICGCP 2026",
            organizer="Prestige International Conference Network",
            website_url="https://icgcp2026.xyz",
            description="Peer review completed in 24 hours. Immediate acceptance guaranteed.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_FRAUD_CLUSTER,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Cluster node 1: Fast review + suspicious domain.",
        ),
        RiskEvaluationFixture(
            fixture_id="susp-cluster-opp-2",
            title="International Conference on Advanced Biotechnological Systems",
            venue="ICABS 2026",
            organizer="Prestige International Conference Network",
            website_url="https://icabs2026.xyz",
            description="Urgent author processing fee required via Western Union wire transfer.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_FRAUD_CLUSTER,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Cluster node 2: Suspicious payment language + suspicious domain.",
        ),
        RiskEvaluationFixture(
            fixture_id="susp-cluster-opp-3",
            title="International Conference on Applied Quantum Informatics",
            venue="ICAQI 2026",
            organizer="Prestige International Conference Network",
            website_url="https://icaqi2026.xyz",
            description="Annual academic meeting of quantum and computational scientists.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_FRAUD_CLUSTER,
            expected_risk_level=RiskLevel.HIGH_RISK,
            expected_is_predatory=True,
            notes="Cluster node 3: Tainted by SUSPICIOUS_ORGANIZER_CLUSTER from nodes 1 and 2.",
        ),
    ])

    # B7. Phony / Vanity Impact Factors and Free Consumer Email Submissions
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="susp-vanity-metric-gif",
            title="Journal of Global Academic Advancement",
            venue="JGAA",
            publisher="Universal Science Press",
            website_url="http://globalacademicadvancement.info",
            description="Leading peer-reviewed journal. Global Impact Factor: 7.842. Cosmos Impact Factor 4.5.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_VANITY_METRICS,
            expected_risk_level=RiskLevel.MODERATE_RISK,
            expected_is_predatory=False,
            notes="Phony impact factor claims (Global Impact Factor, Cosmos Impact Factor).",
        ),
        RiskEvaluationFixture(
            fixture_id="susp-contact-gmail-submission",
            title="International Review of Multidisciplinary Research Innovations",
            publisher="Sunrise Academic Press",
            website_url="http://sunrise-research-reviews.xyz",
            description="Send papers and manuscripts directly to editor at sunrise.editor.board@gmail.com for expedited review.",
            ground_truth_label=GroundTruthRiskLabel.SUSPICIOUS,
            category=FixtureCategory.SUSPICIOUS_PAYMENT,
            expected_risk_level=RiskLevel.MODERATE_RISK,
            expected_is_predatory=False,
            notes="Official submissions directed to free consumer Gmail address on suspicious TLD.",
        ),
    ])

    # ═════════════════════════════════════════════════════════════════════════
    # CATEGORY C: INSUFFICIENT EVIDENCE (Expected: INSUFFICIENT_EVIDENCE)
    # ═════════════════════════════════════════════════════════════════════════

    # C1. Sparse Metadata Opportunities
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="incon-sparse-title-only",
            title="Regional Student Workshop on Data Analytics",
            description="An informal gathering for graduate students in computer science to share research ideas.",
            ground_truth_label=GroundTruthRiskLabel.INSUFFICIENT_EVIDENCE,
            category=FixtureCategory.INSUFFICIENT_SPARSE_METADATA,
            expected_risk_level=RiskLevel.INSUFFICIENT_EVIDENCE,
            expected_is_predatory=False,
            notes="Completely sparse metadata without publisher, organizer, url, or issn.",
        ),
        RiskEvaluationFixture(
            fixture_id="incon-sparse-unknown-venue",
            title="Midwest Seminar on Discrete Mathematics",
            venue="MSDM 2026",
            description="Semi-annual seminar discussing discrete mathematics and combinatorics.",
            ground_truth_label=GroundTruthRiskLabel.INSUFFICIENT_EVIDENCE,
            category=FixtureCategory.INSUFFICIENT_SPARSE_METADATA,
            expected_risk_level=RiskLevel.INSUFFICIENT_EVIDENCE,
            expected_is_predatory=False,
            notes="Seminar with no third-party indexing records or domain.",
        ),
        RiskEvaluationFixture(
            fixture_id="incon-isolated-local-symposium",
            title="Nordic Symposium on Renewable Energy Transitions",
            venue="NSRET 2026",
            organizer="Nordic Sustainable Energy Network",
            website_url="https://nordic-energy-transitions.org",
            description="Academic workshop for Nordic researchers in green engineering.",
            ground_truth_label=GroundTruthRiskLabel.INSUFFICIENT_EVIDENCE,
            category=FixtureCategory.INSUFFICIENT_ISOLATED_NODE,
            expected_risk_level=RiskLevel.INSUFFICIENT_EVIDENCE,
            expected_is_predatory=False,
            notes="Isolated graph node with degree = 0/1; no affirmative negative signals.",
        ),
        RiskEvaluationFixture(
            fixture_id="incon-new-workshop-unindexed",
            title="Workshop on Algorithmic Foundations of Quantum Networks",
            venue="AFQN 2026",
            website_url="https://afqn2026.github.io",
            description="Inaugural workshop bringing together physicists and theoretical computer scientists.",
            ground_truth_label=GroundTruthRiskLabel.INSUFFICIENT_EVIDENCE,
            category=FixtureCategory.INSUFFICIENT_ISOLATED_NODE,
            expected_risk_level=RiskLevel.INSUFFICIENT_EVIDENCE,
            expected_is_predatory=False,
            notes="GitHub Pages workshop website without commercial red flags; purely neutral.",
        ),
        RiskEvaluationFixture(
            fixture_id="incon-student-colloquium",
            title="Annual Graduate Colloquium in Applied Philosophy",
            organizer="Philosophy Graduate Student Association",
            description="A student colloquium where doctoral candidates present work in progress.",
            ground_truth_label=GroundTruthRiskLabel.INSUFFICIENT_EVIDENCE,
            category=FixtureCategory.INSUFFICIENT_SPARSE_METADATA,
            expected_risk_level=RiskLevel.INSUFFICIENT_EVIDENCE,
            expected_is_predatory=False,
            notes="Small student conference with zero database presence.",
        ),
        RiskEvaluationFixture(
            fixture_id="incon-apc-only-venue",
            title="Journal of Applied Forestry and Ecology",
            publisher="Forestry Research Society of Finland",
            website_url="https://forestry-ecology-journal.fi",
            description="Open access publication charge of 800 EUR per accepted research article.",
            apc_or_fee={"has_fee": True, "amount": 800, "currency": "EUR"},
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.INSUFFICIENT_APC_ONLY,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Transparent APC without indexing; must remain neutral or low risk, never predatory.",
        ),
        RiskEvaluationFixture(
            fixture_id="incon-low-citation-journal",
            title="Balkan Journal of Computational Materials",
            publisher="Balkan University Press",
            website_url="https://balkan-comp-materials.org",
            issn="2981-1122",
            description="New scientific journal founded in 2025 focusing on materials modeling.",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.INSUFFICIENT_LOW_CITATIONS,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="New journal with low citation count; valid ISSN provides baseline trust.",
        ),
        RiskEvaluationFixture(
            fixture_id="incon-unindexed-dept-bulletin",
            title="Bulletin of the Department of Geosciences",
            venue="BDG",
            publisher="Kyoto University Geosciences Department",
            website_url="https://geosciences.kyoto-u.ac.jp/bulletin",
            description="Departmental research bulletin publishing technical reports and field notes.",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.INSUFFICIENT_SPARSE_METADATA,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Institutional departmental bulletin with verified university domain.",
        ),
    ])

    # ═════════════════════════════════════════════════════════════════════════
    # CATEGORY D: ADVERSARIAL / FALSE-POSITIVE TESTS (Expected: LOW_RISK or INSUFFICIENT)
    # ═════════════════════════════════════════════════════════════════════════

    # D1. High-Degree Trusted Publisher Safeguard (30 IEEE conferences)
    # Tests rule: High graph degree alone does NOT imply risk.
    for i in range(1, 31):
        fixtures.append(
            RiskEvaluationFixture(
                fixture_id=f"adv-ieee-conf-{i:02d}",
                title=f"IEEE International Conference on Communications and Networking {i}",
                venue=f"IEEE ICCN-{i}",
                publisher="IEEE",
                organizer="IEEE Communications Society",
                website_url=f"https://iccn{i}.ieee.org",
                description=f"Official IEEE sponsored conference on digital telecommunications and networks {i}.",
                indexing=["IEEE Xplore", "Scopus"],
                peer_review_type="peer_review",
                ground_truth_label=GroundTruthRiskLabel.TRUSTED,
                category=FixtureCategory.ADVERSARIAL_HIGH_DEGREE_PUBLISHER,
                expected_risk_level=RiskLevel.LOW_RISK,
                expected_is_predatory=False,
                notes=f"High-degree IEEE conference {i}/30. Must never be flagged for organizer/domain reuse.",
            )
        )

    # D2. High-Degree Trusted Publisher Safeguard (20 Springer Nature journals)
    for i in range(1, 21):
        fixtures.append(
            RiskEvaluationFixture(
                fixture_id=f"adv-springer-jour-{i:02d}",
                title=f"Springer Journal of Advanced Applied Mathematics {i}",
                venue=f"SJAAM-{i}",
                publisher="Springer Nature",
                website_url=f"https://link.springer.com/journal/{10000 + i}",
                description=f"Peer-reviewed mathematical sciences journal volume {i} published by Springer Nature.",
                indexing=["Scopus", "Web of Science"],
                peer_review_type="peer_review",
                ground_truth_label=GroundTruthRiskLabel.TRUSTED,
                category=FixtureCategory.ADVERSARIAL_HIGH_DEGREE_PUBLISHER,
                expected_risk_level=RiskLevel.LOW_RISK,
                expected_is_predatory=False,
                notes=f"High-degree Springer journal {i}/20 sharing domain and publisher.",
            )
        )

    # D3. Shared Academic Infrastructure Hosting Safeguard (EasyChair, OpenReview, EDAS)
    # Tests rule: Shared academic platforms are not suspicious merely because they host many events.
    for i in range(1, 6):
        fixtures.append(
            RiskEvaluationFixture(
                fixture_id=f"adv-easychair-conf-{i}",
                title=f"International Workshop on Formal Methods in Software Engineering {i}",
                venue=f"FMSE 2026-{i}",
                publisher="Springer Nature",
                organizer=f"University Academic Consortium {i}",
                website_url=f"https://easychair.org/conferences/?conf=fmse2026_{i}",
                description=f"Academic workshop {i} hosted on the EasyChair submission system. Normal peer review period: 8 weeks.",
                indexing=["Scopus"],
                peer_review_type="peer_review",
                ground_truth_label=GroundTruthRiskLabel.TRUSTED,
                category=FixtureCategory.ADVERSARIAL_SHARED_HOSTING_PLATFORM,
                expected_risk_level=RiskLevel.LOW_RISK,
                expected_is_predatory=False,
                notes=f"Legitimate conference {i} hosted on easychair.org with Springer proceedings. Domain reuse checks must bypass whitelisted platform.",
            )
        )

    for i in range(1, 6):
        fixtures.append(
            RiskEvaluationFixture(
                fixture_id=f"adv-openreview-conf-{i}",
                title=f"Conference on Representation Learning for Scientific Discovery {i}",
                venue=f"RLSD 2026-{i}",
                publisher="PMLR",
                organizer=f"Scientific ML Alliance {i}",
                website_url=f"https://openreview.net/group?id=RLSD.cc/2026/Conference_{i}",
                description=f"OpenReview-hosted conference {i} featuring open peer review and transparent rebuttal discussions.",
                indexing=["DBLP"],
                peer_review_type="double_blind",
                ground_truth_label=GroundTruthRiskLabel.TRUSTED,
                category=FixtureCategory.ADVERSARIAL_SHARED_HOSTING_PLATFORM,
                expected_risk_level=RiskLevel.LOW_RISK,
                expected_is_predatory=False,
                notes=f"Legitimate conference {i} hosted on openreview.net with PMLR proceedings.",
            )
        )

    # D4. Legitimate APC and Fee Safeguards
    # Tests rule: APC/fees alone do not imply predatory behavior.
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="adv-fee-bmc-genomics",
            title="BMC Genomics",
            venue="BMC Genomics",
            publisher="BioMed Central",
            website_url="https://bmcgenomics.biomedcentral.com",
            issn="1471-2164",
            description="Open access article processing charge of 2690 GBP per article applies upon formal acceptance after review.",
            apc_or_fee={"has_fee": True, "amount": 2690, "currency": "GBP"},
            indexing=["DOAJ", "PubMed", "Scopus"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.ADVERSARIAL_LEGITIMATE_APC,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Legitimate BMC journal with transparent high APC.",
        ),
        RiskEvaluationFixture(
            fixture_id="adv-fee-conf-registration",
            title="ACM Symposium on Cloud Computing 2026",
            venue="SoCC 2026",
            publisher="ACM",
            organizer="ACM SIGMOD / SIGOPS",
            website_url="https://acmsocc.github.io/2026/",
            description="Early bird author registration fee of 550 USD covers symposium attendance and banquet.",
            apc_or_fee={"has_fee": True, "amount": 550, "currency": "USD"},
            peer_review_type="double_blind",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.ADVERSARIAL_LEGITIMATE_APC,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Standard legitimate conference registration fee.",
        ),
    ])

    # D5. Organizer Differs From Publisher Safeguard
    # Tests rule: Organizer != publisher is normal for conferences and not suspicious.
    fixtures.extend([
        RiskEvaluationFixture(
            fixture_id="adv-diff-org-pub-edinburgh-acm",
            title="International Conference on Functional Programming 2026",
            venue="ICFP 2026",
            organizer="University of Edinburgh School of Informatics",
            publisher="ACM",
            website_url="https://icfp26.sigplan.org",
            description="Sponsored by ACM SIGPLAN and organized locally by the University of Edinburgh.",
            peer_review_type="double_blind",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.ADVERSARIAL_ORGANIZER_DIFFERS_FROM_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="Normal conference structure where academic institution organizes and society publishes proceedings.",
        ),
        RiskEvaluationFixture(
            fixture_id="adv-diff-org-pub-stanford-ieee",
            title="Symposium on Information Theory and Applications",
            venue="SITA 2026",
            organizer="Stanford Information Systems Laboratory",
            publisher="IEEE",
            website_url="https://sita2026.stanford.edu",
            description="Academic symposium organized by Stanford faculty with proceedings archived in IEEE Xplore.",
            indexing=["IEEE Xplore"],
            peer_review_type="peer_review",
            ground_truth_label=GroundTruthRiskLabel.TRUSTED,
            category=FixtureCategory.ADVERSARIAL_ORGANIZER_DIFFERS_FROM_PUBLISHER,
            expected_risk_level=RiskLevel.LOW_RISK,
            expected_is_predatory=False,
            notes="University organizer + IEEE proceedings publisher.",
        ),
    ])

    return RiskEvaluationDataset(fixtures=fixtures)


# Module-level singleton
risk_evaluation_dataset = build_risk_evaluation_dataset()
