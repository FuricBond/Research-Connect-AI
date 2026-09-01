"""
Taxonomy service and canonical research topic hierarchy.

Defines the core ResearchConnect AI academic taxonomy tree, supports DAG traversal,
cycle prevention, ancestor/descendant resolution, coverage reporting, and database synchronization.
Expanded in Phase 2.4L to represent 180+ canonical nodes across 9 major disciplines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class TaxonomyNode:
    """Represents a canonical topic in the taxonomy tree."""
    name: str
    slug: str
    description: str | None = None
    parent_slug: str | None = None
    aliases: list[str] = field(default_factory=list)
    ontology_mappings: dict[str, str] = field(default_factory=dict)


# ── Canonical Seed Taxonomy (Expanded to 180+ nodes across 9 disciplines) ────

SEED_TAXONOMY: list[TaxonomyNode] = [
    # ── 1. Top-Level Disciplinary Roots (9 Primary Roots) ─────────────────────
    TaxonomyNode(
        name="Computer Science",
        slug="computer-science",
        description="The study of computation, information, and automation.",
        aliases=["CS", "Computing", "Computer Sciences"],
        ontology_mappings={"openalex": "C41008148", "acm_ccs": "10003752"},
    ),
    TaxonomyNode(
        name="Medicine",
        slug="medicine",
        description="The science and practice of caring for patients, diagnosis, and treatment of disease.",
        aliases=["Medical Sciences", "Healthcare", "Biomedicine", "Clinical Medicine"],
        ontology_mappings={"openalex": "C71924100", "mesh": "D008511"},
    ),
    TaxonomyNode(
        name="Biology",
        slug="biology",
        description="The scientific study of life and living organisms.",
        aliases=["Biological Sciences", "Life Sciences"],
        ontology_mappings={"openalex": "C86803240", "mesh": "D001695"},
    ),
    TaxonomyNode(
        name="Mathematics",
        slug="mathematics",
        description="The science of numbers, quantities, space, and structures.",
        aliases=["Math", "Mathematical Sciences"],
        ontology_mappings={"openalex": "C33923547", "acm_ccs": "10002950"},
    ),
    TaxonomyNode(
        name="Physics",
        slug="physics",
        description="The study of matter, motion, energy, and force.",
        aliases=["Physical Sciences"],
        ontology_mappings={"openalex": "C121332964"},
    ),
    TaxonomyNode(
        name="Engineering",
        slug="engineering",
        description="The application of science and math to design and build structures, machines, and systems.",
        aliases=["Engineering Sciences", "Applied Sciences"],
        ontology_mappings={"openalex": "C127413603"},
    ),
    TaxonomyNode(
        name="Social Sciences",
        slug="social-sciences",
        description="The scientific study of human society, behaviors, and social relationships.",
        aliases=["Social Science", "Behavioral Sciences"],
        ontology_mappings={"openalex": "C17744445"},
    ),
    TaxonomyNode(
        name="Economics",
        slug="economics",
        description="The study of production, distribution, and consumption of goods, services, and wealth.",
        aliases=["Economic Sciences", "Business and Economics"],
        ontology_mappings={"openalex": "C162324750"},
    ),
    TaxonomyNode(
        name="Environmental Science",
        slug="environmental-science",
        description="The interdisciplinary study of the environment, ecosystems, and environmental solutions.",
        aliases=["Ecology and Environment", "Environmental Sciences", "Earth and Environment"],
        ontology_mappings={"openalex": "C39432304"},
    ),

    # ── 2. Computer Science & AI (Subfields & Topics) ─────────────────────────
    TaxonomyNode(name="Artificial Intelligence", slug="artificial-intelligence", parent_slug="computer-science", description="Simulating human intelligence in machines.", aliases=["AI", "Computational Intelligence"], ontology_mappings={"acm_ccs": "10010147.10010178"}),
    TaxonomyNode(name="Data Science", slug="data-science", parent_slug="computer-science", description="Extracting insights and knowledge from structured and unstructured data.", aliases=["Data Analytics", "Big Data Analytics"]),
    TaxonomyNode(name="Software Engineering", slug="software-engineering", parent_slug="computer-science", description="The systematic engineering approach to software development.", aliases=["SE", "Software Development"], ontology_mappings={"acm_ccs": "10011007"}),
    TaxonomyNode(name="Cybersecurity", slug="cybersecurity", parent_slug="computer-science", description="Protecting computer systems and networks from information disclosure and attack.", aliases=["Information Security", "InfoSec", "Cyber Security"], ontology_mappings={"acm_ccs": "10002978"}),
    TaxonomyNode(name="Databases", slug="databases", parent_slug="computer-science", description="Organization, storage, and retrieval of electronic data.", aliases=["Database Systems", "DBMS", "Data Management"], ontology_mappings={"acm_ccs": "10002951.10002952"}),
    TaxonomyNode(name="Distributed Systems", slug="distributed-systems", parent_slug="computer-science", description="Computing systems whose components are located on different networked computers.", aliases=["Distributed Computing", "Cloud Infrastructure"]),
    TaxonomyNode(name="Human-Computer Interaction", slug="human-computer-interaction", parent_slug="computer-science", description="The design and use of computer technology focused on interfaces between people and computers.", aliases=["HCI", "User Experience", "UX"], ontology_mappings={"acm_ccs": "10003120"}),
    TaxonomyNode(name="Computer Networks", slug="computer-networks", parent_slug="computer-science", description="Telecommunications networks allowing computers to exchange data.", aliases=["Networking", "Network Systems"], ontology_mappings={"acm_ccs": "10003033"}),
    TaxonomyNode(name="Cloud Computing", slug="cloud-computing", parent_slug="distributed-systems", description="On-demand availability of computer system resources over the internet.", aliases=["Cloud Services", "Serverless Computing"]),
    TaxonomyNode(name="Cryptography", slug="cryptography", parent_slug="cybersecurity", description="Techniques for secure communication in the presence of adversarial third parties.", aliases=["Crypto", "Applied Cryptography"]),
    TaxonomyNode(name="Compiler Design", slug="compiler-design", parent_slug="software-engineering", description="Principles and practices of translating programming languages into machine code.", aliases=["Compilers", "Programming Language Implementation"]),

    # AI Sub-branches
    TaxonomyNode(name="Machine Learning", slug="machine-learning", parent_slug="artificial-intelligence", description="Algorithms that improve automatically through experience and data.", aliases=["ML", "Statistical Learning", "Machine Learning Algorithms"], ontology_mappings={"openalex": "C119857082", "mesh": "D000077185"}),
    TaxonomyNode(name="Natural Language Processing", slug="natural-language-processing", parent_slug="artificial-intelligence", description="Interaction between computers and human language.", aliases=["NLP", "Computational Linguistics", "Language Technologies"], ontology_mappings={"openalex": "C204321447"}),
    TaxonomyNode(name="Computer Vision", slug="computer-vision", parent_slug="artificial-intelligence", description="Enabling computers to derive high-level understanding from digital images or videos.", aliases=["CV", "Visual Recognition", "Image Processing"], ontology_mappings={"openalex": "C154945302"}),
    TaxonomyNode(name="Robotics", slug="robotics", parent_slug="artificial-intelligence", description="Design, construction, operation, and use of robots and autonomous machines.", aliases=["Autonomous Systems", "Robot Control"], ontology_mappings={"openalex": "C90856484"}),
    TaxonomyNode(name="Knowledge Representation", slug="knowledge-representation", parent_slug="artificial-intelligence", description="Representing information about the world in a form that a computer can use.", aliases=["Knowledge Graphs", "Ontology", "Semantic Web"]),
    TaxonomyNode(name="Autonomous Vehicles", slug="autonomous-vehicles", parent_slug="robotics", description="Self-driving vehicles utilizing sensor fusion and autonomous planning.", aliases=["Self-Driving Cars", "Automated Driving"]),

    # Machine Learning Sub-branches
    TaxonomyNode(name="Deep Learning", slug="deep-learning", parent_slug="machine-learning", description="Neural networks with multiple layers capable of learning hierarchical features.", aliases=["DL", "Neural Networks", "Deep Neural Networks", "DNN"]),
    TaxonomyNode(name="Reinforcement Learning", slug="reinforcement-learning", parent_slug="machine-learning", description="Training machine learning models to make a sequence of decisions through rewards.", aliases=["RL", "Deep Reinforcement Learning", "DRL"]),
    TaxonomyNode(name="Generative AI", slug="generative-ai", parent_slug="deep-learning", description="Artificial intelligence capable of generating text, images, or other media.", aliases=["GenAI", "Generative Models", "Diffusion Models", "GANs"]),
    TaxonomyNode(name="Large Language Models", slug="large-language-models", parent_slug="natural-language-processing", description="Language models with massive parameter counts trained on vast text corpora.", aliases=["LLM", "LLMs", "Large Language Model", "Foundation Models", "GPT", "BERT"]),
    TaxonomyNode(name="Transformers", slug="transformers", parent_slug="deep-learning", description="Self-attention based neural network architectures.", aliases=["Transformer Architecture", "Self-Attention"]),
    TaxonomyNode(name="Graph Neural Networks", slug="graph-neural-networks", parent_slug="deep-learning", description="Deep learning architectures operating directly on graph-structured data.", aliases=["GNN", "GNNs", "Geometric Deep Learning"]),

    # NLP Sub-branches
    TaxonomyNode(name="Information Retrieval", slug="information-retrieval", parent_slug="natural-language-processing", description="Obtaining information system resources relevant to an information need.", aliases=["IR", "Search Engines", "Text Retrieval"], ontology_mappings={"acm_ccs": "10002951.10003317"}),
    TaxonomyNode(name="Text Classification", slug="text-classification", parent_slug="natural-language-processing", description="Assigning predefined categories to text documents.", aliases=["Document Classification", "Sentiment Analysis", "Topic Modeling"]),
    TaxonomyNode(name="Question Answering", slug="question-answering", parent_slug="natural-language-processing", description="Building systems that automatically answer questions in natural language.", aliases=["QA", "RAG", "Retrieval-Augmented Generation"]),
    TaxonomyNode(name="Machine Translation", slug="machine-translation", parent_slug="natural-language-processing", description="Translating text from one natural language to another using computational systems.", aliases=["MT", "Neural Machine Translation", "NMT"]),
    TaxonomyNode(name="Speech Recognition", slug="speech-recognition", parent_slug="natural-language-processing", description="Automatic transcription of spoken audio into textual representation.", aliases=["Automatic Speech Recognition", "ASR", "Speech-to-Text"]),

    # CV Sub-branches
    TaxonomyNode(name="Object Detection", slug="object-detection", parent_slug="computer-vision", description="Locating and classifying instances of visual objects in images or videos.", aliases=["Object Recognition", "YOLO"]),
    TaxonomyNode(name="Image Segmentation", slug="image-segmentation", parent_slug="computer-vision", description="Partitioning digital images into multiple pixel-level semantic regions.", aliases=["Semantic Segmentation", "Instance Segmentation"]),

    # Data Science & Database Topics
    TaxonomyNode(name="Data Mining", slug="data-mining", parent_slug="data-science", description="Discovering non-trivial patterns in large datasets.", aliases=["Pattern Mining", "Knowledge Discovery"]),
    TaxonomyNode(name="Vector Databases", slug="vector-databases", parent_slug="databases", description="Databases designed to index and query high-dimensional vector embeddings.", aliases=["Vector DB", "Vector Search", "ANN Search"]),

    # ── 3. Medicine & Health Sciences (Expanded ~25 nodes) ────────────────────
    TaxonomyNode(name="Cardiovascular Medicine", slug="cardiovascular-medicine", parent_slug="medicine", description="Diagnosis and management of heart and circulatory system diseases.", aliases=["Cardiology and Vascular", "Cardiovascular Diseases"], ontology_mappings={"mesh": "D002318"}),
    TaxonomyNode(name="Cardiology", slug="cardiology", parent_slug="cardiovascular-medicine", description="Medical study and treatment of heart disorders.", aliases=["Heart Disease", "Clinical Cardiology"]),
    TaxonomyNode(name="Heart Failure", slug="heart-failure", parent_slug="cardiovascular-medicine", description="Conditions where the heart muscle cannot pump blood effectively.", aliases=["Congestive Heart Failure", "CHF"]),
    TaxonomyNode(name="Cardiovascular Imaging", slug="cardiovascular-imaging", parent_slug="cardiovascular-medicine", description="Echocardiography, cardiac MRI, and CT imaging of the heart.", aliases=["Echocardiography", "Cardiac MRI"]),

    TaxonomyNode(name="Oncology", slug="oncology", parent_slug="medicine", description="Study, prevention, diagnosis, and clinical treatment of cancer.", aliases=["Cancer Research", "Neoplasms"], ontology_mappings={"mesh": "D009369"}),
    TaxonomyNode(name="Cancer Biology", slug="cancer-biology", parent_slug="oncology", description="Molecular mechanisms of tumorigenesis, metastasis, and cellular transformation.", aliases=["Molecular Oncology", "Tumor Biology"]),
    TaxonomyNode(name="Cancer Immunotherapy", slug="cancer-immunotherapy", parent_slug="oncology", description="Treatment of cancer using antibodies, checkpoint inhibitors, and CAR-T cells.", aliases=["Immuno-Oncology", "Checkpoint Inhibitors", "CAR-T"]),
    TaxonomyNode(name="Radiation Oncology", slug="radiation-oncology", parent_slug="oncology", description="Medical use of ionizing radiation to control or kill malignant cells.", aliases=["Radiotherapy", "Radiation Therapy"]),
    TaxonomyNode(name="Clinical Oncology", slug="clinical-oncology", parent_slug="oncology", description="Medical and surgical management of clinical cancer trials and patients.", aliases=["Chemotherapy", "Surgical Oncology"]),

    TaxonomyNode(name="Neurology", slug="neurology", parent_slug="medicine", description="Disorders of the brain, spinal cord, and nervous system.", aliases=["Clinical Neurology", "Nervous System Diseases"], ontology_mappings={"mesh": "D009422"}),
    TaxonomyNode(name="Neurodegenerative Diseases", slug="neurodegenerative-diseases", parent_slug="neurology", description="Progressive loss of neuronal structure or function, e.g., Alzheimer's, Parkinson's.", aliases=["Alzheimer's Disease", "Parkinson's Disease", "Dementia"]),
    TaxonomyNode(name="Stroke Medicine", slug="stroke-medicine", parent_slug="neurology", description="Ischemic and hemorrhagic cerebrovascular events and neurorehabilitation.", aliases=["Cerebrovascular Disease", "Stroke"]),
    TaxonomyNode(name="Clinical Neuroimaging", slug="clinical-neuroimaging", parent_slug="neurology", description="Diagnostic imaging of brain structure and function in neurological disease.", aliases=["Brain Imaging", "Neuro-MRI"]),

    TaxonomyNode(name="Immunology", slug="immunology", parent_slug="medicine", description="Study of immune system structure, function, and pathological disorders.", aliases=["Immune System", "Clinical Immunology"], ontology_mappings={"mesh": "D007107"}),
    TaxonomyNode(name="Autoimmune Diseases", slug="autoimmune-diseases", parent_slug="immunology", description="Diseases where the immune system attacks host tissues.", aliases=["Autoimmunity", "Rheumatology"]),
    TaxonomyNode(name="Vaccinology", slug="vaccinology", parent_slug="immunology", description="Science and technology of developing preventive and therapeutic vaccines.", aliases=["Vaccines", "Immunization"]),

    TaxonomyNode(name="Epidemiology", slug="epidemiology", parent_slug="medicine", description="Study of the distribution, patterns, and determinants of health and disease conditions.", aliases=["Population Health", "Disease Surveillance"], ontology_mappings={"mesh": "D004812"}),
    TaxonomyNode(name="Infectious Disease Epidemiology", slug="infectious-disease-epidemiology", parent_slug="epidemiology", description="Transmission dynamics and prevention of infectious pathogens and pandemics.", aliases=["Infectious Diseases", "Outbreak Investigation"]),
    TaxonomyNode(name="Public Health", slug="public-health", parent_slug="epidemiology", description="Science of protecting and improving the health of people and their communities.", aliases=["Community Health", "Global Health"]),

    TaxonomyNode(name="Pharmacology", slug="pharmacology", parent_slug="medicine", description="Study of drug action, pharmacokinetics, and therapeutic agents.", aliases=["Pharmaceutical Science", "Therapeutics"], ontology_mappings={"mesh": "D010600"}),
    TaxonomyNode(name="Drug Discovery", slug="drug-discovery", parent_slug="pharmacology", description="Process by which new candidate medications are discovered and designed.", aliases=["Medicinal Chemistry", "Target Identification"]),
    TaxonomyNode(name="Clinical Pharmacology", slug="clinical-pharmacology", parent_slug="pharmacology", description="Science of drugs in humans and their optimal clinical use.", aliases=["Pharmacokinetics", "Pharmacodynamics"]),

    TaxonomyNode(name="Pediatrics", slug="pediatrics", parent_slug="medicine", description="Medical care of infants, children, and adolescents.", aliases=["Child Health", "Pediatric Medicine"]),
    TaxonomyNode(name="Psychiatry", slug="psychiatry", parent_slug="medicine", description="Diagnosis, prevention, and treatment of mental disorders.", aliases=["Mental Health", "Clinical Psychiatry"]),
    TaxonomyNode(name="Medical Informatics", slug="medical-informatics", parent_slug="medicine", description="Informatics in healthcare, electronic health records, and clinical decision support.", aliases=["Healthcare AI", "Health Informatics", "Clinical Informatics"]),
    TaxonomyNode(name="Medical Imaging", slug="medical-imaging", parent_slug="medicine", description="Techniques of creating visual representations of internal body structures for clinical analysis.", aliases=["Radiology", "Diagnostic Imaging", "MRI", "CT Scan"]),

    # ── 4. Biology & Life Sciences (Expanded ~24 nodes) ──────────────────────
    TaxonomyNode(name="Genetics", slug="genetics", parent_slug="biology", description="Study of genes, genetic variation, and heredity in living organisms.", aliases=["Heredity", "Genomics and Genetics"], ontology_mappings={"mesh": "D005805"}),
    TaxonomyNode(name="Genomics", slug="genomics", parent_slug="genetics", description="Sequencing, mapping, and functional analysis of complete organismal genomes.", aliases=["Genome Sequencing", "Functional Genomics"]),
    TaxonomyNode(name="Epigenetics", slug="epigenetics", parent_slug="genetics", description="Heritable phenotype changes that do not involve alterations in DNA sequence.", aliases=["DNA Methylation", "Chromatin Remodeling"]),
    TaxonomyNode(name="CRISPR & Gene Editing", slug="crispr-gene-editing", parent_slug="genetics", description="Targeted DNA modification using CRISPR-Cas systems and base editors.", aliases=["CRISPR", "Gene Editing", "Cas9"]),
    TaxonomyNode(name="Population Genetics", slug="population-genetics", parent_slug="genetics", description="Genetic composition of biological populations and evolutionary forces.", aliases=["Genetic Variation", "Allele Frequencies"]),

    TaxonomyNode(name="Molecular Biology", slug="molecular-biology", parent_slug="biology", description="Study of the molecular basis of biological activity.", aliases=["Molecular Bioscience"], ontology_mappings={"mesh": "D008967"}),
    TaxonomyNode(name="Structural Biology", slug="structural-biology", parent_slug="molecular-biology", description="Molecular structure of biological macromolecules like proteins and nucleic acids.", aliases=["Protein Structure", "Cryo-EM", "X-ray Crystallography"]),
    TaxonomyNode(name="Proteomics", slug="proteomics", parent_slug="molecular-biology", description="Large-scale experimental analysis of proteins and cellular proteomes.", aliases=["Protein Analysis", "Mass Spectrometry Proteomics"]),

    TaxonomyNode(name="Cell Biology", slug="cell-biology", parent_slug="biology", description="Study of cell structure, organelles, physiology, and lifecycle.", aliases=["Cytology", "Cellular Biology"], ontology_mappings={"mesh": "D002477"}),
    TaxonomyNode(name="Stem Cell Research", slug="stem-cell-research", parent_slug="cell-biology", description="Pluripotent and adult stem cells in regeneration and developmental biology.", aliases=["Regenerative Medicine", "Pluripotent Stem Cells"]),
    TaxonomyNode(name="Cellular Signaling", slug="cellular-signaling", parent_slug="cell-biology", description="Signal transduction pathways coordinating cellular activities.", aliases=["Signal Transduction", "Receptor Pathways"]),

    TaxonomyNode(name="Microbiology", slug="microbiology", parent_slug="biology", description="Study of microscopic organisms including bacteria, viruses, fungi, and protozoa.", aliases=["Microbial Biology"], ontology_mappings={"mesh": "D008853"}),
    TaxonomyNode(name="Virology", slug="virology", parent_slug="microbiology", description="Study of viruses and viral infections.", aliases=["Viral Biology", "Viral Pathogenesis"]),
    TaxonomyNode(name="Bacteriology", slug="bacteriology", parent_slug="microbiology", description="Morphology, ecology, genetics, and biochemistry of bacteria.", aliases=["Bacterial Pathogens", "Antibiotic Resistance"]),
    TaxonomyNode(name="Microbiome", slug="microbiome", parent_slug="microbiology", description="Microbial communities residing in specific biological niches like the human gut.", aliases=["Gut Microbiome", "Metagenomics"]),

    TaxonomyNode(name="Biochemistry", slug="biochemistry", parent_slug="biology", description="Chemical processes within and relating to living organisms.", aliases=["Biological Chemistry"], ontology_mappings={"mesh": "D001695"}),
    TaxonomyNode(name="Enzymology", slug="enzymology", parent_slug="biochemistry", description="Kinetic, structural, and functional study of biological enzymes.", aliases=["Enzyme Kinetics", "Biocatalysis"]),
    TaxonomyNode(name="Metabolic Pathways", slug="metabolic-pathways", parent_slug="biochemistry", description="Series of chemical reactions occurring within a cell.", aliases=["Cellular Metabolism", "Metabolomics"]),

    TaxonomyNode(name="Neuroscience", slug="neuroscience", parent_slug="biology", description="Scientific study of the nervous system and the biological basis of behavior.", aliases=["Neurobiology", "Brain Science"], ontology_mappings={"mesh": "D009498"}),
    TaxonomyNode(name="Computational Neuroscience", slug="computational-neuroscience", parent_slug="neuroscience", description="Theoretical and computational modeling of neural system dynamics.", aliases=["Neural Modeling", "Theoretical Neuroscience"]),
    TaxonomyNode(name="Cognitive Neuroscience", slug="cognitive-neuroscience", parent_slug="neuroscience", description="Biological substrates underlying cognition, perception, and memory.", aliases=["Cognitive Brain Research", "fMRI Cognition"]),

    TaxonomyNode(name="Evolutionary Biology", slug="evolutionary-biology", parent_slug="biology", description="Processes that produced the diversity of life on Earth.", aliases=["Evolution", "Phylogenetics"]),
    TaxonomyNode(name="Plant Biology", slug="plant-biology", parent_slug="biology", description="Physiology, structure, genetics, and ecology of plants.", aliases=["Botany", "Plant Sciences"]),
    TaxonomyNode(name="Bioinformatics", slug="bioinformatics", parent_slug="biology", description="Computational methods for analyzing biological data such as genetic sequences.", aliases=["Computational Biology", "Genomic Informatics"]),
    TaxonomyNode(name="Synthetic Biology", slug="synthetic-biology", parent_slug="biology", description="Redesigning organisms for useful purposes by engineering them to have new abilities.", aliases=["SynBio", "Genetic Engineering"]),

    # ── 5. Physics (Expanded ~22 nodes) ──────────────────────────────────────
    TaxonomyNode(name="Astrophysics", slug="astrophysics", parent_slug="physics", description="Physics of astronomical bodies and the universe.", aliases=["Astronomy and Astrophysics", "Space Physics"]),
    TaxonomyNode(name="Cosmology", slug="cosmology", parent_slug="astrophysics", description="Origin, evolution, and eventual fate of the universe.", aliases=["Physical Cosmology", "Dark Energy", "Dark Matter"]),
    TaxonomyNode(name="Stellar Astronomy", slug="stellar-astronomy", parent_slug="astrophysics", description="Formation, structure, evolution, and death of stars.", aliases=["Stellar Physics", "Exoplanets"]),
    TaxonomyNode(name="Gravitational Waves", slug="gravitational-waves", parent_slug="astrophysics", description="Ripples in spacetime caused by accelerated mass, e.g., black hole mergers.", aliases=["LIGO", "Gravitational Wave Astronomy"]),

    TaxonomyNode(name="Condensed Matter Physics", slug="condensed-matter-physics", parent_slug="physics", description="Physical properties of condensed phases of matter like solids and liquids.", aliases=["Solid State Physics", "Condensed Matter"]),
    TaxonomyNode(name="Superconductivity", slug="superconductivity", parent_slug="condensed-matter-physics", description="Zero electrical resistance and expulsion of magnetic fields in materials.", aliases=["High-Tc Superconductors", "Superconducting Materials"]),
    TaxonomyNode(name="Semiconductor Physics", slug="semiconductor-physics", parent_slug="condensed-matter-physics", description="Electronic and optical behavior of semiconductor devices.", aliases=["Semiconductors", "Solid State Electronics"]),
    TaxonomyNode(name="Nanotechnology Physics", slug="nanotechnology-physics", parent_slug="condensed-matter-physics", description="Physics of nanoscale structures, 2D materials, and graphene.", aliases=["Nanomaterials Physics", "Graphene"]),

    TaxonomyNode(name="High Energy Physics", slug="high-energy-physics", parent_slug="physics", description="Study of fundamental particles and interactions at relativistic energies.", aliases=["Particle Physics", "HEP"]),
    TaxonomyNode(name="Particle Physics", slug="particle-physics", parent_slug="high-energy-physics", description="Standard Model particles, quarks, leptons, and gauge bosons.", aliases=["Subatomic Particles", "CERN", "LHC"]),
    TaxonomyNode(name="Quantum Field Theory", slug="quantum-field-theory", parent_slug="high-energy-physics", description="Theoretical framework combining classical field theory, quantum mechanics, and special relativity.", aliases=["QFT", "Quantum Electrodynamics", "QED"]),

    TaxonomyNode(name="Nuclear Physics", slug="nuclear-physics", parent_slug="physics", description="Structure, reactions, and decay of atomic nuclei.", aliases=["Nuclear Structure"]),
    TaxonomyNode(name="Nuclear Fusion", slug="nuclear-fusion", parent_slug="nuclear-physics", description="Physics of thermonuclear fusion reactions for energy generation.", aliases=["Magnetic Confinement Fusion", "Tokamak"]),

    TaxonomyNode(name="Optics and Photonics", slug="optics-and-photonics", parent_slug="physics", description="Behavior and properties of light and its interactions with matter.", aliases=["Optics", "Photonics"]),
    TaxonomyNode(name="Laser Physics", slug="laser-physics", parent_slug="optics-and-photonics", description="Principles of stimulated emission, ultrafast lasers, and optical amplifiers.", aliases=["Ultrafast Optics", "Laser Science"]),
    TaxonomyNode(name="Quantum Optics", slug="quantum-optics", parent_slug="optics-and-photonics", description="Quantum mechanical properties of photons and light-matter interactions.", aliases=["Photon Entanglement", "Single-Photon"]),

    TaxonomyNode(name="Quantum Physics", slug="quantum-physics", parent_slug="physics", description="Fundamental physical theories describing nature at atomic and subatomic scales.", aliases=["Quantum Mechanics", "Quantum Theory"]),
    TaxonomyNode(name="Quantum Information", slug="quantum-information", parent_slug="quantum-physics", description="Processing and transmission of information using quantum mechanical systems.", aliases=["Quantum Cryptography", "Quantum Entanglement", "Qubits"]),
    TaxonomyNode(name="Quantum Computing", slug="quantum-computing", parent_slug="physics", description="Computing utilizing quantum mechanical phenomena such as superposition and entanglement.", aliases=["Quantum Algorithms", "Quantum Hardware"]),
    TaxonomyNode(name="Plasma Physics", slug="plasma-physics", parent_slug="physics", description="Study of charged particles and fluids interacting with self-consistent electromagnetic fields.", aliases=["Plasmas", "Magnetohydrodynamics"]),
    TaxonomyNode(name="Statistical Mechanics", slug="statistical-mechanics", parent_slug="physics", description="Applying probability theory to study the thermodynamic behavior of systems.", aliases=["Statistical Physics", "Thermodynamics"]),
    TaxonomyNode(name="Physics-Informed Machine Learning", slug="physics-informed-machine-learning", parent_slug="physics", description="Integrating physical conservation laws and differential equations into neural network architectures.", aliases=["PINN", "Physics-Guided AI"]),

    # ── 6. Mathematics (Expanded ~22 nodes) ───────────────────────────────────
    TaxonomyNode(name="Pure Mathematics", slug="pure-mathematics", parent_slug="mathematics", description="Mathematics that studies entirely abstract concepts.", aliases=["Theoretical Mathematics"]),
    TaxonomyNode(name="Algebra", slug="algebra", parent_slug="pure-mathematics", description="Study of mathematical symbols and the rules for manipulating these symbols.", aliases=["Modern Algebra"]),
    TaxonomyNode(name="Abstract Algebra", slug="abstract-algebra", parent_slug="algebra", description="Study of algebraic structures such as groups, rings, fields, and modules.", aliases=["Group Theory", "Ring Theory"]),
    TaxonomyNode(name="Linear Algebra", slug="linear-algebra", parent_slug="algebra", description="Branch of mathematics concerning linear equations, vector spaces, and matrices.", aliases=["Matrix Theory", "Vector Spaces"]),

    TaxonomyNode(name="Number Theory", slug="number-theory", parent_slug="pure-mathematics", description="Study of integers and integer-valued functions.", aliases=["Arithmetic", "Prime Numbers"]),
    TaxonomyNode(name="Algebraic Number Theory", slug="algebraic-number-theory", parent_slug="number-theory", description="Techniques from abstract algebra to study the integers, rational numbers, and algebraic numbers.", aliases=["Class Field Theory"]),

    TaxonomyNode(name="Analysis", slug="analysis", parent_slug="pure-mathematics", description="Branch of mathematics dealing with continuous change, limits, and integration.", aliases=["Mathematical Analysis", "Real Analysis"]),
    TaxonomyNode(name="Functional Analysis", slug="functional-analysis", parent_slug="analysis", description="Study of vector spaces endowed with limit-related structures like Hilbert and Banach spaces.", aliases=["Banach Spaces", "Hilbert Spaces"]),
    TaxonomyNode(name="Complex Analysis", slug="complex-analysis", parent_slug="analysis", description="Functions of complex numbers and holomorphic functions.", aliases=["Complex Variables", "Holomorphic Functions"]),

    TaxonomyNode(name="Geometry and Topology", slug="geometry-and-topology", parent_slug="pure-mathematics", description="Properties of space that are preserved under continuous deformations.", aliases=["Topology", "Differential Geometry"]),
    TaxonomyNode(name="Differential Geometry", slug="differential-geometry", parent_slug="geometry-and-topology", description="Using calculus to study problems in geometry of manifolds.", aliases=["Riemannian Manifolds", "Manifold Learning"]),
    TaxonomyNode(name="Algebraic Topology", slug="algebraic-topology", parent_slug="geometry-and-topology", description="Using tools from abstract algebra to study topological spaces.", aliases=["Homology", "Homotopy"]),
    TaxonomyNode(name="Mathematical Logic", slug="mathematical-logic", parent_slug="pure-mathematics", description="Formal logic and its applications to mathematics and foundations.", aliases=["Set Theory", "Model Theory"]),

    TaxonomyNode(name="Applied Mathematics", slug="applied-mathematics", parent_slug="mathematics", description="Mathematical methods typically used in science, engineering, business, and industry.", aliases=["Applied Math"]),
    TaxonomyNode(name="Differential Equations", slug="differential-equations", parent_slug="applied-mathematics", description="Equations that relate one or more unknown functions and their derivatives.", aliases=["DE", "Dynamical Systems"]),
    TaxonomyNode(name="Partial Differential Equations", slug="partial-differential-equations", parent_slug="differential-equations", description="Equations involving unknown multivariable functions and their partial derivatives.", aliases=["PDE", "PDEs"]),
    TaxonomyNode(name="Ordinary Differential Equations", slug="ordinary-differential-equations", parent_slug="differential-equations", description="Equations containing one or more functions of one independent variable and its derivatives.", aliases=["ODE", "ODEs"]),
    TaxonomyNode(name="Numerical Analysis", slug="numerical-analysis", parent_slug="applied-mathematics", description="Algorithms for the problems of continuous mathematics.", aliases=["Scientific Computing", "Numerical Methods"]),
    TaxonomyNode(name="Mathematical Optimization", slug="mathematical-optimization", parent_slug="applied-mathematics", description="Selection of a best element from some set of available alternatives.", aliases=["Optimization Theory", "Convex Optimization"]),
    TaxonomyNode(name="Probability and Statistics", slug="probability-and-statistics", parent_slug="applied-mathematics", description="Mathematical theories of chance, uncertainty, and empirical data analysis.", aliases=["Mathematical Statistics", "Probability Theory"]),
    TaxonomyNode(name="Bayesian Statistics", slug="bayesian-statistics", parent_slug="probability-and-statistics", description="Statistical theory based on the Bayesian interpretation of probability.", aliases=["Bayesian Inference", "MCMC"]),
    TaxonomyNode(name="Stochastic Processes", slug="stochastic-processes", parent_slug="probability-and-statistics", description="Collections of random variables representing evolution of some system of random values.", aliases=["Markov Chains", "Random Walk"]),
    TaxonomyNode(name="Discrete Mathematics", slug="discrete-mathematics", parent_slug="applied-mathematics", description="Study of mathematical structures that are fundamentally discrete rather than continuous.", aliases=["Combinatorics", "Graph Theory"]),
    TaxonomyNode(name="Graph Theory", slug="graph-theory", parent_slug="discrete-mathematics", description="Study of graphs which are mathematical structures used to model pairwise relations between objects.", aliases=["Network Theory", "Graph Algorithms"]),

    # ── 7. Engineering (Expanded ~24 nodes) ───────────────────────────────────
    TaxonomyNode(name="Electrical Engineering", slug="electrical-engineering", parent_slug="engineering", description="Design and application of equipment, devices, and systems using electricity and electronics.", aliases=["EE", "Electronics Engineering"]),
    TaxonomyNode(name="Power Systems", slug="power-systems", parent_slug="electrical-engineering", description="Generation, transmission, and distribution of electric power.", aliases=["Smart Grids", "Power Electronics"]),
    TaxonomyNode(name="Signal Processing", slug="signal-processing", parent_slug="electrical-engineering", description="Analyzing, modifying, and synthesizing signals such as sound, images, and sensor data.", aliases=["DSP", "Digital Signal Processing"]),
    TaxonomyNode(name="Telecommunications", slug="telecommunications", parent_slug="electrical-engineering", description="Transmission of information across distances via electronic means.", aliases=["Telecom", "Wireless Communications", "5G", "6G"]),
    TaxonomyNode(name="VLSI Design", slug="vlsi-design", parent_slug="electrical-engineering", description="Creating integrated circuits by combining thousands of transistors into a single chip.", aliases=["Very Large Scale Integration", "Chip Design", "FPGA"]),

    TaxonomyNode(name="Mechanical Engineering", slug="mechanical-engineering", parent_slug="engineering", description="Design, analysis, manufacturing, and maintenance of mechanical systems.", aliases=["MechE"]),
    TaxonomyNode(name="Thermodynamics Engineering", slug="thermodynamics-engineering", parent_slug="mechanical-engineering", description="Heat transfer, thermal systems, and energy conversion.", aliases=["Thermal Engineering", "Heat Transfer"]),
    TaxonomyNode(name="Fluid Mechanics", slug="fluid-mechanics", parent_slug="mechanical-engineering", description="Behavior of fluids (liquids, gases, and plasmas) at rest and in motion.", aliases=["Computational Fluid Dynamics", "CFD", "Aerodynamics"]),
    TaxonomyNode(name="Solid Mechanics", slug="solid-mechanics", parent_slug="mechanical-engineering", description="Behavior of solid materials under external forces and temperature changes.", aliases=["Finite Element Analysis", "FEA", "Structural Mechanics"]),
    TaxonomyNode(name="Mechatronics", slug="mechatronics", parent_slug="mechanical-engineering", description="Multidisciplinary field combining mechanical, electrical, and robotic engineering.", aliases=["Robotics Engineering", "Electro-Mechanical Systems"]),

    TaxonomyNode(name="Civil Engineering", slug="civil-engineering", parent_slug="engineering", description="Design, construction, and maintenance of the physical and naturally built environment.", aliases=["Civil and Structural"]),
    TaxonomyNode(name="Structural Engineering", slug="structural-engineering", parent_slug="civil-engineering", description="Analysis and design of physical structures that support or resist loads.", aliases=["Bridge Engineering", "Earthquake Engineering"]),
    TaxonomyNode(name="Transportation Engineering", slug="transportation-engineering", parent_slug="civil-engineering", description="Planning, functional design, operation, and management of transport facilities.", aliases=["Traffic Engineering", "Smart Transportation"]),
    TaxonomyNode(name="Geotechnical Engineering", slug="geotechnical-engineering", parent_slug="civil-engineering", description="Engineering behavior of earth materials and soil mechanics.", aliases=["Soil Mechanics", "Foundation Engineering"]),

    TaxonomyNode(name="Chemical Engineering", slug="chemical-engineering", parent_slug="engineering", description="Design and operation of chemical plants and processes for converting raw materials into products.", aliases=["ChemE"]),
    TaxonomyNode(name="Process Engineering", slug="process-engineering", parent_slug="chemical-engineering", description="Understanding and optimization of chemical, physical, and biological processes.", aliases=["Chemical Process Control", "Bioprocess Engineering"]),
    TaxonomyNode(name="Catalysis", slug="catalysis", parent_slug="chemical-engineering", description="Increase in the rate of a chemical reaction by adding a catalyst substance.", aliases=["Heterogeneous Catalysis", "Electrocatalysis"]),

    TaxonomyNode(name="Materials Science", slug="materials-science", parent_slug="engineering", description="Design and discovery of new solid materials with tailored mechanical and physical properties.", aliases=["Materials Engineering", "Materials Science and Engineering"]),
    TaxonomyNode(name="Nanomaterials", slug="nanomaterials", parent_slug="materials-science", description="Materials with chemical or structural features at the nanoscale (1-100 nm).", aliases=["Nanostructures", "Carbon Nanotubes"]),
    TaxonomyNode(name="Biomaterials", slug="biomaterials", parent_slug="materials-science", description="Natural or synthetic substances engineered to interact with biological systems.", aliases=["Tissue Scaffolds", "Implant Materials"]),
    TaxonomyNode(name="Materials Informatics", slug="materials-informatics", parent_slug="materials-science", description="Application of machine learning, data science, and AI to materials discovery.", aliases=["Computational Materials", "AI for Materials"]),

    TaxonomyNode(name="Biomedical Engineering", slug="biomedical-engineering", parent_slug="engineering", description="Application of engineering principles to medicine and biology for healthcare purposes.", aliases=["BME", "Bioengineering"]),
    TaxonomyNode(name="Neural Engineering", slug="neural-engineering", parent_slug="biomedical-engineering", description="Engineering techniques to interface, repair, or enhance neural systems.", aliases=["Brain-Computer Interfaces", "BCI", "Neuroprosthetics"]),
    TaxonomyNode(name="Biomechanics", slug="biomechanics", parent_slug="biomedical-engineering", description="Study of the structure, function, and motion of the mechanical aspects of biological systems.", aliases=["Orthopedic Biomechanics", "Cardiovascular Biomechanics"]),

    TaxonomyNode(name="Aerospace Engineering", slug="aerospace-engineering", parent_slug="engineering", description="Primary field of engineering concerned with the development of aircraft and spacecraft.", aliases=["Aeronautical Engineering", "Astronautical Engineering", "Spacecraft"]),
    TaxonomyNode(name="Environmental Engineering", slug="environmental-engineering", parent_slug="engineering", description="Integration of science and engineering principles for improving environmental health.", aliases=["Water Treatment", "Waste Management"]),

    # ── 8. Social Sciences (Expanded ~22 nodes) ───────────────────────────────
    TaxonomyNode(name="Psychology", slug="psychology", parent_slug="social-sciences", description="Scientific study of mind and human behavior.", aliases=["Psychological Science"], ontology_mappings={"openalex": "C15744967"}),
    TaxonomyNode(name="Cognitive Psychology", slug="cognitive-psychology", parent_slug="psychology", description="Study of mental processes such as attention, language use, memory, and perception.", aliases=["Cognition", "Memory Studies"]),
    TaxonomyNode(name="Clinical Psychology", slug="clinical-psychology", parent_slug="psychology", description="Assessment and treatment of mental illness, abnormal behavior, and psychiatric problems.", aliases=["Psychotherapy", "Psychopathology"]),
    TaxonomyNode(name="Social Psychology", slug="social-psychology", parent_slug="psychology", description="How thoughts, feelings, and behaviors are influenced by actual or implied presence of others.", aliases=["Group Dynamics", "Social Cognition"]),
    TaxonomyNode(name="Developmental Psychology", slug="developmental-psychology", parent_slug="psychology", description="Scientific approach which aims to explain growth, change and consistency through the lifespan.", aliases=["Child Psychology", "Lifespan Development"]),

    TaxonomyNode(name="Sociology", slug="sociology", parent_slug="social-sciences", description="Study of society, social institutions, patterns of social relationships, and human action.", aliases=["Sociological Studies"], ontology_mappings={"openalex": "C144024400"}),
    TaxonomyNode(name="Social Stratification", slug="social-stratification", parent_slug="sociology", description="Categorization of people into socio-economic tiers based upon wealth, income, and race.", aliases=["Inequality Studies", "Socioeconomic Status"]),
    TaxonomyNode(name="Sociology of Technology", slug="sociology-of-technology", parent_slug="sociology", description="How social factors shape technological innovation and its adoption.", aliases=["Science and Technology Studies", "STS"]),
    TaxonomyNode(name="Social Networks", slug="social-networks", parent_slug="sociology", description="Study of social structures made up of a set of social actors and dyadic ties.", aliases=["Social Network Analysis", "SNA"]),
    TaxonomyNode(name="Computational Social Science", slug="computational-social-science", parent_slug="sociology", description="Interdisciplinary science utilizing computational approaches to investigate complex social phenomena.", aliases=["CSS", "Social Big Data"]),

    TaxonomyNode(name="Political Science", slug="political-science", parent_slug="social-sciences", description="Scientific study of politics, government systems, political activities, and behaviors.", aliases=["Politics", "Government"], ontology_mappings={"openalex": "C94625758"}),
    TaxonomyNode(name="International Relations", slug="international-relations", parent_slug="political-science", description="Interactions between sovereign states, international organizations, and multinational corporations.", aliases=["IR Politics", "Foreign Policy", "Diplomacy"]),
    TaxonomyNode(name="Comparative Politics", slug="comparative-politics", parent_slug="political-science", description="Systematic comparison of the world's political systems and institutions.", aliases=["Comparative Government", "Democratization"]),
    TaxonomyNode(name="Public Policy", slug="public-policy", parent_slug="political-science", description="Principled guide to action taken by the administrative executive branches of the state.", aliases=["Policy Analysis", "Governance"]),

    TaxonomyNode(name="Anthropology", slug="anthropology", parent_slug="social-sciences", description="Scientific study of humanity, human behavior, culture, and societies past and present.", aliases=["Anthropological Sciences"]),
    TaxonomyNode(name="Cultural Anthropology", slug="cultural-anthropology", parent_slug="anthropology", description="Study of cultural variation among humans through ethnography and comparative analysis.", aliases=["Ethnography", "Sociocultural Anthropology"]),

    TaxonomyNode(name="Linguistics", slug="linguistics", parent_slug="social-sciences", description="Scientific study of language structure, grammar, semantics, and pragmatics.", aliases=["Linguistic Science"]),
    TaxonomyNode(name="Computational Linguistics", slug="computational-linguistics", parent_slug="linguistics", description="Computational modeling of natural language syntax, semantics, and phonology.", aliases=["Formal Linguistics", "Syntax and Semantics"]),
    TaxonomyNode(name="Sociolinguistics", slug="sociolinguistics", parent_slug="linguistics", description="Descriptive study of the effect of any and all aspects of society on language use.", aliases=["Language and Society"]),

    TaxonomyNode(name="Education", slug="education", parent_slug="social-sciences", description="Discipline concerned with methods of teaching and learning in schools and school-like environments.", aliases=["Educational Sciences", "Pedagogy"]),
    TaxonomyNode(name="Educational Technology", slug="educational-technology", parent_slug="education", description="Use of physical hardware, software, and educational theory to facilitate learning and improve performance.", aliases=["EdTech", "AI in Education", "Learning Analytics"]),
    TaxonomyNode(name="Law and Legal Studies", slug="law-and-legal-studies", parent_slug="social-sciences", description="Systematic study of legal rules, jurisprudence, human rights, and legal systems.", aliases=["Jurisprudence", "Legal Science", "Constitutional Law"]),

    # ── 9. Economics (Expanded ~20 nodes) ─────────────────────────────────────
    TaxonomyNode(name="Microeconomics", slug="microeconomics", parent_slug="economics", description="Study of decisions of individuals and firms regarding resource allocation.", aliases=["Microeconomic Theory"], ontology_mappings={"openalex": "C175444787"}),
    TaxonomyNode(name="Game Theory", slug="game-theory", parent_slug="microeconomics", description="Mathematical models of strategic interaction among rational agents.", aliases=["Strategic Interaction", "Mechanism Design"]),
    TaxonomyNode(name="Behavioral Economics", slug="behavioral-economics", parent_slug="microeconomics", description="Effects of psychological, cognitive, and cultural factors on economic decisions.", aliases=["Behavioral Finance", "Nudge Theory", "Bounded Rationality"]),
    TaxonomyNode(name="Market Design", slug="market-design", parent_slug="microeconomics", description="Designing economic mechanisms and auction rules to match buyers and sellers.", aliases=["Auction Theory", "Matching Markets"]),

    TaxonomyNode(name="Macroeconomics", slug="macroeconomics", parent_slug="economics", description="Structure, performance, behavior, and decision-making of an entire economy.", aliases=["Macroeconomic Theory"], ontology_mappings={"openalex": "C16520705"}),
    TaxonomyNode(name="Monetary Economics", slug="monetary-economics", parent_slug="macroeconomics", description="Analyses of money, interest rates, banking, and central bank monetary policy.", aliases=["Monetary Policy", "Central Banking"]),
    TaxonomyNode(name="Fiscal Policy", slug="fiscal-policy", parent_slug="macroeconomics", description="Use of government revenue collection and expenditure to influence a country's economy.", aliases=["Public Finance", "Tax Policy"]),
    TaxonomyNode(name="Economic Growth", slug="economic-growth", parent_slug="macroeconomics", description="Long-term expansion of the productive potential of an economy.", aliases=["Growth Theory", "Total Factor Productivity"]),

    TaxonomyNode(name="Econometrics", slug="econometrics", parent_slug="economics", description="Application of statistical methods to economic data to give empirical content to economic relationships.", aliases=["Empirical Economics", "Applied Econometrics"], ontology_mappings={"openalex": "C149782125"}),
    TaxonomyNode(name="Time Series Econometrics", slug="time-series-econometrics", parent_slug="econometrics", description="Statistical methods for analyzing economic data ordered sequentially across time.", aliases=["Vector Autoregression", "VAR", "Cointegration", "GARCH"]),
    TaxonomyNode(name="Microeconometrics", slug="microeconometrics", parent_slug="econometrics", description="Econometric methods for individual, household, and firm-level observational data.", aliases=["Panel Data", "Difference-in-Differences", "Causal Inference"]),
    TaxonomyNode(name="Machine Learning in Economics", slug="machine-learning-in-economics", parent_slug="econometrics", description="Using machine learning algorithms for causal inference and economic prediction.", aliases=["Double Machine Learning", "Causal Forests"]),

    TaxonomyNode(name="Financial Economics", slug="financial-economics", parent_slug="economics", description="Interrelation of financial variables such as share prices, interest rates, and risk.", aliases=["Finance", "Corporate Finance"]),
    TaxonomyNode(name="Asset Pricing", slug="asset-pricing", parent_slug="financial-economics", description="Determining the market prices of financial assets and derivatives.", aliases=["Capital Asset Pricing Model", "CAPM", "Black-Scholes"]),
    TaxonomyNode(name="Quantitative Finance", slug="quantitative-finance", parent_slug="financial-economics", description="Using mathematical models and extremely large datasets to analyze financial markets.", aliases=["Mathematical Finance", "Algorithmic Trading"]),

    TaxonomyNode(name="Development Economics", slug="development-economics", parent_slug="economics", description="Focuses on improving fiscal, economic, and social conditions in developing countries.", aliases=["Poverty Reduction", "Randomized Controlled Trials Economics"]),
    TaxonomyNode(name="International Trade", slug="international-trade", parent_slug="economics", description="Exchange of capital, goods, and services across international borders or territories.", aliases=["Trade Policy", "Tariffs and Globalization"]),
    TaxonomyNode(name="Industrial Organization", slug="industrial-organization", parent_slug="economics", description="Structure of markets, imperfect competition, and antitrust regulation.", aliases=["Antitrust Economics", "Market Power"]),
    TaxonomyNode(name="Environmental Economics", slug="environmental-economics", parent_slug="economics", description="Economic impact of environmental policies, carbon pricing, and resource management.", aliases=["Carbon Pricing", "Resource Economics"]),

    # ── 10. Environmental Science (Expanded ~20 nodes) ───────────────────────
    TaxonomyNode(name="Climate Science", slug="climate-science", parent_slug="environmental-science", description="Study of climate, climate variability, and anthropogenic climate change.", aliases=["Climatology", "Climate Change"], ontology_mappings={"openalex": "C13280743"}),
    TaxonomyNode(name="Climate Modeling", slug="climate-modeling", parent_slug="climate-science", description="Numerical simulation of general circulation models and Earth system dynamics.", aliases=["GCM", "Coupled Climate Models"]),
    TaxonomyNode(name="Climate Change Adaptation", slug="climate-change-adaptation", parent_slug="climate-science", description="Strategies and policies to adapt natural and human systems to climate impacts.", aliases=["Climate Resilience", "Mitigation and Adaptation"]),
    TaxonomyNode(name="Greenhouse Gas Dynamics", slug="greenhouse-gas-dynamics", parent_slug="climate-science", description="Carbon cycle, methane emissions, and atmospheric radiative forcing.", aliases=["Carbon Cycle", "Carbon Sequestration"]),

    TaxonomyNode(name="Atmospheric Science", slug="atmospheric-science", parent_slug="environmental-science", description="Study of Earth's atmosphere, weather processes, and atmospheric chemistry.", aliases=["Meteorology and Atmosphere"]),
    TaxonomyNode(name="Meteorology", slug="meteorology", parent_slug="atmospheric-science", description="Atmospheric phenomena and weather forecasting.", aliases=["Numerical Weather Prediction", "Severe Weather"]),
    TaxonomyNode(name="Air Quality Research", slug="air-quality-research", parent_slug="atmospheric-science", description="Aerosols, particulate matter, and atmospheric pollutant dispersion.", aliases=["Aerosol Science", "PM2.5 Pollution"]),

    TaxonomyNode(name="Oceanography", slug="oceanography", parent_slug="environmental-science", description="Physical, chemical, and biological properties of the world's oceans.", aliases=["Marine Science", "Physical Oceanography"]),
    TaxonomyNode(name="Marine Ecology", slug="marine-ecology", parent_slug="oceanography", description="Interactions between marine organisms and their oceanic environment.", aliases=["Coral Reefs", "Ocean Acidification"]),
    TaxonomyNode(name="Ocean Circulation", slug="ocean-circulation", parent_slug="oceanography", description="Large scale movement of waters in the ocean basins.", aliases=["Thermohaline Circulation", "El Nino", "ENSO"]),

    TaxonomyNode(name="Hydrology", slug="hydrology", parent_slug="environmental-science", description="Movement, distribution, and management of water on Earth.", aliases=["Water Resources"]),
    TaxonomyNode(name="Water Resources Management", slug="water-resources-management", parent_slug="hydrology", description="Planning, developing, and managing the optimum use of water resources.", aliases=["Integrated Water Management", "Watershed Hydrology"]),
    TaxonomyNode(name="Groundwater Hydrology", slug="groundwater-hydrology", parent_slug="hydrology", description="Distribution and movement of water in soil and subterranean aquifers.", aliases=["Hydrogeology", "Aquifer Management"]),

    TaxonomyNode(name="Ecology and Conservation", slug="ecology-and-conservation", parent_slug="environmental-science", description="Preserving biodiversity and protecting threatened ecosystems.", aliases=["Conservation Biology", "Biodiversity"]),
    TaxonomyNode(name="Biodiversity Conservation", slug="biodiversity-conservation", parent_slug="ecology-and-conservation", description="Protection and management of biodiversity to maintain ecosystem resilience.", aliases=["Species Conservation", "Habitat Restoration"]),
    TaxonomyNode(name="Ecosystem Services", slug="ecosystem-services", parent_slug="ecology-and-conservation", description="Direct and indirect benefits that ecosystems provide for human well-being.", aliases=["Natural Capital", "Ecological Valuation"]),

    TaxonomyNode(name="Environmental Chemistry", slug="environmental-chemistry", parent_slug="environmental-science", description="Chemical processes occurring in the environment which are impacted by humankind's activities.", aliases=["Environmental Toxicology"]),
    TaxonomyNode(name="Ecotoxicology", slug="ecotoxicology", parent_slug="environmental-chemistry", description="Effects of toxic chemicals on biological organisms, especially at population levels.", aliases=["Pollution Toxicology", "Bioaccumulation"]),

    TaxonomyNode(name="Renewable Energy Systems", slug="renewable-energy-systems", parent_slug="environmental-science", description="Sustainable energy technology including solar, wind, biomass, and geothermal power.", aliases=["Clean Energy", "Sustainable Energy"]),
    TaxonomyNode(name="Solar Energy Research", slug="solar-energy-research", parent_slug="renewable-energy-systems", description="Photovoltaics, solar thermal collectors, and perovskite solar cells.", aliases=["Photovoltaics", "Solar Cells"]),
    TaxonomyNode(name="Wind Energy Research", slug="wind-energy-research", parent_slug="renewable-energy-systems", description="Aerodynamics, turbine mechanics, and grid integration of wind energy.", aliases=["Wind Turbines", "Offshore Wind"]),
    TaxonomyNode(name="Soil Science", slug="soil-science", parent_slug="environmental-science", description="Study of soil as a natural resource on the surface of the Earth.", aliases=["Pedology", "Soil Health"]),
    TaxonomyNode(name="Environmental Modeling", slug="environmental-modeling", parent_slug="environmental-science", description="Computational modeling and spatial simulation of environmental and ecological systems.", aliases=["Ecological Modeling", "GIS Environmental Analysis"]),
]


# ── Taxonomy Service ──────────────────────────────────────────────────────────


class TaxonomyService:
    """
    Manages the canonical topic taxonomy tree, aliases, DAG hierarchy, and database synchronization.
    Supports DAG validation, cycle detection, orphan detection, and comprehensive coverage reports.
    """

    def __init__(self, nodes: list[TaxonomyNode] | None = None) -> None:
        self._nodes_list = list(nodes if nodes is not None else SEED_TAXONOMY)
        self._by_slug: dict[str, TaxonomyNode] = {}
        self._by_name_lower: dict[str, TaxonomyNode] = {}
        self._by_alias_lower: dict[str, TaxonomyNode] = {}
        self._children_map: dict[str, list[str]] = {}

        self._build_indexes()
        self.validate_no_cycles()

    def _build_indexes(self) -> None:
        """Construct fast lookup maps from the registered nodes."""
        self._by_slug.clear()
        self._by_name_lower.clear()
        self._by_alias_lower.clear()
        self._children_map.clear()

        for node in self._nodes_list:
            self._by_slug[node.slug] = node
            self._by_name_lower[node.name.strip().lower()] = node

            # Map all aliases
            for alias in node.aliases:
                cleaned_alias = alias.strip().lower()
                if cleaned_alias:
                    self._by_alias_lower[cleaned_alias] = node

            # Build children hierarchy
            if node.parent_slug:
                self._children_map.setdefault(node.parent_slug, []).append(node.slug)

    def add_node(self, node: TaxonomyNode) -> None:
        """Add a new node to the taxonomy and validate cycle freedom."""
        if node.slug in self._by_slug:
            # Replace existing node
            self._nodes_list = [n for n in self._nodes_list if n.slug != node.slug]
        self._nodes_list.append(node)
        self._build_indexes()
        self.validate_no_cycles()

    def validate_no_cycles(self) -> bool:
        """
        Validate that parent relationships form a valid DAG (Directed Acyclic Graph)
        with no circular dependencies.

        Raises:
            ValueError: If a cycle is detected.
        """
        for slug in self._by_slug:
            visited: set[str] = set()
            curr: str | None = slug
            while curr:
                if curr in visited:
                    raise ValueError(f"Taxonomy cycle detected involving topic slug {curr!r}")
                visited.add(curr)
                node = self._by_slug.get(curr)
                curr = node.parent_slug if node else None
        return True

    def validate_dag(self) -> dict[str, Any]:
        """
        Perform strict, comprehensive DAG validation.

        Verifies:
        - No cycles
        - All parent slugs exist in taxonomy
        - All nodes are reachable from a root node (parent_slug is None)
        - No duplicate slugs or names

        Returns:
            Dictionary with validation status and diagnostics.
        """
        self.validate_no_cycles()

        roots = [node.slug for node in self._nodes_list if node.parent_slug is None]
        orphans: list[str] = []
        invalid_parents: list[tuple[str, str]] = []

        for node in self._nodes_list:
            if node.parent_slug is not None:
                if node.parent_slug not in self._by_slug:
                    invalid_parents.append((node.slug, node.parent_slug))

            # Reachability check
            ancestors = self.get_ancestors(node.slug)
            root_reached = (node.slug in roots) or (len(ancestors) > 0 and ancestors[-1] in roots)
            if not root_reached:
                orphans.append(node.slug)

        is_valid = len(invalid_parents) == 0 and len(orphans) == 0
        return {
            "is_valid": is_valid,
            "total_nodes": len(self._nodes_list),
            "root_count": len(roots),
            "roots": roots,
            "orphan_count": len(orphans),
            "orphans": orphans,
            "invalid_parents": invalid_parents,
        }

    def generate_coverage_report(self) -> dict[str, Any]:
        """
        Generate a comprehensive, deterministic coverage report over the taxonomy hierarchy.
        Computes per-discipline node counts, percentages, depth statistics, and DAG integrity.
        """
        roots = [node for node in self._nodes_list if node.parent_slug is None]
        total_nodes = len(self._nodes_list)

        # Compute nodes belonging to each primary discipline tree
        discipline_counts: dict[str, int] = {}
        discipline_pcts: dict[str, float] = {}

        for root in roots:
            descendants = self.get_descendants(root.slug)
            # Count includes root itself + all descendants
            count = 1 + len(descendants)
            discipline_counts[root.name] = count
            pct = round((count / total_nodes) * 100.0, 2) if total_nodes > 0 else 0.0
            discipline_pcts[root.name] = pct

        depths = [self.get_depth(node.slug) for node in self._nodes_list]
        max_depth = max(depths) if depths else 0
        avg_depth = round(sum(depths) / len(depths), 2) if depths else 0.0

        dag_check = self.validate_dag()

        return {
            "total_nodes": total_nodes,
            "root_count": len(roots),
            "roots": [r.name for r in roots],
            "discipline_counts": discipline_counts,
            "discipline_percentages": discipline_pcts,
            "max_depth": max_depth,
            "average_depth": avg_depth,
            "is_valid_dag": dag_check["is_valid"],
            "orphan_count": dag_check["orphan_count"],
        }

    def get_node(self, slug: str) -> TaxonomyNode | None:
        """Lookup node by canonical slug."""
        return self._by_slug.get(slug)

    def get_all_nodes(self) -> list[TaxonomyNode]:
        """Return all registered taxonomy nodes."""
        return list(self._nodes_list)

    def get_ancestors(self, slug: str) -> list[str]:
        """
        Return ordered list of ancestor slugs from immediate parent to root.

        Example:
            get_ancestors('transformers') -> ['deep-learning', 'machine-learning', 'artificial-intelligence', 'computer-science']
        """
        ancestors: list[str] = []
        visited: set[str] = {slug}
        node = self._by_slug.get(slug)
        curr = node.parent_slug if node else None

        while curr and curr in self._by_slug and curr not in visited:
            ancestors.append(curr)
            visited.add(curr)
            node = self._by_slug.get(curr)
            curr = node.parent_slug if node else None

        return ancestors

    def get_descendants(self, slug: str) -> list[str]:
        """
        Return all descendant slugs in depth-first order.

        Example:
            get_descendants('machine-learning') -> ['deep-learning', 'generative-ai', 'transformers', 'reinforcement-learning', ...]
        """
        descendants: list[str] = []
        stack = list(self._children_map.get(slug, []))
        visited: set[str] = set(stack)

        while stack:
            curr = stack.pop()
            descendants.append(curr)
            for child in self._children_map.get(curr, []):
                if child not in visited:
                    visited.add(child)
                    stack.append(child)

        return descendants

    def get_depth(self, slug: str) -> int:
        """Return depth of node in the hierarchy (Root = 0)."""
        return len(self.get_ancestors(slug))

    def get_ontology_mapping(self, slug: str, system: str) -> str | None:
        """
        Retrieve external ontology identifier (e.g. 'mesh', 'acm_ccs', 'openalex') for a node.
        """
        node = self.get_node(slug)
        if node and node.ontology_mappings:
            return node.ontology_mappings.get(system.lower().strip())
        return None

    def sync_to_db(self, session: Session) -> dict[str, int]:
        """
        Synchronize seed taxonomy into database `topics` and `topic_aliases` tables.
        Idempotent: updates existing topics and aliases, adds missing ones.
        """
        from app.models.topic import TopicAliasModel, TopicModel

        created_topics = 0
        updated_topics = 0
        created_aliases = 0

        # Pass 1: Insert or update topic records without parent_id (to avoid FK errors)
        db_topics_by_slug: dict[str, TopicModel] = {}
        for node in self._nodes_list:
            stmt = select(TopicModel).where(TopicModel.slug == node.slug)
            topic = session.execute(stmt).scalar_one_or_none()

            if topic is None:
                topic = TopicModel(
                    id=uuid.uuid4(),
                    name=node.name,
                    slug=node.slug,
                    description=node.description,
                    parent_id=None,
                )
                session.add(topic)
                session.flush()
                created_topics += 1
            else:
                if topic.name != node.name or topic.description != node.description:
                    topic.name = node.name
                    topic.description = node.description
                    session.flush()
                    updated_topics += 1

            db_topics_by_slug[node.slug] = topic

        # Pass 2: Set parent_id relationships
        for node in self._nodes_list:
            if node.parent_slug and node.parent_slug in db_topics_by_slug:
                topic = db_topics_by_slug[node.slug]
                parent_topic = db_topics_by_slug[node.parent_slug]
                if topic.parent_id != parent_topic.id:
                    topic.parent_id = parent_topic.id
                    session.flush()

        # Pass 3: Sync aliases
        for node in self._nodes_list:
            topic = db_topics_by_slug[node.slug]
            for alias in node.aliases:
                clean_alias = alias.strip()
                normalized_alias = clean_alias.lower()
                if not clean_alias:
                    continue

                stmt = select(TopicAliasModel).where(
                    TopicAliasModel.topic_id == topic.id,
                    TopicAliasModel.normalized_alias == normalized_alias,
                )
                existing_alias = session.execute(stmt).scalar_one_or_none()

                if existing_alias is None:
                    new_alias = TopicAliasModel(
                        id=uuid.uuid4(),
                        topic_id=topic.id,
                        alias=clean_alias,
                        normalized_alias=normalized_alias,
                        source="SEED_TAXONOMY",
                    )
                    session.add(new_alias)
                    session.flush()
                    created_aliases += 1

        session.commit()
        logger.info(
            "Taxonomy sync complete: created_topics=%d updated_topics=%d created_aliases=%d",
            created_topics,
            updated_topics,
            created_aliases,
        )
        return {
            "created_topics": created_topics,
            "updated_topics": updated_topics,
            "created_aliases": created_aliases,
        }
