# Academic Relevance Annotation Guidelines

**Version:** v1.0-2026  
**Status:** Canonical Reference Standard  
**Applicability:** ResearchConnect AI Discovery & Ranking Evaluation Benchmarks  

---

## 1. Purpose & Scope

These guidelines establish a formal, reproducible rubric for annotating query-document relevance judgments across academic literature retrieval and opportunity matching. The goal is to produce deterministic, human-auditable ground truth for evaluating retrieval systems, hybrid rankers, and cross-encoder rerankers.

---

## 2. Graded Relevance Scale (0–3)

Each candidate research paper or academic opportunity is evaluated on a 4-point ordinal scale:

| Grade | Label | Operational Definition | Inclusion Standard |
| :---: | :--- | :--- | :--- |
| **3** | **Highly Relevant** | Directly addresses the primary research question, methodology, or task described in the query. Provides central findings, foundational theorems, or primary clinical/empirical results. | The researcher would cite this work immediately or submit directly to this venue. |
| **2** | **Relevant** | Substantially related to the query topic. May address a closely related subfield, apply the query's method in an adjacent context, or offer a valuable survey/framework. | Highly useful background literature or relevant domain call for papers. |
| **1** | **Marginally Relevant** | Tangentially related. Mentions query keywords or methodology in passing, but the core contribution is distinct. | Broad context only; would not directly satisfy the researcher's query. |
| **0** | **Irrelevant** | Completely unrelated or shares incidental vocabulary without conceptual overlap. | Excluded from useful result sets. |

---

## 3. Multidimensional Relevance Criteria

Relevance judgments must evaluate five core dimensions:

### 3.1 Topical Relevance
- **Direct Match (Grade 3)**: Core focus of paper matches query concepts (e.g. *Graph Neural Networks for Drug Discovery* $\to$ *GNN molecular property prediction*).
- **Broader/Narrower Match (Grade 2)**: Paper covers the broader domain (e.g. *Deep Learning in Chemistry*) or a specific sub-case (e.g. *Message Passing in Small Molecules*).

### 3.2 Methodological Relevance
- When queries specify an empirical, statistical, or mathematical method (e.g., *Instrumental Variables*, *Hamiltonian Monte Carlo*, *Finite Element Analysis*), candidates employing that exact methodology score higher than purely theoretical or unrelated empirical treatments.

### 3.3 Disciplinary & Boundary Alignment
- Queries must be judged within their intended discipline. If a query has cross-disciplinary applications (e.g., *Topological Data Analysis in Neuroscience*), works bridging both domains earn Grade 3; works in only one domain with methodological applicability earn Grade 2.

### 3.4 Temporal Relevance
- Emerging methods (e.g., *LLM alignment*, *Transformer architectures*) prioritize recent foundational works, while historical/foundational queries (e.g., *Navier-Stokes existence theorems*) evaluate theoretical validity regardless of publication year.

### 3.5 Duplicate & Near-Duplicate Handling
- Preprints (e.g. arXiv) and subsequent peer-reviewed journal articles on identical content are assigned identical relevance grades.

---

## 4. Special Query Class Handling

### 4.1 Polysemous & Ambiguous Acronyms
- **SEM**: If query contains social science keywords $\to$ *Structural Equation Modeling*; if materials/microscopy keywords $\to$ *Scanning Electron Microscopy*.
- **IV**: If economics/statistics context $\to$ *Instrumental Variables*; if pharmacology/medicine context $\to$ *Intravenous*.
- **PCA**: If statistics/ML context $\to$ *Principal Component Analysis*; if anesthesia/pain management context $\to$ *Patient-Controlled Analgesia*.

### 4.2 Incomplete or Truncated Metadata
- When abstracts are brief or truncated, annotators must evaluate title clarity, venue reputation, and canonical topic taxonomy associations before downgrading relevance.

---

## 5. Inter-Annotator Agreement Standards

To ensure scientific defensibility:
- Every query scenario is evaluated against this standard rubric.
- Paired annotator evaluations compute **Cohen's Kappa ($\kappa$)**; multi-annotator panels compute **Fleiss' Kappa**.
- Acceptable benchmark agreement threshold: $\kappa \ge 0.65$ (Substantial Agreement) with mandatory adjudication for $\kappa < 0.60$.
