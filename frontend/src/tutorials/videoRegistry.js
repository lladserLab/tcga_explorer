// Versioned assets keep browser caches aligned with the reviewed film cut.
export const GUIDE_VIDEOS = Object.freeze({
  "quick-analysis": "01-survival/draft_v12",
  "quick-compare": "03-compare/draft_v3",
  "quick-expression": "04-expression/draft_v3",
  "quick-gsea": "05-gsea/draft_v3",
  "quick-multiverse": "02-robustness/draft_v4",
  "quick-session": "07-runhistory/draft_v3",
  "quick-pancancer": "06-pancancer/draft_v3",
});

export function guideVideoUrl(guideId) {
  const film = GUIDE_VIDEOS[guideId];
  if (!film) return null;
  return `${import.meta.env.BASE_URL}tutorial-videos/${film}_en.mp4`;
}
