/** Stable references for methodological claims in the learning system. */

function citation(id, authors, year, title, venue, extra = {}) {
  return Object.freeze({ id, authors, year, title, venue, ...extra });
}

export const TUTORIAL_CITATIONS = Object.freeze({
  "cox-1972": citation(
    "cox-1972",
    "Cox DR",
    1972,
    "Regression Models and Life-Tables",
    "Journal of the Royal Statistical Society: Series B",
    { doi: "10.1111/j.2517-6161.1972.tb00899.x" },
  ),
  "schoenfeld-1982": citation(
    "schoenfeld-1982",
    "Schoenfeld D",
    1982,
    "Partial Residuals for the Proportional Hazards Regression Model",
    "Biometrika",
    { doi: "10.1093/biomet/69.1.239" },
  ),
  "benjamini-hochberg-1995": citation(
    "benjamini-hochberg-1995",
    "Benjamini Y; Hochberg Y",
    1995,
    "Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing",
    "Journal of the Royal Statistical Society: Series B",
    { doi: "10.1111/j.2517-6161.1995.tb02031.x" },
  ),
  "welch-1947": citation(
    "welch-1947",
    "Welch BL",
    1947,
    "The Generalization of Student's Problem when Several Different Population Variances are Involved",
    "Biometrika",
    { doi: "10.1093/biomet/34.1-2.28" },
  ),
  "mann-whitney-1947": citation(
    "mann-whitney-1947",
    "Mann HB; Whitney DR",
    1947,
    "On a Test of Whether one of Two Random Variables is Stochastically Larger than the Other",
    "The Annals of Mathematical Statistics",
    { doi: "10.1214/aoms/1177730491" },
  ),
  "subramanian-2005": citation(
    "subramanian-2005",
    "Subramanian A et al.",
    2005,
    "Gene set enrichment analysis: A knowledge-based approach for interpreting genome-wide expression profiles",
    "Proceedings of the National Academy of Sciences",
    { doi: "10.1073/pnas.0506580102" },
  ),
  "wu-smyth-2012": citation(
    "wu-smyth-2012",
    "Wu D; Smyth GK",
    2012,
    "Camera: a competitive gene set test accounting for inter-gene correlation",
    "Nucleic Acids Research",
    { doi: "10.1093/nar/gks461" },
  ),
  "go-consortium-2023": citation(
    "go-consortium-2023",
    "The Gene Ontology Consortium",
    2023,
    "The Gene Ontology knowledgebase in 2023",
    "Genetics",
    { doi: "10.1093/genetics/iyad031" },
  ),
  "simonsohn-2020": citation(
    "simonsohn-2020",
    "Simonsohn U; Simmons JP; Nelson LD",
    2020,
    "Specification curve analysis",
    "Nature Human Behaviour",
    { doi: "10.1038/s41562-020-0912-z" },
  ),
  "higgins-thompson-2002": citation(
    "higgins-thompson-2002",
    "Higgins JPT; Thompson SG",
    2002,
    "Quantifying heterogeneity in a meta-analysis",
    "Statistics in Medicine",
    { doi: "10.1002/sim.1186" },
  ),
  "hartung-knapp-2001": citation(
    "hartung-knapp-2001",
    "Hartung J; Knapp G",
    2001,
    "A refined method for the meta-analysis of controlled clinical trials with binary outcome",
    "Statistics in Medicine",
    { doi: "10.1002/1097-0258(20010228)20:4<387::AID-SIM739>3.0.CO;2-7" },
  ),
  "int-hout-2014": citation(
    "int-hout-2014",
    "IntHout J; Ioannidis JPA; Borm GF",
    2014,
    "The Hartung-Knapp-Sidik-Jonkman method for random effects meta-analysis is straightforward and considerably outperforms the standard DerSimonian-Laird method",
    "BMC Medical Research Methodology",
    { doi: "10.1186/1471-2288-14-25" },
  ),
  "riley-2011": citation(
    "riley-2011",
    "Riley RD; Higgins JPT; Deeks JJ",
    2011,
    "Interpretation of random effects meta-analyses",
    "BMJ",
    { doi: "10.1136/bmj.d549" },
  ),
  "wilkinson-2016": citation(
    "wilkinson-2016",
    "Wilkinson MD et al.",
    2016,
    "The FAIR Guiding Principles for scientific data management and stewardship",
    "Scientific Data",
    { doi: "10.1038/sdata.2016.18" },
  ),
});

export const TUTORIAL_CITATION_IDS = Object.freeze(Object.keys(TUTORIAL_CITATIONS));

export function getTutorialCitation(citationId) {
  return TUTORIAL_CITATIONS[citationId] || null;
}

export function resolveTutorialCitations(citationIds) {
  return Object.freeze(
    (citationIds || []).map((citationId) => getTutorialCitation(citationId)).filter(Boolean),
  );
}
