# Signature scoring

How TRACE turns one gene or a gene set into one score per sample

**Contract:** `trace-signature-scoring-methods-v2`  
**Scoring engine contract:** `bioconductor-single-sample-scoring-v2.0`  
**Reviewed:** 2026-09-07  
**Public HTML:** `https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/`  
**In-app explanation:** `https://apps.cienciavida.org/tcga_explorer/?view=help#trace-guide-methods-signature-scoring`  
**Source SHA-256:** `4f9349a7a6c7e373f7a67aa9362da40c9386535361168eb7e0edff671000fd5c`

A signature score is a compact summary of expression. It does not by itself establish pathway activity, prognosis or treatment response.

TRACE records the expression layer, resolved genes, scoring population, method parameters and score hash so the calculation can be inspected and repeated.

## Recommended starting point

For a bulk-RNA signature that may be examined across cohorts, start with singscore. It ranks genes within each sample and does not estimate its reference distribution from the other patients in the run.

## What happens before a score is returned

1. **Choose the expression layer.** TRACE uses the analysis-ready layer declared by the dataset. Uploaded counts or abundance values are transformed during import according to their declared unit; the scorer never guesses a scale.

2. **Resolve the signature.** Gene symbols and supported aliases are resolved before scoring. Every requested component must map. Consistent duplicates are reported and counted once; conflicting weights or directions are rejected.

3. **Fix the patient and feature universe.** The selected molecular population or external sample types are applied before choosing one RNA profile per participant. Arithmetic scores use the analysis-eligible complete cases. Rank-based scores use this molecular population and the full frozen feature universe before endpoint and clinical filters are applied. Choosing a different tissue population changes the scoring population; it never falls back to another tissue type.

4. **Calculate and record the score.** TRACE stores the method, parameters, direction of every component, population counts, resolved feature universe and a hash of the resulting score vector. Clinical filters are part of this record.

## Notation

| Symbol | Meaning |
| --- | --- |
| xᵢg | analysis-ready expression for sample i and gene g |
| w₍g₎ | user-supplied gene weight; the default is 1 |
| G | number of distinct resolved genes in the signature |
| U | number of usable genes in the frozen expression-layer universe |

## Scoring methods

### Single gene (`single`)

**Status:** Available  
**Role:** Direct expression  
**Engine:** TRACE native scorer  
**Formula:** `Sᵢ = xᵢg`  
**Parameters:** Exactly one resolved gene.  
**Direction:** A direction is not applied. The score retains the expression direction of the selected gene.  
**Gene universe:** The selected gene. Participants without its expression value are excluded.  
**Dependence on the run:** The same stored expression value does not change when other participants are added or removed.  
**Interpretation:** A one-unit score difference is one unit on the declared expression layer.  
**Limit:** Values from different expression layers or processing pipelines are not directly interchangeable.

### Mean (`mean`)

**Status:** Available  
**Role:** Transparent arithmetic score  
**Engine:** TRACE native scorer  
**Formula:** `Sᵢ = (1/G) Σg xᵢg`  
**Parameters:** Two or more resolved genes; all components receive equal weight.  
**Direction:** All genes are treated as positive components.  
**Gene universe:** The resolved signature genes. Only participants with expression for every component are scored.  
**Dependence on the run:** It does not use other participants, but it depends directly on the expression scale.  
**Interpretation:** Higher scores mean higher average expression of the listed genes on the declared layer.  
**Limit:** Highly expressed genes can dominate the average. Use only genes measured on a common, appropriate scale.

### Weighted mean (`weighted`)

**Status:** Available  
**Role:** Signed arithmetic score  
**Engine:** TRACE native scorer  
**Formula:** `Sᵢ = Σg w₍g₎xᵢg / Σg |w₍g₎|`  
**Parameters:** Two or more resolved genes with finite, non-zero weights.  
**Direction:** Positive weights increase the score; negative weights decrease it. Weight magnitude is retained.  
**Gene universe:** The resolved signature genes. Only participants with expression for every component are scored.  
**Dependence on the run:** It does not use other participants, but it depends directly on the expression scale and chosen weights.  
**Interpretation:** The sign and magnitude follow the declared weights and expression layer.  
**Limit:** Weights learned in another assay may not transfer to a new processing pipeline.

### Z-score mean (`zscore`)

