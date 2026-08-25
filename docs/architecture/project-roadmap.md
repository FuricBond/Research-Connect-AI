# ResearchConnect AI — Development Roadmap

This document outlines the planned architecture and modular development roadmap for **ResearchConnect AI**. The project follows a clean, maintainable modular structure designed for a collaborative final-year project team, avoiding unnecessary distributed systems or MLOps overhead while maintaining high code quality and clear separation of concerns.

### Implementation Status:
- **Phase 1 (Foundation)**: COMPLETE (PostgreSQL + pgvector, core models, opportunity API)
- **Phase 2.1 (Ingestion Hardening)**: COMPLETE (WikiCFP source, validation, deduplication, change detection, audit tracking)
- **Phase 2.2A (Research Knowledge - OpenAlex)**: COMPLETE (OpenAlex API, research_works, researchers, research_sources, institutions)
- **Phase 2.2B (Research Knowledge - Crossref)**: COMPLETE (Crossref API, DOI canonicalization, non-destructive matching & enrichment, citation fields)
- **Phase 2.3A (Topic & Taxonomy Intelligence)**: COMPLETE (Canonical taxonomy DAG, aliases, OpenAlex/Crossref mapping, deterministic keyword extraction, multi-evidence scoring)

---

## 1. Data & Discovery
Focuses on acquiring, sanitizing, and maintaining accurate, fresh data on academic and research opportunities across various publication venues.

- **Conference Discovery**: Automated discovery and indexing of peer-reviewed conferences across disciplines.
- **Journal Discovery**: Identification of academic journals with verified indexing details and publication cycles.
- **CFP & Workshop Discovery**: Tracking of special calls for papers (CFPs), symposiums, and workshop deadlines.
- **Web Scraping**: Resilient data scrapers using `Requests` and `BeautifulSoup` (with `Playwright` reserved for JavaScript-heavy pages).
- **Data Cleaning**: Stripping formatting artifacts, noise, invalid HTML, and normalizing date/text formats.
- **Normalization**: Standardizing opportunity metadata (dates, topics, venue types, submission URLs) into consistent schemas.
- **Validation**: Schema-level validation and completeness checks before ingestion into the primary database.
- **Duplicate Detection**: Identifying overlapping submissions or duplicate listings across multiple feeds.
- **Change Detection**: Detecting revisions in deadlines, venue locations, or submission guidelines.
- **Data Freshness**: Routine checks and TTL management to archive expired opportunities.
- **Source Reliability**: Tracking and rating the historical accuracy and uptime of source feeds.

---

## 2. Research Intelligence
Extracts contextual understanding from user inputs (abstracts, drafts, profiles) and research domain taxonomies.

- **Research Profile**: Structured user profile capturing current domains, methodologies, publications, and interests.
- **Research Topic Extraction**: Semantic topic identification from uploaded abstracts or research summaries.
- **Abstract Analysis**: Deep parsing of manuscript drafts or abstracts to extract core themes and contributions.
- **Keyword Extraction**: Automated extraction of domain-specific keywords and phrases.
- **Domain/Sub-Domain Classification**: Hierarchical categorization of research areas (e.g., Computer Science -> NLP -> Information Retrieval).
- **Literature Discovery**: Contextual suggestions of relevant prior work and foundational literature.
- **Research Trend Analysis**: Identifying trending research topics and emerging themes across venues.
- **Research Gap Suggestions**: Identifying under-explored niches and potential intersections in chosen topics.
- **Research Roadmap**: Generating step-by-step milestones for manuscript preparation and targeted submission.

---

## 3. AI Recommendation
Provides explainable, ranked recommendations matching research profiles to appropriate venues and opportunities.

