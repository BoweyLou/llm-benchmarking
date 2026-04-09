export const DASHBOARD_DEFAULT_TAB = "browser";
export const DASHBOARD_DEFAULT_LENS = "general_reasoning";
export const DASHBOARD_DEFAULT_CATALOG_MODE = "exact";
export const DASHBOARD_DEFAULT_RECOMMENDATION_FILTER = "recommended";
export const DASHBOARD_EMPTY_LENS_QUERY_VALUE = "none";

export const RECOMMENDATION_RAIL_WIDTH_PX = 52;
export const RECOMMENDATION_RAIL_DESKTOP_FONT_SIZE_REM = 0.64;
export const RECOMMENDATION_RAIL_DESKTOP_LETTER_SPACING_EM = 0.12;
export const RECOMMENDATION_RAIL_MOBILE_FONT_SIZE_REM = 0.7;
export const RECOMMENDATION_RAIL_MOBILE_LETTER_SPACING_EM = 0.12;

const RECOMMENDATION_RAIL_LABELS = Object.freeze({
  discouraged: "Discouraged",
  mixed: "Mixed",
  not_recommended: "Not rec.",
  recommended: "Recommended",
  unrated: "Unrated",
});

export function getDashboardBaselineRecommendationFilter(lensId) {
  return lensId ? DASHBOARD_DEFAULT_RECOMMENDATION_FILTER : "all";
}

export function getDashboardRailLabel(status) {
  return RECOMMENDATION_RAIL_LABELS[status] || RECOMMENDATION_RAIL_LABELS.unrated;
}