**Status:** Available  
**Role:** Within-run standardized score  
**Engine:** TRACE native scorer  
**Formula:** `Sᵢ = Σg w₍g₎[(xᵢg − x̄g)/s₍g₎] / Σg |w₍g₎|`  
**Parameters:** Two or more resolved genes with finite, non-zero weights; x̄g and sample SD s₍g₎ are estimated among eligible, expression-complete participants in the run.  
**Direction:** Positive weights increase the score; negative weights decrease it. Weight magnitude is retained.  
**Gene universe:** The resolved signature genes and the eligible complete-case scoring population.  
**Dependence on the run:** Yes. Changing clinical filters, endpoint eligibility or cohort composition can change every score.  
**Interpretation:** A higher value means higher standardized expression relative to this run, not an absolute cross-study value.  
**Limit:** Do not compare numerical z-scores from separately scored cohorts. Constant components contribute no variation and are reported.

### singscore (`singscore`)

**Status:** Available  
**Role:** Recommended rank-based bulk score  
**Engine:** singscore::rankGenes + singscore::simpleScore  
**Formula:** `Sᵢ = singscore TotalScore from centered within-sample ranks`  
**Parameters:** rankGenes(tiesMethod = "min"); simpleScore(centerScore = TRUE, knownDirection = TRUE).  
**Direction:** Plain genes and +1 weights form upSet; −1 weights form downSet. Other weight magnitudes and zero are rejected because rank methods do not estimate weighted effects.  
**Gene universe:** All usable genes in the selected frozen expression layer for that sample.  
**Dependence on the run:** It does not estimate ranks from other participants. Scores can still change if the measured gene universe, preprocessing or signature mapping changes.  
**Interpretation:** Higher TotalScore means positive genes rank higher and negative genes rank lower within the sample.  
**Limit:** Cross-study interpretation still requires comparable feature universes and attention to assay, batch and tissue composition.

### ssGSEA (`ssgsea`)

**Status:** Available  
**Role:** Sample-wise enrichment score  
**Engine:** GSVA::ssgseaParam + GSVA::gsva  
**Formula:** `Sᵢ = ESᵢ(up) − ESᵢ(down); a missing direction contributes 0`  
**Parameters:** alpha = 0.25, normalize = FALSE, minSize = 2, maxSize = Inf.  
**Direction:** Plain genes and +1 weights form the positive set; −1 weights form the negative set. Other magnitudes and zero are rejected.  
**Gene universe:** All usable genes in the selected frozen expression layer for that sample. Each non-empty direction must retain at least two mapped genes.  
**Dependence on the run:** The enrichment walk is sample-wise and TRACE disables across-sample range normalization. Scores can still change with the feature universe, preprocessing and ties.  
**Interpretation:** Higher values indicate relative enrichment of the positive component over the negative component within a sample.  
**Limit:** Numerical scores should not be assumed exchangeable across assays. Signature size and gene-gene correlation affect behaviour.

### AUCell (`aucell`)

**Status:** Available  
**Role:** Top-ranked activity sensitivity  
**Engine:** AUCell::AUCell_buildRankings + AUCell::AUCell_calcAUC  
**Formula:** `Sᵢ = normalized AUCᵢ(up) − normalized AUCᵢ(down)`  
**Parameters:** Sequential ranking with package-defined random tie handling; keepZeroesAsNA = FALSE; aucMaxRank = ceiling(0.05 × U); normAUC = TRUE. Per-sample seed = first 8 hex digits of SHA-256("bioconductor-single-sample-scoring-v2.0|1|<sample ID>"), modulo 2,147,483,646, plus 1.  
**Direction:** Plain genes and +1 weights form the positive set; −1 weights form the negative set. Other magnitudes and zero are rejected.  
**Gene universe:** All usable genes in the selected frozen expression layer for that sample; U and the resulting aucMaxRank are exported.  
**Dependence on the run:** Ranking is performed per sample. Results still depend on feature detection, ties, the feature universe and the top-rank threshold.  
**Interpretation:** Higher values indicate that positive signature genes are more concentrated near the top of the sample ranking than negative genes.  
**Limit:** AUCell was developed for ranking-based activity assessment in single-cell workflows. TRACE presents it as a sensitivity, not the default bulk-RNA score.

### GSVA (`gsva`)

**Status:** Not available  
**Role:** Current boundary  
**Engine:** Not implemented  
**Formula:** `Not available in TRACE Explorer.`  
**Parameters:** None.  
**Direction:** Not applicable.  
**Gene universe:** Not applicable.  
**Dependence on the run:** GSVA estimates expression distributions across a sample cohort, so its score is cohort-relative.  
**Interpretation:** TRACE does not currently expose GSVA as a signature score.  
**Limit:** If introduced later, it will require a frozen reference population and will not be presented as a transportable per-sample default.