- **Semantic Recommendation**: Vector similarity search using `pgvector` and domain-tuned embedding models.
- **Conference Recommendation**: Matching manuscript topics and readiness to appropriate conference tracks.
- **Journal Recommendation**: Matching paper scope, turnaround time, and impact factor expectations to journal profiles.
- **Best Venue Recommendation**: Multi-criteria ranking identifying optimal submission targets.
- **Recommendation Ranking**: Combining semantic similarity, deadline proximity, and domain match into a unified score.
- **Personalized Recommendation**: Adapting results to individual researcher stage, past submissions, and preferences.
- **Opportunity Comparison**: Side-by-side comparative analysis of candidate venues (acceptance rates, indexing, deadlines).
- **Recommendation Feedback**: Capturing explicit user feedback (save, dismiss, irrelevant) to refine future rankings.
- **Explainable Recommendations**: Transparent rationales detailing *why* a specific venue or opportunity was recommended.

---

## 4. Trust & Quality
Ensures students and researchers avoid predatory or substandard publication venues through transparent risk analysis.

- **Predatory/Suspicious Opportunity Detection**: Heuristic and pattern-based identification of predatory conferences and journals.
- **Risk Scoring**: Composite risk ratings based on transparency indicators, editorial board checks, and domain reputation.
- **Publisher/Indexing Verification**: Cross-referencing indexing claims (e.g., Scopus, Web of Science, IEEE, ACM, Springer, DOAJ).
- **Explanation of Risk Signals**: Clear, actionable warnings detailing flagged concerns (e.g., suspiciously short review times, vanity metrics).

---

## 5. Research Management
Empowers researchers to organize deadlines, track submissions, and manage applications seamlessly.

- **Saved Opportunities**: Bookmarking and custom categorization of relevant calls and venues.
- **Submission Tracker**: Kanban or status-driven tracking of paper drafts, submissions, revisions, and acceptances.
- **Application History**: Audit log of historical submissions and outcomes for personal reporting.
- **Recommendation History**: Log of past recommendations with historical match parameters.
- **Deadline Intelligence**: Smart countdowns, timezone conversions, and deadline warning indicators.
- **Calendar**: Interactive calendar view with exportable feeds (iCal/Google Calendar).
- **Notifications**: Email and in-app alerts for approaching deadlines, date changes, or newly matched opportunities.

---

## 6. Community
Facilitates institutional and cross-disciplinary academic collaboration within the platform.

- **Faculty Opportunities**: Listings posted by university faculty for open research slots.
- **Research Projects**: Collaborative multi-student or inter-departmental project postings.
- **Research Internships**: Curated industry and academic research internship openings.
- **Research Assistant Opportunities**: Formal RA openings for undergraduate and postgraduate students.

---

## 7. Platform
Core system infrastructure, user interfaces, access control, and deployment operations.

- **Student Portal**: Tailored view for undergraduate and postgraduate student discovery, tracking, and profile matching.
- **Faculty Portal**: Administrative tools for faculty to post opportunities and review applicant matches.
- **Admin Portal**: System moderation, manual data review, feed management, and user governance.
- **Admin Verification**: Verification workflows for faculty credentials and institutional affiliations.
- **Analytics**: Usage insights, opportunity trends, search metrics, and match effectiveness.
- **Authentication**: Secure user authentication (JWT/OAuth) with password hashing.
- **Authorization**: Role-Based Access Control (RBAC) separating Student, Faculty, and Admin permissions.
- **Security**: Strict input validation, CORS protection, rate limiting, and secure environment configuration.
- **Logging**: Structured application logging for debugging and audit trails.
- **Deployment**: Lightweight Docker configuration for production containerization on standard cloud/VPS hosts.

---

## 8. Evaluation
Rigorous testing and quantitative validation of AI, scraping, and ranking systems.

- **Recommendation Evaluation**: Offline and online metrics (Precision@K, Recall@K, MRR, NDCG) for opportunity ranking.
- **Risk Model Evaluation**: Classification accuracy, precision, and recall against known predatory venue benchmarks.
- **Data Quality Evaluation**: Validation rates, duplicate reduction efficiency, and parsing completeness metrics.
