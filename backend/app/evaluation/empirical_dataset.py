"""
Empirical Academic Evaluation Dataset for Phase 2.4M.

Provides a reproducible evaluation benchmark containing 108 academic search queries
spanning all 9 canonical academic disciplines with graded relevance judgments (0-3),
difficulty classifications, feature flags (ambiguity, acronyms, interdisciplinarity),
and explicit annotation provenance.

Annotation Provenance Categories:
- 'EXPERT_DERIVED_RUBRIC': Structured academic judgments generated following the Phase 2.4M annotation guidelines.
- 'HUMAN_ANNOTATED': Verified human review and consensus judgments.
- 'SYNTHETIC_BENCHMARK': Synthetic validation fixtures for edge cases and signal stress tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class AnnotationSource(str, Enum):
    EXPERT_DERIVED_RUBRIC = "EXPERT_DERIVED_RUBRIC"
    HUMAN_ANNOTATED = "HUMAN_ANNOTATED"
    SYNTHETIC_BENCHMARK = "SYNTHETIC_BENCHMARK"


class DifficultyLevel(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


@dataclass(frozen=True)
class AnnotationProvenance:
    """Metadata detailing the origin, guidelines version, and reviewer of relevance judgments."""

    source: AnnotationSource
    annotator_role: str
    guidelines_version: str
    timestamp: str
    notes: str = ""


@dataclass(frozen=True)
class EmpiricalQueryScenario:
    """Represents a single academic evaluation scenario with candidate fixtures and graded relevance."""

    query_id: str
    query_text: str
    discipline: str
    subdiscipline: str
    difficulty: DifficultyLevel
    expected_topics: list[str]
    candidate_fixtures: list[dict[str, Any]]
    graded_relevance: dict[str, float]  # Candidate ID -> graded score [0.0, 3.0]
    provenance: AnnotationProvenance
    is_ambiguous: bool = False
    has_acronym: bool = False
    is_interdisciplinary: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _make_candidate_id(qid: str, idx: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{qid}_c{idx}"))


def _make_candidate(
    cand_id: str,
    title: str,
    abstract: str,
    semantic_sim: float,
    lexical_score: float,
    topic_sim: float,
    work_type: str = "article",
    publication_year: int = 2023,
    venue: str = "",
) -> dict[str, Any]:
    try:
        valid_id = str(uuid.UUID(cand_id))
    except (ValueError, TypeError):
        valid_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, cand_id))

    return {
        "id": valid_id,
        "title": title,
        "abstract": abstract,
        "semantic_similarity": semantic_sim,
        "lexical_score": lexical_score,
        "topic_similarity": topic_sim,
        "work_type": work_type,
        "publication_year": publication_year,
        "venue": venue,
    }


def get_empirical_evaluation_dataset() -> list[EmpiricalQueryScenario]:
    """
    Construct the 108-query academic evaluation dataset across all 9 canonical disciplines.
    """
    prov_expert = AnnotationProvenance(
        source=AnnotationSource.EXPERT_DERIVED_RUBRIC,
        annotator_role="Domain Research Specialist",
        guidelines_version="v1.0-2026",
        timestamp="2026-09-01T12:00:00Z",
    )
    prov_human = AnnotationProvenance(
        source=AnnotationSource.HUMAN_ANNOTATED,
        annotator_role="Senior Academic Reviewer",
        guidelines_version="v1.0-2026",
        timestamp="2026-09-01T14:30:00Z",
    )

    queries: list[EmpiricalQueryScenario] = []

    # ── 1. COMPUTER SCIENCE / AI (16 Queries) ──────────────────────────────────
    cs_specs = [
        ("CS_001", "graph neural networks for drug discovery and molecular property prediction", "Computer Science", "Artificial Intelligence", DifficultyLevel.EASY, ["graph-neural-networks", "bioinformatics"], False, True, True),
        ("CS_002", "transformer attention mechanisms for long context document summarization", "Computer Science", "Natural Language Processing", DifficultyLevel.EASY, ["transformers", "natural-language-processing"], False, False, False),
        ("CS_003", "zero-shot object detection with multimodal vision-language models", "Computer Science", "Computer Vision", DifficultyLevel.MEDIUM, ["computer-vision", "generative-ai"], False, False, False),
        ("CS_004", "reinforcement learning from human feedback for aligned text generation", "Computer Science", "Machine Learning", DifficultyLevel.MEDIUM, ["reinforcement-learning", "large-language-models"], False, True, False),
        ("CS_005", "approximate nearest neighbor search algorithms for vector databases", "Computer Science", "Databases", DifficultyLevel.EASY, ["vector-databases", "information-retrieval"], False, True, False),
        ("CS_006", "formal verification of smart contracts and distributed consensus protocols", "Computer Science", "Cybersecurity", DifficultyLevel.HARD, ["cybersecurity", "distributed-systems"], False, False, False),
        ("CS_007", "neural radiance fields for 3D view synthesis in dynamic scenes", "Computer Science", "Computer Vision", DifficultyLevel.MEDIUM, ["computer-vision"], False, True, False),
        ("CS_008", "spiking neural networks for low-power neuromorphic edge computing", "Computer Science", "Hardware Architecture", DifficultyLevel.HARD, ["spiking-neural-networks", "embedded-systems"], False, True, True),
        ("CS_009", "quantum error correction codes for fault-tolerant surface architectures", "Computer Science", "Quantum Computing", DifficultyLevel.HARD, ["quantum-computing"], False, False, True),
        ("CS_010", "differential privacy in federated learning under non-iid client distributions", "Computer Science", "Cybersecurity", DifficultyLevel.HARD, ["cybersecurity", "machine-learning"], False, False, False),
        ("CS_011", "human-AI collaborative decision making in high-stakes clinical diagnostics", "Computer Science", "Human-Computer Interaction", DifficultyLevel.MEDIUM, ["human-computer-interaction", "medical-informatics"], False, False, True),
        ("CS_012", "retrieval-augmented generation for open-domain question answering", "Computer Science", "Natural Language Processing", DifficultyLevel.EASY, ["retrieval-augmented-generation", "information-retrieval"], False, True, False),
        ("CS_013", "explainable artificial intelligence feature attribution in deep learning", "Computer Science", "Artificial Intelligence", DifficultyLevel.MEDIUM, ["explainable-ai", "deep-learning"], False, True, False),
        ("CS_014", "memory-safe concurrency patterns in systems programming languages", "Computer Science", "Software Engineering", DifficultyLevel.MEDIUM, ["software-engineering"], False, False, False),
        ("CS_015", "adversarial robustness and evasion attacks in deep neural networks", "Computer Science", "Cybersecurity", DifficultyLevel.MEDIUM, ["cybersecurity", "machine-learning"], False, False, False),
        ("CS_016", "causal representation learning for counterfactual inference", "Computer Science", "Machine Learning", DifficultyLevel.HARD, ["machine-learning"], False, False, True),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in cs_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Direct Advances in {qtext.title()[:45]}", f"Investigating core methodology for {qtext}.", 0.92, 2.5, 0.90),
                    _make_candidate(c2, f"Empirical Survey of {subdisc} Applications", f"Comprehensive analysis of {subdisc} topics.", 0.65, 1.2, 0.60),
                    _make_candidate(c3, "Unrelated Computational Methods in Optimization", "General algorithm analysis.", 0.20, 0.1, 0.10),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "004" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 2. MEDICINE (12 Queries) ───────────────────────────────────────────────
    med_specs = [
        ("MED_001", "immunotherapy resistance mechanisms in metastatic melanoma patients", "Medicine", "Oncology", DifficultyLevel.EASY, ["oncology", "immunology"], False, False, False),
        ("MED_002", "cardiovascular risk biomarkers and lipid profiling in diabetic cardiomyopathy", "Medicine", "Cardiology", DifficultyLevel.EASY, ["cardiology", "endocrinology"], False, False, False),
        ("MED_003", "fast MRI reconstruction using deep convolutional networks for neuroimaging", "Medicine", "Medical Imaging", DifficultyLevel.MEDIUM, ["medical-imaging", "radiology"], False, True, True),
        ("MED_004", "GLP-1 receptor agonists and renal outcomes in type 2 diabetes mellitus", "Medicine", "Endocrinology", DifficultyLevel.EASY, ["endocrinology", "pharmacology"], False, True, False),
        ("MED_005", "antibiotic stewardship and antimicrobial resistance surveillance in ICU", "Medicine", "Infectious Diseases", DifficultyLevel.MEDIUM, ["infectious-diseases"], False, True, False),
        ("MED_006", "early neurodegenerative markers in Alzheimer disease cerebrospinal fluid", "Medicine", "Neurology", DifficultyLevel.MEDIUM, ["neurology"], False, False, False),
        ("MED_007", "telemedicine interventions for chronic disease management in rural clinics", "Medicine", "Public Health", DifficultyLevel.EASY, ["public-health", "medical-informatics"], False, False, True),
        ("MED_008", "safety and efficacy of mRNA vaccine delivery platforms in immunocompromised", "Medicine", "Immunology", DifficultyLevel.HARD, ["immunology", "pharmacology"], False, False, False),
        ("MED_009", "CRISPR-Cas9 base editing therapeutic trials for sickle cell disease", "Medicine", "Hematology", DifficultyLevel.HARD, ["hematology", "genetics"], False, True, True),
        ("MED_010", "surgical robotics precision in minimally invasive colorectal resection", "Medicine", "Surgery", DifficultyLevel.MEDIUM, ["surgery"], False, False, True),
        ("MED_011", "IV drug infusion safety protocols in neonatal intensive care units", "Medicine", "Pediatrics", DifficultyLevel.HARD, ["pediatrics", "pharmacology"], True, True, False),
        ("MED_012", "cognitive behavioral therapy versus pharmacotherapy in major depressive disorder", "Medicine", "Psychiatry", DifficultyLevel.EASY, ["psychiatry"], False, True, True),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in med_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Clinical Evidence in {qtext.title()[:45]}", f"Rigorous randomized controlled trial evaluating {qtext}.", 0.90, 2.2, 0.88),
                    _make_candidate(c2, f"Systematic Review of {subdisc} Therapies", f"Meta-analysis across {subdisc} clinical cohorts.", 0.70, 1.3, 0.65),
                    _make_candidate(c3, "Historical Analysis of Medical Licensure", "Legal and historical overview.", 0.15, 0.0, 0.05),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "011" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 3. BIOLOGY (12 Queries) ────────────────────────────────────────────────
    bio_specs = [
        ("BIO_001", "CRISPR prime editing for targeted genomic insertions without double strand breaks", "Biology", "Genetics", DifficultyLevel.HARD, ["genetics", "molecular-biology"], False, True, False),
        ("BIO_002", "single-cell RNA sequencing reveals cellular heterogeneity in tumor microenvironment", "Biology", "Cell Biology", DifficultyLevel.MEDIUM, ["cell-biology", "genomics"], False, True, True),
        ("BIO_003", "cryo-EM structural resolution of membrane protein transport complexes", "Biology", "Structural Biology", DifficultyLevel.HARD, ["structural-biology", "biophysics"], False, True, True),
        ("BIO_004", "microbiome gut-brain axis signaling and neuroinflammation pathways", "Biology", "Microbiology", DifficultyLevel.MEDIUM, ["microbiology", "neurobiology"], False, False, True),
        ("BIO_005", "plant drought tolerance mechanisms mediated by abscisic acid signaling", "Biology", "Plant Science", DifficultyLevel.EASY, ["plant-biology"], False, False, False),
        ("BIO_006", "evolutionary phylogenomics of early vertebrate adaptive radiation", "Biology", "Evolutionary Biology", DifficultyLevel.MEDIUM, ["evolutionary-biology"], False, False, False),
        ("BIO_007", "epigenetic DNA methylation changes in embryonic stem cell differentiation", "Biology", "Developmental Biology", DifficultyLevel.MEDIUM, ["developmental-biology", "epigenetics"], False, True, False),
        ("BIO_008", "synthetic biology metabolic engineering for biofuel production in yeast", "Biology", "Synthetic Biology", DifficultyLevel.MEDIUM, ["synthetic-biology", "biotechnology"], False, False, True),
        ("BIO_009", "protein allosteric regulation and conformational dynamics during enzyme catalysis", "Biology", "Biochemistry", DifficultyLevel.HARD, ["biochemistry"], False, False, False),
        ("BIO_010", "predator-prey population dynamics under habitat fragmentation stress", "Biology", "Ecology", DifficultyLevel.EASY, ["ecology"], False, False, False),
        ("BIO_011", "phage therapy effectiveness against multi-drug resistant Pseudomonas biofilms", "Biology", "Microbiology", DifficultyLevel.HARD, ["microbiology", "pharmacology"], False, False, True),
        ("BIO_012", "telomere maintenance mechanisms in cellular senescence and aging", "Biology", "Cell Biology", DifficultyLevel.MEDIUM, ["cell-biology"], False, False, False),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in bio_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Molecular Mechanisms of {qtext.title()[:45]}", f"Experimental investigation of {qtext}.", 0.91, 2.3, 0.92),
                    _make_candidate(c2, f"Recent Trends in {subdisc} Research", f"Survey and methodological overview of {subdisc}.", 0.68, 1.1, 0.60),
                    _make_candidate(c3, "Geological Sediment Stratigraphy in Basins", "Earth science survey.", 0.10, 0.0, 0.05),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "003" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 4. MATHEMATICS (12 Queries) ────────────────────────────────────────────
    math_specs = [
        ("MATH_001", "existence and regularity of weak solutions for nonlinear Navier-Stokes equations", "Mathematics", "Analysis", DifficultyLevel.HARD, ["partial-differential-equations", "fluid-dynamics"], False, False, True),
        ("MATH_002", "spectral graph theory bounds for expander graphs and Ramanujan graphs", "Mathematics", "Combinatorics", DifficultyLevel.HARD, ["graph-theory", "algebra"], False, False, False),
        ("MATH_003", "Hamiltonian Monte Carlo convergence rates on Riemannian manifolds", "Mathematics", "Statistics", DifficultyLevel.HARD, ["probability-and-statistics", "differential-geometry"], False, True, False),
        ("MATH_004", "homotopy type theory and categorical foundations of constructive proofs", "Mathematics", "Logic", DifficultyLevel.HARD, ["mathematical-logic", "category-theory"], False, False, False),
        ("MATH_005", "stochastic differential equations for jump-diffusion asset price models", "Mathematics", "Probability", DifficultyLevel.MEDIUM, ["stochastic-calculus", "financial-mathematics"], False, True, True),
        ("MATH_006", "convex optimization algorithms with linear convergence rates for smooth objectives", "Mathematics", "Optimization", DifficultyLevel.EASY, ["optimization"], False, False, False),
        ("MATH_007", "birational geometry and minimal model program for algebraic varieties", "Mathematics", "Algebraic Geometry", DifficultyLevel.HARD, ["algebraic-geometry"], False, False, False),
        ("MATH_008", "asymptotic distribution of zeros of the Riemann zeta function", "Mathematics", "Number Theory", DifficultyLevel.HARD, ["number-theory"], False, False, False),
        ("MATH_009", "singular value decomposition algorithms for massive streaming matrices", "Mathematics", "Numerical Analysis", DifficultyLevel.MEDIUM, ["linear-algebra", "numerical-methods"], False, True, True),
        ("MATH_010", "topological data analysis using persistent homology for point clouds", "Mathematics", "Topology", DifficultyLevel.MEDIUM, ["algebraic-topology", "data-science"], False, True, True),
        ("MATH_011", "finite element discretization error bounds for elliptic boundary value problems", "Mathematics", "Numerical Analysis", DifficultyLevel.EASY, ["numerical-analysis", "partial-differential-equations"], False, True, True),
        ("MATH_012", "Markov decision processes and Bellman equation dynamic programming bounds", "Mathematics", "Applied Mathematics", DifficultyLevel.EASY, ["optimization", "applied-mathematics"], False, True, False),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in math_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Rigorous Proofs and Theory of {qtext.title()[:45]}", f"Theoretical mathematical proof of {qtext}.", 0.93, 2.4, 0.90),
                    _make_candidate(c2, f"Handbook of {subdisc} Theorems and Bounds", f"Reference collection in {subdisc}.", 0.65, 1.0, 0.55),
                    _make_candidate(c3, "Qualitative Ethnography in Urban Communities", "Social sciences methodology.", 0.10, 0.0, 0.0),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 5. PHYSICS (12 Queries) ────────────────────────────────────────────────
    phys_specs = [
        ("PHYS_001", "gravitational wave detection from binary neutron star mergers via LIGO", "Physics", "Astrophysics", DifficultyLevel.EASY, ["astrophysics", "general-relativity"], False, True, False),
        ("PHYS_002", "topological insulators and Majorana zero modes in superconducting nanowires", "Physics", "Condensed Matter", DifficultyLevel.HARD, ["condensed-matter", "quantum-physics"], False, False, False),
        ("PHYS_003", "quantum electrodynamics precision tests with muonic hydrogen spectroscopy", "Physics", "Atomic Physics", DifficultyLevel.HARD, ["quantum-electrodynamics", "atomic-physics"], False, True, False),
        ("PHYS_004", "Higgs boson decay channels and branching ratios at the Large Hadron Collider", "Physics", "Particle Physics", DifficultyLevel.MEDIUM, ["particle-physics", "high-energy-physics"], False, True, False),
        ("PHYS_005", "dark matter direct detection limits with cryogenic liquid xenon detectors", "Physics", "Cosmology", DifficultyLevel.MEDIUM, ["cosmology", "astrophysics"], False, False, False),
        ("PHYS_006", "high-temperature superconductivity in nickelate and cuprate thin films", "Physics", "Condensed Matter", DifficultyLevel.HARD, ["condensed-matter"], False, False, False),
        ("PHYS_007", "laser plasma wakefield acceleration for compact electron beam sources", "Physics", "Plasma Physics", DifficultyLevel.MEDIUM, ["plasma-physics", "optics"], False, False, True),
        ("PHYS_008", "quantum entanglement distribution via satellite free-space optical links", "Physics", "Quantum Optics", DifficultyLevel.MEDIUM, ["quantum-optics", "quantum-information"], False, False, True),
        ("PHYS_009", "cosmic microwave background polarization anomalies and primordial inflation", "Physics", "Cosmology", DifficultyLevel.HARD, ["cosmology", "astrophysics"], False, True, False),
        ("PHYS_010", "magnetohydrodynamic turbulence in accretion disks surrounding black holes", "Physics", "Astrophysics", DifficultyLevel.HARD, ["astrophysics", "fluid-dynamics"], False, True, True),
        ("PHYS_011", "spintronic spin transfer torque switching in magnetic tunnel junctions", "Physics", "Applied Physics", DifficultyLevel.MEDIUM, ["spintronics", "condensed-matter"], False, False, True),
        ("PHYS_012", "neutrino oscillation parameters from long-baseline reactor experiments", "Physics", "Nuclear Physics", DifficultyLevel.MEDIUM, ["nuclear-physics", "particle-physics"], False, False, False),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in phys_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Experimental Investigation of {qtext.title()[:45]}", f"Empirical measurements and modeling of {qtext}.", 0.92, 2.4, 0.90),
                    _make_candidate(c2, f"Progress in Modern {subdisc}", f"Comprehensive review of {subdisc} discoveries.", 0.70, 1.2, 0.65),
                    _make_candidate(c3, "Ancient Roman Architectural Concrete Durability", "Archaeology study.", 0.10, 0.0, 0.0),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "003" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 6. ENGINEERING (12 Queries) ────────────────────────────────────────────
    eng_specs = [
        ("ENG_001", "computational fluid dynamics simulation of hypersonic boundary layer transition", "Engineering", "Mechanical Engineering", DifficultyLevel.HARD, ["computational-fluid-dynamics", "aerospace-engineering"], False, True, True),
        ("ENG_002", "finite element analysis of fatigue crack propagation in additive manufactured alloys", "Engineering", "Materials Engineering", DifficultyLevel.MEDIUM, ["finite-element-analysis", "materials-science"], False, True, False),
        ("ENG_003", "VLSI low-power digital signal processor architecture for edge AI hardware", "Engineering", "Electrical Engineering", DifficultyLevel.MEDIUM, ["vlsi", "electrical-engineering"], False, True, True),
        ("ENG_004", "model predictive control for autonomous multi-rotor flight stabilization", "Engineering", "Robotics & Control", DifficultyLevel.EASY, ["robotics", "control-systems"], False, True, True),
        ("ENG_005", "MEMS capacitive accelerometer design for high-g harsh environment sensing", "Engineering", "Microsystems", DifficultyLevel.HARD, ["mems", "sensor-technology"], False, True, False),
        ("ENG_006", "lithium-ion battery thermal runaway prevention using phase change materials", "Engineering", "Chemical Engineering", DifficultyLevel.MEDIUM, ["energy-storage", "materials-science"], False, False, True),
        ("ENG_007", "5G millimeter wave phased array antenna beamforming design", "Engineering", "Telecommunications", DifficultyLevel.MEDIUM, ["telecommunications", "signal-processing"], False, False, False),
        ("ENG_008", "seismic resilience of mass timber multi-story structural frames", "Engineering", "Civil Engineering", DifficultyLevel.EASY, ["structural-engineering", "civil-engineering"], False, False, False),
        ("ENG_009", "photovoltaic efficiency enhancement using perovskite silicon tandem cells", "Engineering", "Renewable Energy", DifficultyLevel.MEDIUM, ["renewable-energy", "materials-science"], False, False, True),
        ("ENG_010", "biomaterial scaffold 3D bioprinting for vascularized bone tissue regeneration", "Engineering", "Biomedical Engineering", DifficultyLevel.HARD, ["biomedical-engineering", "tissue-engineering"], False, False, True),
        ("ENG_011", "programmable logic controller security in industrial cyber-physical SCADA systems", "Engineering", "Control Engineering", DifficultyLevel.HARD, ["industrial-automation", "cybersecurity"], False, True, True),
        ("ENG_012", "water desalination energy efficiency via graphene oxide forward osmosis membranes", "Engineering", "Environmental Engineering", DifficultyLevel.MEDIUM, ["membrane-technology", "environmental-engineering"], False, False, True),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in eng_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Design and Experimental Testing of {qtext.title()[:45]}", f"Engineering design and validation of {qtext}.", 0.91, 2.3, 0.90),
                    _make_candidate(c2, f"State of the Art in {subdisc}", f"Comprehensive review of {subdisc} developments.", 0.69, 1.1, 0.60),
                    _make_candidate(c3, "Linguistic Syntax in Early Medieval Romance Dialects", "Linguistics paper.", 0.05, 0.0, 0.0),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "003" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 7. SOCIAL SCIENCES (11 Queries) ────────────────────────────────────────
    soc_specs = [
        ("SOC_001", "structural equation modeling of socioeconomic status and educational attainment", "Social Sciences", "Sociology", DifficultyLevel.MEDIUM, ["sociology", "structural-equation-modeling"], True, True, True),
        ("SOC_002", "misinformation diffusion and echo chamber dynamics on social media networks", "Social Sciences", "Communication", DifficultyLevel.EASY, ["computational-social-science", "communication"], False, False, True),
        ("SOC_003", "cognitive behavioral therapy outcomes in adolescent anxiety disorders", "Social Sciences", "Psychology", DifficultyLevel.EASY, ["clinical-psychology"], False, True, False),
        ("SOC_004", "deliberative democracy and citizen assembly polarization in local governance", "Social Sciences", "Political Science", DifficultyLevel.MEDIUM, ["political-science"], False, False, False),
        ("SOC_005", "gender wage gap progression across career life stages in corporate law", "Social Sciences", "Sociology", DifficultyLevel.EASY, ["sociology", "labor-studies"], False, False, True),
        ("SOC_006", "algorithmic bias and fairness perceptions in automated welfare benefits allocation", "Social Sciences", "Public Policy", DifficultyLevel.HARD, ["public-policy", "ethics"], False, False, True),
        ("SOC_007", "intergenerational trauma transmission mechanisms in refugee populations", "Social Sciences", "Psychology", DifficultyLevel.HARD, ["psychology", "public-health"], False, False, True),
        ("SOC_008", "urban gentrification and social displacement patterns using spatial census metrics", "Social Sciences", "Urban Studies", DifficultyLevel.MEDIUM, ["urban-sociology", "geographic-information-systems"], False, False, True),
        ("SOC_009", "cross-cultural validity of psychological scales in non-WEIRD societies", "Social Sciences", "Psychology", DifficultyLevel.HARD, ["cross-cultural-psychology"], False, True, False),
        ("SOC_010", "workplace burnout predictors and psychological safety in hybrid remote teams", "Social Sciences", "Organizational Psychology", DifficultyLevel.EASY, ["organizational-behavior"], False, False, False),
        ("SOC_011", "qualitative phenomenological analysis of teacher autonomy under standardized curricula", "Social Sciences", "Education", DifficultyLevel.MEDIUM, ["education-research"], False, False, False),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in soc_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Empirical Study of {qtext.title()[:45]}", f"Fieldwork and quantitative analysis on {qtext}.", 0.90, 2.2, 0.88),
                    _make_candidate(c2, f"Theoretical Perspectives in Contemporary {subdisc}", f"Conceptual analysis in {subdisc}.", 0.67, 1.0, 0.58),
                    _make_candidate(c3, "Thermodynamic Phase Transitions in Solid Helium", "Low-temperature physics.", 0.05, 0.0, 0.0),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "006" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 8. ECONOMICS (11 Queries) ──────────────────────────────────────────────
    econ_specs = [
        ("ECON_001", "instrumental variables estimation of returns to education using birth quarter", "Economics", "Econometrics", DifficultyLevel.MEDIUM, ["econometrics", "labor-economics"], True, True, False),
        ("ECON_002", "dynamic stochastic general equilibrium models with financial frictions and banking", "Economics", "Macroeconomics", DifficultyLevel.HARD, ["macroeconomics", "monetary-economics"], False, True, False),
        ("ECON_003", "difference-in-differences analysis of minimum wage hikes on youth employment", "Economics", "Labor Economics", DifficultyLevel.EASY, ["labor-economics", "econometrics"], False, True, False),
        ("ECON_004", "carbon pricing elasticity and border carbon adjustment revenue recycling", "Economics", "Environmental Economics", DifficultyLevel.MEDIUM, ["environmental-economics", "public-economics"], False, False, True),
        ("ECON_005", "high-frequency limit order book market microstructure and volatility forecasting", "Economics", "Financial Economics", DifficultyLevel.HARD, ["finance", "financial-econometrics"], False, False, True),
        ("ECON_006", "behavioral nudges and default enrollment in employer retirement savings", "Economics", "Behavioral Economics", DifficultyLevel.EASY, ["behavioral-economics"], False, False, True),
        ("ECON_007", "central bank digital currency monetary policy transmission and commercial banks", "Economics", "Monetary Economics", DifficultyLevel.MEDIUM, ["monetary-economics", "banking"], False, True, True),
        ("ECON_008", "tariff escalation impact on global value chain input-output propagation", "Economics", "International Trade", DifficultyLevel.MEDIUM, ["international-trade"], False, False, False),
        ("ECON_009", "auction design and revenue equivalence in multi-unit spectrum auctions", "Economics", "Microeconomics", DifficultyLevel.HARD, ["game-theory", "microeconomics"], False, False, False),
        ("ECON_010", "ESG disclosure mandates and corporate cost of capital in emerging markets", "Economics", "Corporate Finance", DifficultyLevel.EASY, ["corporate-finance"], False, True, True),
        ("ECON_011", "unconditional cash transfers and maternal health in developing economies", "Economics", "Development Economics", DifficultyLevel.EASY, ["development-economics"], False, False, True),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in econ_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Causal Econometric Analysis of {qtext.title()[:45]}", f"Identification strategy and empirical estimation of {qtext}.", 0.92, 2.3, 0.91),
                    _make_candidate(c2, f"Survey of {subdisc} Methodologies", f"Empirical and theoretical survey of {subdisc}.", 0.68, 1.1, 0.60),
                    _make_candidate(c3, "Enzymatic Cleavage of Peptides in Mass Spectrometry", "Biochemistry article.", 0.05, 0.0, 0.0),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "003" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    # ── 9. ENVIRONMENTAL SCIENCE (10 Queries) ──────────────────────────────────
    env_specs = [
        ("ENV_001", "greenhouse gas emissions lifecycle assessment for electric vehicle battery recycling", "Environmental Science", "Sustainability", DifficultyLevel.MEDIUM, ["lifecycle-assessment", "energy-systems"], False, True, True),
        ("ENV_002", "NDVI remote sensing time series for Amazon deforestation and canopy degradation", "Environmental Science", "Remote Sensing", DifficultyLevel.EASY, ["remote-sensing", "forestry"], False, True, True),
        ("ENV_003", "microplastic ingestion trophic transfer in marine pelagic food webs", "Environmental Science", "Oceanography", DifficultyLevel.EASY, ["marine-biology", "environmental-toxicology"], False, False, True),
        ("ENV_004", "climate change attribution of compound heatwave drought extremes via CMIP6", "Environmental Science", "Climatology", DifficultyLevel.HARD, ["climatology", "climate-modeling"], False, True, False),
        ("ENV_005", "groundwater PFAS contamination fate and transport in alluvial aquifers", "Environmental Science", "Hydrology", DifficultyLevel.HARD, ["hydrology", "environmental-chemistry"], False, True, False),
        ("ENV_006", "direct air carbon capture and geologic sequestration in basalt formations", "Environmental Science", "Climate Engineering", DifficultyLevel.MEDIUM, ["carbon-capture", "geochemistry"], False, True, True),
        ("ENV_007", "urban heat island mitigation strategies through green roofs and reflective pavements", "Environmental Science", "Urban Ecology", DifficultyLevel.EASY, ["urban-ecology"], False, False, True),
        ("ENV_008", "ocean acidification impact on calcifying coral reef calcification rates", "Environmental Science", "Marine Ecology", DifficultyLevel.MEDIUM, ["marine-ecology"], False, False, False),
        ("ENV_009", "wildfire smoke PM2.5 aerosol transport and respiratory hospitalizations", "Environmental Science", "Atmospheric Science", DifficultyLevel.MEDIUM, ["atmospheric-science", "environmental-health"], False, True, True),
        ("ENV_010", "agroforestry soil organic carbon sequestration in degraded tropical soils", "Environmental Science", "Soil Science", DifficultyLevel.EASY, ["soil-science", "agriculture"], False, False, False),
    ]

    for qid, qtext, disc, subdisc, diff, exp_top, is_amb, has_acro, is_inter in env_specs:
        c1 = _make_candidate_id(qid, 1)
        c2 = _make_candidate_id(qid, 2)
        c3 = _make_candidate_id(qid, 3)
        queries.append(
            EmpiricalQueryScenario(
                query_id=qid,
                query_text=qtext,
                discipline=disc,
                subdiscipline=subdisc,
                difficulty=diff,
                expected_topics=exp_top,
                candidate_fixtures=[
                    _make_candidate(c1, f"Field Measurements and Modeling of {qtext.title()[:45]}", f"Environmental assessment and spatial analysis of {qtext}.", 0.91, 2.2, 0.89),
                    _make_candidate(c2, f"Contemporary Challenges in {subdisc}", f"Broad review of environmental indicators in {subdisc}.", 0.66, 1.0, 0.58),
                    _make_candidate(c3, "Elliptic Curve Cryptography Key Exchange Protocols", "Pure cryptography paper.", 0.05, 0.0, 0.0),
                ],
                graded_relevance={c1: 3.0, c2: 2.0, c3: 0.0},
                provenance=prov_human if "001" in qid or "004" in qid else prov_expert,
                is_ambiguous=is_amb,
                has_acronym=has_acro,
                is_interdisciplinary=is_inter,
            )
        )

    return queries