## Rules shared by all methods

### Expression input

The result records the dataset, release, expression-layer identifier and analysis scale. Rank-based scores require a finite, frozen broad expression layer with at least 1,000 unique usable genes and no more than 75 million gene-by-sample entries; small targeted panels should use arithmetic methods. Rank-based methods are insensitive to strictly monotone transformations only when the feature universe and ties are unchanged.

### Mapping and coverage

Signature scoring requires 100% mapping of all requested components. TRACE reports submitted and resolved symbols, aliases, missing genes and duplicate resolutions. Consistent duplicates contribute once; a conflicting duplicate, an unmapped gene or fewer than two distinct resolved genes blocks a multi-gene score. Duplicate symbols inside a source matrix use the first row by recorded row number, and that policy is exported.

### Missing expression

Arithmetic methods use complete cases for all resolved signature genes. Rank methods require every value in the frozen expression layer and canonical molecular population to be finite; they do not silently drop a patient or feature when scoring. Constant signature genes remain in the calculation and are reported. Participant counts before and after scoring remain visible.

### Direction and weights

Mean treats all genes as positive. Weighted and z-score methods retain finite, non-zero weight magnitude. singscore, ssGSEA and AUCell accept only plain or +1 genes as up and −1 genes as down; zero and other magnitudes are invalid.

### REST representation

The interface uses GENE, GENE:1 and GENE:-1. REST clients may instead set signature_genes[].direction to up or down and should omit weight in that form. Explicit direction is authoritative if both fields are sent; any supplied rank-method weight must still be +1 or −1.

### Filters and timing

Arithmetic methods follow endpoint and clinical eligibility; z-score is recalculated in that complete-case population. Rank methods are scored once on the canonical molecular population before endpoint and clinical filters, then the stored scores are subset for the requested analysis. Thus filtering unrelated patients does not change a retained patient's rank score.

### Across studies

TRACE scores and fits associations inside each study. Raw patient-level rank scores from different studies are never pooled as if they shared one numerical scale. A workflow reports multi-study synthesis only for effect estimates that satisfy its declared common-scale and hierarchy rules; rank-signature effects remain study-level in the current pan-cancer workflow.

### Downstream inference

Scoring and inference are separate decisions. A score may enter a continuous model, a declared grouped comparison or GSEA grouping. Survival models report the effect per one standard deviation among the patients retained for that analysis, and grouped views recalculate their declared cutpoint there. Filtering therefore does not change a retained patient's frozen rank score, but it can change the model's unit or group assignment. A cutpoint does not validate a signature, and multiple tried definitions must be interpreted as a family.

## Limitations

- A high score is not direct evidence that a pathway is causally active.
- Tumour purity and immune or stromal content can influence many signatures; adjustment is not automatic and should be justified for the biological question.
- Batch, assay and feature-universe differences remain relevant even for within-sample rank methods.
- A signature evaluated in the same data used to derive it is not an independent validation.
- Random or matched gene sets can be useful negative controls, but they do not replace a prespecified hypothesis or external validation.

## References

- [Foroutan M et al. Single sample scoring of molecular phenotypes. BMC Bioinformatics. 2018;19:404.](https://doi.org/10.1186/s12859-018-2435-4)
- [Barbie DA et al. Systematic RNA interference reveals that oncogenic KRAS-driven cancers require TBK1. Nature. 2009;462:108–112.](https://doi.org/10.1038/nature08460)
- [Hänzelmann S, Castelo R, Guinney J. GSVA: gene set variation analysis for microarray and RNA-seq data. BMC Bioinformatics. 2013;14:7.](https://doi.org/10.1186/1471-2105-14-7)
- [Aibar S et al. SCENIC: single-cell regulatory network inference and clustering. Nature Methods. 2017;14:1083–1086.](https://doi.org/10.1038/nmeth.4463)
- [Bioconductor. GSVA package reference and vignette, version 2.0.7.](https://bioconductor.org/packages/3.20/bioc/html/GSVA.html)
- [Bioconductor. singscore package reference, version 1.26.0.](https://bioconductor.org/packages/3.20/bioc/html/singscore.html)
- [Bioconductor. AUCell package reference, version 1.28.0.](https://bioconductor.org/packages/3.20/bioc/html/AUCell.html)
