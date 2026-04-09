import { useDeferredValue, useEffect, useMemo, useRef, useState, useTransition } from "react";

import {
  DASHBOARD_BRAND_EYEBROW,
  DASHBOARD_BRAND_TITLE,
  DASHBOARD_DEFAULT_CATALOG_MODE,
  DASHBOARD_DEFAULT_LENS,
  DASHBOARD_DEFAULT_RECOMMENDATION_FILTER,
  DASHBOARD_DEFAULT_TAB,
  DASHBOARD_EMPTY_LENS_QUERY_VALUE,
  RECOMMENDATION_RAIL_DESKTOP_FONT_SIZE_REM,
  RECOMMENDATION_RAIL_DESKTOP_LETTER_SPACING_EM,
  RECOMMENDATION_RAIL_MOBILE_FONT_SIZE_REM,
  RECOMMENDATION_RAIL_MOBILE_LETTER_SPACING_EM,
  RECOMMENDATION_RAIL_WIDTH_PX,
  getDashboardBaselineRecommendationFilter,
  getDashboardRailLabel,
} from "./dashboardDefaults";
import { exportDashboardHtmlSnapshot } from "./exportStaticHtml";
import { useDashboardData } from "./useDashboardData";

const PROVIDER_COLORS = {
  Anthropic: { tone: "orange" },
  OpenAI: { tone: "green" },
  Google: { tone: "blue" },
  "Zhipu AI": { tone: "violet" },
  "Inception Labs": { tone: "pink" },
  default: { tone: "slate" },
};

const TAB_ITEMS = [
  { id: "finder", label: "Use Case Finder", icon: "🔍" },
  { id: "browser", label: "Model Browser", icon: "📊" },
  { id: "compare", label: "Compare", icon: "⚖️" },
  { id: "admin", label: "Admin", icon: "🛠️" },
  { id: "methodology", label: "Methodology", icon: "🧭" },
  { id: "history", label: "History", icon: "🕐" },
];
const STARTER_LENS_IDS = ["general_reasoning", "coding", "document_operations", "cost_efficiency"];

const DEFAULT_BROWSER_LIMIT = 24;
const INTERNAL_VIEW_BENCHMARK_ID = "internal_view";
const VALID_MODEL_TYPES = new Set(["All", "proprietary", "open_weights"]);
const DEFAULT_APPROVAL_FAMILY_FILTER = "All";
const DEFAULT_HYPERSCALER_FILTER = "All";
const DEFAULT_INFERENCE_PROVIDER_FILTER = "All";
const DEFAULT_INFERENCE_LOCATION_FILTER = "All";
const DEFAULT_ORIGIN_FILTER = "All";
const DEFAULT_REVIEW_SIGNAL_FILTER = "all";
const DEFAULT_RECOMMENDATION_FILTER = "all";
const DEFAULT_FAMILY_APPROVAL_SCOPE = "family";
const BROWSER_SORT_OPTIONS = [
  { id: "smart", label: "Smart order" },
  { id: "popularity", label: "OpenRouter popularity" },
  { id: "price", label: "Lowest price" },
  { id: "coverage", label: "Coverage" },
  { id: "release", label: "Newest release" },
  { id: "name", label: "Name A-Z" },
];
const REGION_COUNTRY_OVERRIDES = {
  global: "Global",
  "af-south-1": "South Africa",
  "ap-east-1": "Hong Kong",
  "ap-east-2": "Taiwan",
  "ap-northeast-1": "Japan",
  "ap-northeast-2": "South Korea",
  "ap-northeast-3": "Japan",
  "ap-south-1": "India",
  "ap-south-2": "India",
  "ap-southeast-1": "Singapore",
  "ap-southeast-2": "Australia",
  "ap-southeast-3": "Indonesia",
  "ap-southeast-4": "Australia",
  "ap-southeast-5": "Malaysia",
  "ap-southeast-6": "New Zealand",
  "asia-east1": "Taiwan",
  "asia-east2": "Hong Kong",
  "asia-northeast1": "Japan",
  "asia-northeast2": "Japan",
  "asia-northeast3": "South Korea",
  "asia-south1": "India",
  "asia-south2": "India",
  "asia-southeast1": "Singapore",
  "asia-southeast2": "Indonesia",
  australiaeast: "Australia",
  australiasoutheast: "Australia",
  "australia-southeast1": "Australia",
  "australia-southeast2": "Australia",
  brazilsouth: "Brazil",
  brazilsoutheast: "Brazil",
  "ca-central-1": "Canada",
  "ca-west-1": "Canada",
  canadacentral: "Canada",
  canadaeast: "Canada",
  centralindia: "India",
  centralus: "United States",
  eastasia: "Hong Kong",
  eastus: "United States",
  eastus2: "United States",
  "eu-central-1": "Germany",
  "eu-central-2": "Switzerland",
  "eu-north-1": "Sweden",
  "eu-south-1": "Italy",
  "eu-south-2": "Spain",
  "eu-west-1": "Ireland",
  "eu-west-2": "United Kingdom",
  "eu-west-3": "France",
  "europe-central2": "Poland",
  "europe-north1": "Finland",
  "europe-southwest1": "Spain",
  "europe-west1": "Belgium",
  "europe-west2": "United Kingdom",
  "europe-west3": "Germany",
  "europe-west4": "Netherlands",
  "europe-west6": "Switzerland",
  "europe-west8": "Italy",
  "europe-west9": "France",
  "europe-west10": "Germany",
  "europe-west12": "Italy",
  francecentral: "France",
  germanynorth: "Germany",
  germanywestcentral: "Germany",
  "il-central-1": "Israel",
  israelcentral: "Israel",
  japaneast: "Japan",
  japanwest: "Japan",
  koreacentral: "South Korea",
  koreasouth: "South Korea",
  "me-central-1": "United Arab Emirates",
  "me-central1": "Qatar",
  "me-south-1": "Bahrain",
  "me-west1": "Israel",
  mexicocentral: "Mexico",
  "mx-central-1": "Mexico",
  "northamerica-northeast1": "Canada",
  "northamerica-northeast2": "Canada",
  northcentralus: "United States",
  northeurope: "Ireland",
  norwayeast: "Norway",
  norwaywest: "Norway",
  polandcentral: "Poland",
  qatarcentral: "Qatar",
  "sa-east-1": "Brazil",
  southafricanorth: "South Africa",
  southafricawest: "South Africa",
  southcentralus: "United States",
  southeastasia: "Singapore",
  southindia: "India",
  "southamerica-east1": "Brazil",
  "southamerica-west1": "Chile",
  swedencentral: "Sweden",
  switzerlandnorth: "Switzerland",
  switzerlandwest: "Switzerland",
  uaecentral: "United Arab Emirates",
  uaeeast: "United Arab Emirates",
  uaenorth: "United Arab Emirates",
  uksouth: "United Kingdom",
  ukwest: "United Kingdom",
  "us-central1": "United States",
  "us-east-1": "United States",
  "us-east-2": "United States",
  "us-east1": "United States",
  "us-east4": "United States",
  "us-east5": "United States",
  "us-south1": "United States",
  "us-west-1": "United States",
  "us-west-2": "United States",
  "us-west1": "United States",
  "us-west2": "United States",
  "us-west3": "United States",
  "us-west4": "United States",
  westcentralus: "United States",
  westeurope: "Netherlands",
  westindia: "India",
  westus: "United States",
  westus2: "United States",
  westus3: "United States",
};
const REGION_COUNTRY_KEYWORDS = [
  ["australia", "Australia"],
  ["sweden", "Sweden"],
  ["france", "France"],
  ["germany", "Germany"],
  ["switzerland", "Switzerland"],
  ["poland", "Poland"],
  ["norway", "Norway"],
  ["japan", "Japan"],
  ["korea", "South Korea"],
  ["india", "India"],
  ["canada", "Canada"],
  ["mexico", "Mexico"],
  ["brazil", "Brazil"],
  ["israel", "Israel"],
  ["uae", "United Arab Emirates"],
  ["qatar", "Qatar"],
  ["singapore", "Singapore"],
];
const ADMIN_FOCUS_OPTIONS = [
  { id: "all", label: "All sections" },
  { id: "providers", label: "Providers" },
  { id: "approvals", label: "Approvals" },
  { id: "internal_weights", label: "Internal weights" },
  { id: "internal_scores", label: "Internal scores" },
];
const MODEL_APPROVAL_FILTER_OPTIONS = [
  { id: "all", label: "All models" },
  { id: "pending", label: "Not approved" },
  { id: "approved", label: "Approved" },
  { id: "changed", label: "Changed" },
];
const MODEL_REVIEW_FILTER_OPTIONS = [
  { id: "all", label: "All review states" },
  { id: "unrated", label: "Unrated" },
  { id: "needs_review", label: "Needs review" },
  { id: "suggested", label: "Suggested approve" },
  { id: "new_only", label: "New family" },
  { id: "reviewed_no", label: "Reviewed not approved" },
];
const RECOMMENDATION_STATUS_OPTIONS = [
  { id: "unrated", label: "Unrated" },
  { id: "recommended", label: "Recommended" },
  { id: "not_recommended", label: "Not recommended" },
  { id: "discouraged", label: "Discouraged" },
];
const AUTO_LEGACY_RELEASE_DAYS = 365;
const AUTO_LEGACY_OPENROUTER_DAYS = 365;
const RECOMMENDATION_FILTER_OPTIONS = [
  { id: DEFAULT_RECOMMENDATION_FILTER, label: "All recommendation states" },
  ...RECOMMENDATION_STATUS_OPTIONS,
];
const FAMILY_APPROVAL_SCOPE_OPTIONS = [
  { id: "family", label: "Approve entire family" },
  { id: "delta", label: "Approve family delta only" },
];
const INTERNAL_SCORE_FILTER_OPTIONS = [
  { id: "all", label: "All models" },
  { id: "missing", label: "Missing score" },
  { id: "scored", label: "Has score" },
  { id: "changed", label: "Changed" },
];

function App() {
  const initialUrlStateRef = useRef(readUrlState());
  const didHydrateLensRef = useRef(false);
  const data = useDashboardData();
  const [activeTab, setActiveTab] = useState(initialUrlStateRef.current.tab);
  const [catalogMode, setCatalogMode] = useState(initialUrlStateRef.current.mode);
  const [compareIds, setCompareIds] = useState(initialUrlStateRef.current.compare);
  const [query, setQuery] = useState(initialUrlStateRef.current.query);
  const [providerFilter, setProviderFilter] = useState(initialUrlStateRef.current.provider);
  const [inferenceLocationFilter, setInferenceLocationFilter] = useState(initialUrlStateRef.current.inferenceLocation);
  const [typeFilter, setTypeFilter] = useState(initialUrlStateRef.current.type);
  const [approvedOnly, setApprovedOnly] = useState(initialUrlStateRef.current.approvedOnly);
  const [recommendationFilter, setRecommendationFilter] = useState(initialUrlStateRef.current.recommendation);
  const [browserSort, setBrowserSort] = useState(initialUrlStateRef.current.sort);
  const [expandedId, setExpandedId] = useState(initialUrlStateRef.current.expandedModelId);
  const [compareQuery, setCompareQuery] = useState("");
  const [expandedHistoryId, setExpandedHistoryId] = useState(initialUrlStateRef.current.historyLogId);
  const [requestedLensId, setRequestedLensId] = useState(initialUrlStateRef.current.lens);
  const [lensPickerOpen, setLensPickerOpen] = useState(!initialUrlStateRef.current.lens);
  const [browserOnlyCompared, setBrowserOnlyCompared] = useState(initialUrlStateRef.current.onlyCompared);
  const [visibleBrowserCount, setVisibleBrowserCount] = useState(DEFAULT_BROWSER_LIMIT);
  const [showAllRankings, setShowAllRankings] = useState(false);
  const [isExportingSnapshot, setIsExportingSnapshot] = useState(false);
  const [isPending, startTransition] = useTransition();

  const deferredQuery = useDeferredValue(query);
  const deferredCompareQuery = useDeferredValue(compareQuery);

  const benchmarksById = useMemo(
    () => Object.fromEntries(data.benchmarks.map((benchmark) => [benchmark.id, benchmark])),
    [data.benchmarks],
  );
  const exactModels = useMemo(() => buildCanonicalModels(data.models, benchmarksById), [benchmarksById, data.models]);
  const exactModelsById = useMemo(() => Object.fromEntries(exactModels.map((model) => [model.id, model])), [exactModels]);
  const familyModels = useMemo(
    () => buildFamilyModelsFromCanonical(exactModels, benchmarksById),
    [benchmarksById, exactModels],
  );
  const familyLookup = useMemo(() => buildFamilyLookup(familyModels), [familyModels]);
  const catalogModels = catalogMode === "family" ? familyModels : exactModels;
  const visibleModelCount = catalogModels.length;
  const selectedUseCase =
    data.useCases.find((useCase) => useCase.id === data.selectedUseCaseId) || null;
  const selectedRankingEntries = data.rankings?.rankings || [];
  const filteredRankingEntries = useMemo(
    () => selectedRankingEntries.filter((entry) => !approvedOnly || isModelApprovedForUseCase(entry.model, selectedUseCase?.id)),
    [approvedOnly, selectedRankingEntries, selectedUseCase],
  );
  const exactRankingById = useMemo(
    () => Object.fromEntries(filteredRankingEntries.map((entry) => [entry.model.id, entry])),
    [filteredRankingEntries],
  );
  const familyRankingById = useMemo(
    () => mapRankingEntriesToFamilies(filteredRankingEntries, familyModels),
    [familyModels, filteredRankingEntries],
  );
  const rankingByCatalogId = catalogMode === "family" ? familyRankingById : exactRankingById;

  const filteredModels = useMemo(() => {
    const search = deferredQuery.toLowerCase();
    return catalogModels.filter((model) => {
      const matchQuery = buildModelSearchText(model).includes(search);
      const matchProvider = providerFilter === "All" || model.provider === providerFilter;
      const matchInferenceLocation =
        inferenceLocationFilter === DEFAULT_INFERENCE_LOCATION_FILTER ||
        (model.inference_countries || []).includes(inferenceLocationFilter);
      const matchType = typeFilter === "All" || model.type === typeFilter;
      const matchApproval =
        !approvedOnly ||
        isModelApprovedForUseCase(model, selectedUseCase?.id, {
          locationLabel:
            inferenceLocationFilter !== DEFAULT_INFERENCE_LOCATION_FILTER ? inferenceLocationFilter : "",
        });
      const matchRecommendation =
        !selectedUseCase ||
        recommendationFilter === DEFAULT_RECOMMENDATION_FILTER ||
        matchesRecommendationFilter(model, selectedUseCase?.id, recommendationFilter);
      const matchCompared = !browserOnlyCompared || compareIds.includes(model.id);
      return (
        matchQuery &&
        matchProvider &&
        matchInferenceLocation &&
        matchType &&
        matchApproval &&
        matchRecommendation &&
        matchCompared
      );
    });
  }, [
    approvedOnly,
    browserOnlyCompared,
    catalogModels,
    compareIds,
    deferredQuery,
    inferenceLocationFilter,
    providerFilter,
    recommendationFilter,
    selectedUseCase,
    typeFilter,
  ]);

  const sortedModels = useMemo(
    () =>
      sortCatalogModels(filteredModels, {
        rankingByCatalogId,
        selectedUseCase,
        sortKey: browserSort,
      }),
    [browserSort, filteredModels, rankingByCatalogId, selectedUseCase],
  );

  const visibleBrowserModels = useMemo(
    () => sortedModels.slice(0, visibleBrowserCount),
    [sortedModels, visibleBrowserCount],
  );
  const hasMoreBrowserResults = visibleBrowserModels.length < sortedModels.length;

  const compareSuggestions = useMemo(() => {
    const search = deferredCompareQuery.toLowerCase();
    return catalogModels
      .filter((model) => !compareIds.includes(model.id))
      .filter((model) => buildModelSearchText(model).includes(search))
      .slice(0, 8);
  }, [catalogModels, compareIds, deferredCompareQuery]);

  const providers = useMemo(
    () => ["All", ...new Set(catalogModels.map((model) => model.provider).filter(Boolean))].sort(),
    [catalogModels],
  );
  const inferenceLocations = useMemo(
    () => [
      DEFAULT_INFERENCE_LOCATION_FILTER,
      ...sortInferenceCountries(catalogModels.flatMap((model) => model.inference_countries || [])),
    ],
    [catalogModels],
  );
  const comparisonSeedIds = useMemo(
    () => getTopComparisonIds(filteredRankingEntries, catalogMode, familyLookup),
    [catalogMode, familyLookup, filteredRankingEntries],
  );

  useEffect(() => {
    if (!providers.includes(providerFilter)) {
      setProviderFilter("All");
    }
  }, [providerFilter, providers]);

  useEffect(() => {
    if (!inferenceLocations.includes(inferenceLocationFilter)) {
      setInferenceLocationFilter(DEFAULT_INFERENCE_LOCATION_FILTER);
    }
  }, [inferenceLocationFilter, inferenceLocations]);

  useEffect(() => {
    if (!VALID_MODEL_TYPES.has(typeFilter)) {
      setTypeFilter("All");
    }
  }, [typeFilter]);

  useEffect(() => {
    if (data.loading) {
      return;
    }
    setCompareIds((current) => current.filter((id) => catalogModels.some((model) => model.id === id)));
  }, [catalogModels, data.loading]);

  useEffect(() => {
    setVisibleBrowserCount(DEFAULT_BROWSER_LIMIT);
  }, [
    approvedOnly,
    browserOnlyCompared,
    browserSort,
    catalogMode,
    inferenceLocationFilter,
    providerFilter,
    query,
    requestedLensId,
    typeFilter,
  ]);

  useEffect(() => {
    if (data.loading) {
      return;
    }
    if (expandedId && !catalogModels.some((model) => model.id === expandedId)) {
      setExpandedId(null);
    }
  }, [catalogModels, data.loading, expandedId]);

  useEffect(() => {
    if (!data.useCases.length || didHydrateLensRef.current) {
      return;
    }

    didHydrateLensRef.current = true;
    const nextLens = sanitizeRequestedLens(requestedLensId, data.useCases);
    if (nextLens !== requestedLensId) {
      setRequestedLensId(nextLens);
    }
    setLensPickerOpen(!nextLens);
    if (nextLens) {
      data.loadRankings(nextLens);
    }
  }, [data.useCases.length, requestedLensId]);

  useEffect(() => {
    if (!didHydrateLensRef.current || !data.useCases.length) {
      return;
    }

    const nextLens = sanitizeRequestedLens(requestedLensId, data.useCases);
    if (nextLens !== requestedLensId) {
      setRequestedLensId(nextLens);
      return;
    }
    if (nextLens === data.selectedUseCaseId) {
      return;
    }

    data.loadRankings(nextLens);
  }, [data.selectedUseCaseId, data.useCases.length, requestedLensId]);

  useEffect(() => {
    function handlePopState() {
      const next = readUrlState();
      startTransition(() => {
        setActiveTab(next.tab);
        setCatalogMode(next.mode);
        setCompareIds(next.compare);
        setQuery(next.query);
        setProviderFilter(next.provider);
        setInferenceLocationFilter(next.inferenceLocation);
        setTypeFilter(next.type);
        setApprovedOnly(next.approvedOnly);
        setRecommendationFilter(next.recommendation);
        setBrowserSort(next.sort);
        setExpandedId(next.expandedModelId);
        setExpandedHistoryId(next.historyLogId);
        setRequestedLensId(next.lens);
        setLensPickerOpen(!next.lens);
        setBrowserOnlyCompared(next.onlyCompared);
        setVisibleBrowserCount(DEFAULT_BROWSER_LIMIT);
        setShowAllRankings(false);
      });
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [startTransition]);

  useEffect(() => {
    if (!didHydrateLensRef.current) {
      return;
    }

    writeUrlState({
      compare: compareIds,
      expandedModelId: activeTab === "browser" ? expandedId : "",
      historyLogId: activeTab === "history" ? expandedHistoryId : "",
      lens: requestedLensId,
      mode: catalogMode,
      approvedOnly,
      inferenceLocation: inferenceLocationFilter,
      onlyCompared: browserOnlyCompared,
      provider: providerFilter,
      query,
      recommendation: recommendationFilter,
      sort: browserSort,
      tab: activeTab,
      type: typeFilter,
    });
  }, [
    activeTab,
    approvedOnly,
    browserOnlyCompared,
    browserSort,
    catalogMode,
    compareIds,
    expandedHistoryId,
    expandedId,
    inferenceLocationFilter,
    providerFilter,
    query,
    recommendationFilter,
    requestedLensId,
    typeFilter,
  ]);

  const currentUrlState = {
    compare: compareIds,
    expandedModelId: activeTab === "browser" ? expandedId : "",
    historyLogId: activeTab === "history" ? expandedHistoryId : "",
    lens: requestedLensId,
    mode: catalogMode,
    approvedOnly,
    inferenceLocation: inferenceLocationFilter,
    onlyCompared: browserOnlyCompared,
    provider: providerFilter,
    query,
    recommendation: recommendationFilter,
    sort: browserSort,
    tab: activeTab,
    type: typeFilter,
  };

  function buildHref(overrides = {}) {
    return buildUrlStateHref({
      ...currentUrlState,
      ...overrides,
    });
  }

  function handleSelectUseCase(useCaseId) {
    const nextUseCaseId = useCaseId === requestedLensId ? "" : useCaseId;
    startTransition(() => {
      setRequestedLensId(nextUseCaseId);
      setRecommendationFilter(getDashboardBaselineRecommendationFilter(nextUseCaseId));
      setLensPickerOpen(!nextUseCaseId);
      setShowAllRankings(false);
    });
  }

  function toggleCompare(modelId) {
    setCompareIds((current) =>
      current.includes(modelId) ? current.filter((id) => id !== modelId) : [...current, modelId],
    );
  }

  function handleCatalogModeChange(nextMode) {
    if (nextMode === catalogMode) {
      return;
    }
    startTransition(() => {
      setCompareIds((current) => remapIdsForCatalogMode(current, catalogMode, nextMode, familyLookup));
      setExpandedId((current) => remapIdForCatalogMode(current, catalogMode, nextMode, familyLookup));
      setCatalogMode(nextMode);
      setCompareQuery("");
    });
  }

  function toggleHistoryEntry(logId) {
    setExpandedHistoryId((current) => {
      const nextLogId = current === logId ? null : logId;
      if (nextLogId && !data.sourceRunsByLogId[nextLogId]?.length) {
        data.loadSourceRuns(nextLogId);
      }
      return nextLogId;
    });
  }

  function handleCompareTopModels() {
    const nextCompareIds = comparisonSeedIds.slice(0, 3);
    if (nextCompareIds.length < 2) {
      return;
    }
    startTransition(() => {
      setCompareIds(nextCompareIds);
      setActiveTab("compare");
    });
  }

  function handleClearBrowserFilters() {
    startTransition(() => {
      setQuery("");
      setProviderFilter("All");
      setInferenceLocationFilter(DEFAULT_INFERENCE_LOCATION_FILTER);
      setTypeFilter("All");
      setApprovedOnly(false);
      setRecommendationFilter(getDashboardBaselineRecommendationFilter(requestedLensId));
      setBrowserOnlyCompared(false);
      setBrowserSort("smart");
    });
  }

  async function handleExportHtml() {
    if (isExportingSnapshot) {
      return;
    }

    try {
      const exportContext = await prepareExportDataForSnapshot({ activeTab, data });
      setIsExportingSnapshot(true);
      await waitForExportRender();
      exportDashboardHtmlSnapshot({
        activeTab,
        benchmarks: data.benchmarks,
        browserOnlyCompared,
        browserSort,
        catalogMode,
        compareIds,
        exactModels,
        familyModels,
        history: data.history,
        inferenceLocationFilter,
        marketSnapshots: data.marketSnapshots,
        providerFilter,
        query,
        rankingEntries: selectedRankingEntries,
        recommendationFilter,
        selectedUseCaseId: data.selectedUseCaseId,
        selectedUseCaseLabel: selectedUseCase?.label || "",
        sourceRunsByLogId: exportContext.sourceRunsByLogId,
        typeFilter,
        useCases: data.useCases,
        approvedOnly,
      });
    } catch (error) {
      console.error(error);
      window.alert(error instanceof Error ? error.message : "Failed to export HTML snapshot.");
    } finally {
      setIsExportingSnapshot(false);
    }
  }

  function renderContent() {
    if (activeTab === "finder") {
      return (
        <UseCaseFinder
          benchmarksById={benchmarksById}
          buildHref={buildHref}
          catalogMode={catalogMode}
          compareIds={compareIds}
          isPending={isPending}
          lensPickerOpen={lensPickerOpen}
          onBrowseCatalog={() => setActiveTab("browser")}
          onCompareTopModels={handleCompareTopModels}
          approvedOnly={approvedOnly}
          onOpenMethodology={() => setActiveTab("methodology")}
          onApprovedOnlyChange={setApprovedOnly}
          rankings={data.rankings}
          rankingEntries={filteredRankingEntries}
          rankingsError={data.rankingsError}
          rankingsLoading={data.rankingsLoading}
          selectedUseCase={selectedUseCase}
          useCases={data.useCases}
          onLensPickerOpenChange={setLensPickerOpen}
          onSelectUseCase={handleSelectUseCase}
          onToggleCompare={toggleCompare}
          familyLookup={familyLookup}
          exportMode={isExportingSnapshot}
          showAllRankings={showAllRankings}
          onShowAllRankingsChange={setShowAllRankings}
        />
      );
    }

    if (activeTab === "browser") {
      return (
        <ModelBrowser
          compareIds={compareIds}
          browserOnlyCompared={browserOnlyCompared}
          browserSort={browserSort}
          catalogMode={catalogMode}
          exactModelsById={exactModelsById}
          expandedId={expandedId}
          benchmarksById={benchmarksById}
          filteredModelsCount={sortedModels.length}
          hasMoreResults={!isExportingSnapshot && hasMoreBrowserResults}
          visibleModels={isExportingSnapshot ? sortedModels : visibleBrowserModels}
          inferenceLocationFilter={inferenceLocationFilter}
          inferenceLocations={inferenceLocations}
          onAddToCompare={toggleCompare}
          onBrowserOnlyComparedChange={setBrowserOnlyCompared}
          onBrowserSortChange={setBrowserSort}
          onApprovedOnlyChange={setApprovedOnly}
          onCatalogModeChange={handleCatalogModeChange}
          onClearFilters={handleClearBrowserFilters}
          onExpandedIdChange={setExpandedId}
          onInferenceLocationFilterChange={setInferenceLocationFilter}
          onLoadMore={() => setVisibleBrowserCount((current) => current + DEFAULT_BROWSER_LIMIT)}
          onProviderFilterChange={setProviderFilter}
          onQueryChange={setQuery}
          onRecommendationFilterChange={setRecommendationFilter}
          onTypeFilterChange={setTypeFilter}
          providerFilter={providerFilter}
          providers={providers}
          query={query}
          rankingByCatalogId={rankingByCatalogId}
          approvedOnly={approvedOnly}
          recommendationFilter={recommendationFilter}
          selectedUseCase={selectedUseCase}
          typeFilter={typeFilter}
          exportMode={isExportingSnapshot}
        />
      );
    }

    if (activeTab === "compare") {
      return (
        <Compare
          benchmarks={data.benchmarks}
          benchmarksById={benchmarksById}
          catalogMode={catalogMode}
          compareIds={compareIds}
          compareSuggestions={compareSuggestions}
          compareQuery={compareQuery}
          models={catalogModels}
          onAddToCompare={toggleCompare}
          onCatalogModeChange={handleCatalogModeChange}
          onCompareQueryChange={setCompareQuery}
          rankingByCatalogId={rankingByCatalogId}
          selectedUseCase={selectedUseCase}
          exportMode={isExportingSnapshot}
        />
      );
    }

    if (activeTab === "methodology") {
      return (
        <Methodology
          benchmarks={data.benchmarks}
          benchmarksById={benchmarksById}
          catalogMode={catalogMode}
          selectedUseCaseId={data.selectedUseCaseId}
          useCases={data.useCases}
        />
      );
    }

    if (activeTab === "admin") {
      return (
        <AdminPanel
          onApplyInferenceRouteApprovalBulk={data.applyInferenceRouteApprovalBulk}
          onApplyFamilyApprovalBulk={data.applyFamilyApprovalBulk}
          onRefreshSelectedUseCaseRankings={data.refreshSelectedUseCaseRankings}
          benchmarks={data.benchmarks}
          models={data.models}
          onSaveInternalBenchmarkScore={data.saveManualBenchmarkScore}
          onSaveInternalWeight={data.saveUseCaseInternalWeight}
          onSaveModelDuplicateMerge={data.saveModelDuplicateMerge}
          providers={data.providers}
          onSaveModelApproval={data.saveModelApproval}
          onSaveModelIdentityCuration={data.saveModelIdentityCuration}
          onSaveProvider={data.saveProvider}
          selectedUseCaseId={data.selectedUseCaseId}
          useCases={data.useCases}
        />
      );
    }

    return (
      <History
        exportMode={isExportingSnapshot}
        expandedHistoryId={expandedHistoryId}
        history={data.history}
        loadRawSourceRecords={data.loadRawSourceRecords}
        marketSnapshots={data.marketSnapshots}
        marketSnapshotsError={data.marketSnapshotsError}
        marketSnapshotsLoading={data.marketSnapshotsLoading}
        onToggleEntry={toggleHistoryEntry}
        rawRecordsBySourceRunId={data.rawRecordsBySourceRunId}
        rawRecordsLoadingBySourceRunId={data.rawRecordsLoadingBySourceRunId}
        sourceRunsByLogId={data.sourceRunsByLogId}
        sourceRunsLoadingByLogId={data.sourceRunsLoadingByLogId}
        updateState={data.updateState}
      />
    );
  }

  return (
    <div className="shell">
      <style>{styles}</style>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div aria-live="polite" className="sr-only">
        {data.updateState.message || data.error || data.rankingsError || ""}
      </div>
      <Header
        benchmarkCount={data.benchmarks.length}
        compareCount={compareIds.length}
        exportDisabled={data.loading || data.updateState.status === "running" || isExportingSnapshot}
        isUpdating={data.updateState.status === "running"}
        lastUpdated={data.history[0]?.completed_at || data.history[0]?.started_at || "Not updated yet"}
        message={data.updateState.message}
        modelCount={visibleModelCount}
        onExportHtml={handleExportHtml}
        onUpdate={() => data.triggerUpdate()}
        selectedUseCase={selectedUseCase}
      />
      <TabNav
        activeTab={activeTab}
        buildHref={buildHref}
        compareCount={compareIds.length}
        onTabChange={(tab) => startTransition(() => setActiveTab(tab))}
      />
      <main className="page" id="main-content">
        {data.error ? <Banner tone="error" title="Data load failed" message={data.error} /> : null}
        {data.updateState.message ? (
          <Banner
            tone={data.updateState.status === "failed" ? "error" : "info"}
            title="Update status"
            message={data.updateState.message}
          />
        ) : null}
        {data.updateState.progressSteps?.length ? <UpdateProgressPanel updateState={data.updateState} /> : null}
        {data.loading ? <LoadingState /> : renderContent()}
      </main>
      {data.updateState.status === "running" ? (
        <div aria-live="polite" className="toast" role="status">
          {data.updateState.message || "Update running…"}
        </div>
      ) : null}
    </div>
  );
}

function Header({
  benchmarkCount,
  compareCount,
  exportDisabled,
  isUpdating,
  lastUpdated,
  message,
  modelCount,
  onExportHtml,
  onUpdate,
  selectedUseCase,
}) {
  return (
    <header className="topbar">
      <div className="topbar-main">
        <div className="eyebrow">{DASHBOARD_BRAND_EYEBROW}</div>
        <h1>{DASHBOARD_BRAND_TITLE}</h1>
        <p className="meta">
          Last updated {formatDate(lastUpdated)} · {modelCount} models · {benchmarkCount} benchmarks
        </p>
        <div className="hero-state-row">
          <span className="pill">{selectedUseCase ? `Lens: ${selectedUseCase.label}` : "Pick a lens to rank models"}</span>
          <span className="pill">{compareCount} in compare</span>
        </div>
      </div>
      <div className="topbar-actions">
        <div className="version">v1.0</div>
        <button className="btn btn-secondary" disabled={exportDisabled} onClick={onExportHtml} type="button">
          Export HTML
        </button>
        <button className="btn btn-primary" disabled={isUpdating} onClick={onUpdate} type="button">
          {isUpdating ? "Updating…" : "Update Now"}
        </button>
        {message ? <div className="message topbar-message">{message}</div> : null}
      </div>
    </header>
  );
}

function NavigationLink({ ariaCurrent, children, className, href, onNavigate }) {
  function handleClick(event) {
    if (!shouldHandleClientNavigation(event)) {
      return;
    }
    event.preventDefault();
    onNavigate?.();
  }

  return (
    <a aria-current={ariaCurrent} className={className} href={href} onClick={handleClick}>
      {children}
    </a>
  );
}

function TabNav({ activeTab, buildHref, compareCount, onTabChange }) {
  return (
    <nav aria-label="Primary sections" className="tabs">
      <div className="tabs-mobile">
        <label className="field">
          <span className="field-label">Section</span>
          <select className="input select" onChange={(event) => onTabChange(event.target.value)} value={activeTab}>
            {TAB_ITEMS.map((tab) => (
              <option key={tab.id} value={tab.id}>
                {tab.label}
                {tab.id === "compare" && compareCount ? ` (${compareCount})` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="tabs-desktop">
        {TAB_ITEMS.map((tab) => (
          <NavigationLink
            key={tab.id}
            aria-current={activeTab === tab.id ? "page" : undefined}
            className={activeTab === tab.id ? "tab tab-active" : "tab"}
            href={buildHref({ tab: tab.id })}
            onNavigate={() => onTabChange(tab.id)}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
            {tab.id === "compare" && compareCount ? <span className="tab-badge">{compareCount}</span> : null}
          </NavigationLink>
        ))}
      </div>
      <div aria-hidden="true" className="tabs-edge tabs-edge-left" />
      <div aria-hidden="true" className="tabs-edge tabs-edge-right" />
    </nav>
  );
}

function ViewModeToggle({ mode, onChange }) {
  return (
    <div aria-label="Catalog mode" className="toggle-group" role="group">
      <button
        aria-pressed={mode === "family"}
        className={mode === "family" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
        onClick={() => onChange("family")}
        type="button"
      >
        Families
      </button>
      <button
        aria-pressed={mode === "exact"}
        className={mode === "exact" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
        onClick={() => onChange("exact")}
        type="button"
      >
        Individual models
      </button>
    </div>
  );
}

function UseCaseFinder({
  approvedOnly,
  benchmarksById,
  buildHref,
  catalogMode,
  compareIds,
  exportMode,
  familyLookup,
  isPending,
  lensPickerOpen,
  onApprovedOnlyChange,
  onBrowseCatalog,
  onCompareTopModels,
  onLensPickerOpenChange,
  onOpenMethodology,
  onSelectUseCase,
  onToggleCompare,
  rankings,
  rankingEntries,
  rankingsError,
  rankingsLoading,
  selectedUseCase,
  showAllRankings,
  onShowAllRankingsChange,
  useCases,
}) {
  const groupedUseCases = groupUseCasesBySegment(useCases);
  const starterLenses = useMemo(
    () => STARTER_LENS_IDS.map((lensId) => useCases.find((useCase) => useCase.id === lensId)).filter(Boolean),
    [useCases],
  );
  const recommendedLens = useMemo(
    () =>
      useCases.find((useCase) => useCase.id === "general_reasoning") ||
      useCases.find((useCase) => useCase.status === "ready") ||
      useCases[0] ||
      null,
    [useCases],
  );
  const selectedRequired = selectedUseCase?.required_benchmarks || [];
  const selectedNotes = selectedUseCase?.benchmark_notes || {};
  const selectedMinCoverage = selectedUseCase?.min_coverage ?? 0.5;
  const allRankingCount = rankings?.rankings?.length || 0;
  const showExpandedExportContent = Boolean(exportMode);
  const showingAllRankings = showAllRankings || showExpandedExportContent;
  const visibleRankings = showingAllRankings ? rankingEntries : rankingEntries.slice(0, 8);
  const remainingRankings = Math.max(0, rankingEntries.length - visibleRankings.length);
  const compareSeedIds = getTopComparisonIds(rankingEntries, catalogMode, familyLookup);
  const quickRankings = rankingEntries.slice(0, 3);
  const noRankingsMessage = approvedOnly
    ? allRankingCount
      ? "No approved models currently match this ranking lens. Turn off the approved-only filter or approve more exact models."
      : "No approved models currently satisfy this use case. Turn off the approved-only filter or approve more exact models."
    : selectedRequired.length
      ? "No models currently satisfy the required evidence stack for this use case. Run an update or review the required benchmarks below."
      : "No models have data for this use case yet. Trigger an update to populate scores.";
  const topEntry = rankingEntries[0] || null;

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Which model for my use case?</h2>
          <p>Select a use case to see models ranked by evidence from our benchmark sources.</p>
        </div>
        {isPending || rankingsLoading ? <div className="pill">Loading rankings…</div> : null}
      </div>

      {!selectedUseCase ? (
        <>
          <article className="panel workspace-intro">
            <div className="workspace-intro-copy">
              Start with a lens. The selected lens becomes the context for rankings, compare, and browser sorting, and the
              current workspace is mirrored into the URL so this exact state can be reopened later.
            </div>
          </article>
          {recommendedLens ? (
            <article className="panel starter-panel">
              <div className="starter-panel-head">
                <div className="stack-tight">
                  <div className="panel-head">Fast start</div>
                  <div className="panel-copy">
                    If you are not sure where to begin, start with a broadly useful lens, then open the full picker for
                    more specific workflows.
                  </div>
                </div>
                <button className="btn btn-primary" onClick={() => onSelectUseCase(recommendedLens.id)} type="button">
                  Start with {recommendedLens.label}
                </button>
              </div>
              <div className="starter-lens-row">
                {starterLenses.map((useCase) => (
                  <button
                    key={useCase.id}
                    className="starter-lens-chip"
                    onClick={() => onSelectUseCase(useCase.id)}
                    type="button"
                  >
                    <span>{useCase.icon}</span>
                    <span>{useCase.label}</span>
                  </button>
                ))}
              </div>
              <div className="hint">Browse the full lens library below when you need a more specific decision recipe.</div>
            </article>
          ) : null}
        </>
      ) : (
        <article className="finder-focus">
          <div className="finder-focus-main">
            <div className="finder-focus-head">
              <div>
                <div className="eyebrow">Active lens</div>
                <h3>
                  {selectedUseCase.icon} {selectedUseCase.label}
                </h3>
                <p className="finder-focus-copy">{selectedUseCase.description}</p>
              </div>
              <div className="usecase-status-row">
                <span className={selectedUseCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
                  {selectedUseCase.status === "preview" ? "Preview lens" : "Ready lens"}
                </span>
                <span className="tag">{Math.round(selectedMinCoverage * 100)}% minimum coverage</span>
              </div>
            </div>
            <div className="finder-focus-metrics">
              <div className="finder-metric">
                <strong>{rankingEntries.length}</strong>
                <span>ranked models</span>
              </div>
              <div className="finder-metric">
                <strong>{topEntry ? Math.round(topEntry.score) : "—"}</strong>
                <span>top score</span>
              </div>
              <div className="finder-metric">
                <strong>{selectedRequired.length}</strong>
                <span>required benchmarks</span>
              </div>
            </div>
            <div className="finder-focus-notes">
              <span className="hint">Evidence mix: {formatUseCaseWeights(selectedUseCase, benchmarksById)}.</span>
              {selectedRequired.length ? (
                <span className="hint">
                  Required evidence: {selectedRequired.map((id) => benchmarksById[id]?.short || id.replaceAll("_", " ")).join(", ")}.
                </span>
              ) : null}
            </div>
          </div>
          <div className="finder-focus-actions">
            <button className="btn btn-secondary" onClick={() => onLensPickerOpenChange(!lensPickerOpen)} type="button">
              {lensPickerOpen ? "Hide lens picker" : "Change lens"}
            </button>
            <button
              className="btn btn-primary"
              disabled={compareSeedIds.length < 2}
              onClick={onCompareTopModels}
              type="button"
            >
              Compare top 3
            </button>
            <NavigationLink className="btn btn-secondary btn-link" href={buildHref({ tab: "browser" })} onNavigate={onBrowseCatalog}>
              Browse model browser
            </NavigationLink>
            <NavigationLink
              className="btn btn-ghost btn-link"
              href={buildHref({ tab: "methodology" })}
              onNavigate={onOpenMethodology}
            >
              Review methodology
            </NavigationLink>
          </div>
          {quickRankings.length ? (
            <div className="finder-quick-picks">
              {quickRankings.map((entry) => {
                const compareId = toCatalogIdForMode(entry.model.id, catalogMode, familyLookup);
                const inCompare = compareIds.includes(compareId);
                return (
                  <article
                    key={`quick-${entry.model.id}-${entry.rank}`}
                    className={entry.rank === 1 ? "finder-quick-pick finder-quick-pick-top" : "finder-quick-pick"}
                  >
                    <div className="finder-quick-rank">#{entry.rank}</div>
                    <div className="finder-quick-main">
                      <div className="finder-quick-title">{entry.model.name}</div>
                      <ProviderBadge
                        countryCode={entry.model.provider_country_code}
                        countryFlag={entry.model.provider_country_flag}
                        countryName={entry.model.provider_country_name}
                        provider={entry.model.provider}
                      />
                      <div className="finder-quick-meta">
                        <span>Score {Math.round(entry.score)}</span>
                        <span>{Math.round((entry.coverage || 0) * 100)}% coverage</span>
                      </div>
                    </div>
                    <button
                      aria-label={inCompare ? `Remove ${entry.model.name} from compare` : `Add ${entry.model.name} to compare`}
                      className={inCompare ? "btn btn-secondary btn-active btn-compact" : "btn btn-secondary btn-compact"}
                      onClick={() => onToggleCompare(compareId)}
                      type="button"
                    >
                      {inCompare ? "In compare" : "Add"}
                    </button>
                  </article>
                );
              })}
            </div>
          ) : null}
          <details className="finder-details" open={showExpandedExportContent ? true : undefined}>
            <summary>{selectedRequired.length ? "Why this ranking and what is required" : "Why this ranking"}</summary>
            <div className="finder-details-body">
              <div className="note">
                <strong>Note:</strong> Rankings are weighted normalized composites over the full configured evidence stack.
                Missing optional benchmarks contribute zero score and reduce coverage. Models must cover at least{" "}
                {Math.round(selectedMinCoverage * 100)}% of the benchmark weight and include every required benchmark to be
                ranked.
                <span className="note-list">Evidence mix: {formatUseCaseWeights(selectedUseCase, benchmarksById)}.</span>
                {Object.prototype.hasOwnProperty.call(selectedUseCase.weights, "terminal_bench") ? (
                  <span className="note-list">
                    Terminal-Bench contributes agent-derived workflow evidence from verified single-model public submissions.
                  </span>
                ) : null}
              </div>

              {selectedUseCase.status === "preview" ? (
                <div className="preview-note">
                  Preview lenses are useful for exploration, but they still rely on thinner or more uneven benchmark
                  coverage than the ready lenses.
                </div>
              ) : null}

              {selectedRequired.length ? (
                <div className="panel finder-details-panel">
                  <div className="panel-head">Required evidence</div>
                  <div className="usecase-chip-list">
                    {selectedRequired.map((benchmarkId) => (
                      <span key={benchmarkId} className="usecase-chip usecase-chip-required">
                        {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                      </span>
                    ))}
                  </div>
                  <div className="usecase-note-caption">
                    Models must have every required benchmark to appear in this ranking. If no model satisfies the full
                    evidence stack yet, this lens will stay empty until more data is collected.
                  </div>
                  {Object.keys(selectedNotes).length ? (
                    <div className="usecase-notes">
                      {Object.entries(selectedNotes).map(([benchmarkId, note]) => (
                        <div key={benchmarkId} className="usecase-note-item">
                          <strong>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}:</strong>
                          <span>{note}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </details>
        </article>
      )}

      {(!selectedUseCase || lensPickerOpen) && (
        <div className="usecase-sections">
          {groupedUseCases.map((group) => (
            <section key={group.id} className="usecase-section">
              <div className="usecase-section-head">
                <div className="eyebrow">{group.title}</div>
                <div className="usecase-section-copy">{group.description}</div>
              </div>
              <div className="usecase-grid">
                {group.items.map((useCase) => (
                  <button
                    key={useCase.id}
                    className={selectedUseCase?.id === useCase.id ? "usecase usecase-active" : "usecase"}
                    onClick={() => onSelectUseCase(useCase.id)}
                    type="button"
                  >
                    <div className="usecase-topline">
                      <div className="usecase-icon">{useCase.icon}</div>
                      <span className={useCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
                        {useCase.status === "preview" ? "Preview" : "Ready"}
                      </span>
                    </div>
                    <div className="usecase-label">{useCase.label}</div>
                    <div className="usecase-desc">{useCase.description}</div>
                    <div className="usecase-meta">
                      <span>{Math.round((useCase.min_coverage ?? 0.5) * 100)}% min coverage</span>
                      {useCase.segment === "enterprise" ? <span className="tag tag-enterprise">Enterprise</span> : null}
                    </div>
                    {useCase.required_benchmarks?.length ? (
                      <div className="usecase-chip-list">
                        {useCase.required_benchmarks.slice(0, 3).map((benchmarkId) => (
                          <span key={benchmarkId} className="usecase-chip">
                            {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {rankingsError ? <Banner tone="error" title="Rankings failed" message={rankingsError} /> : null}

      {selectedUseCase ? (
        <section className="stack">
          <div className="section-head finder-results-head">
            <div>
              <h3>
                {selectedUseCase.icon} Best models for <span className="accent">{selectedUseCase.label}</span>
              </h3>
              <div className="hint">
                {rankingEntries.length
                  ? `Showing ${visibleRankings.length} of ${rankingEntries.length}${approvedOnly ? " approved" : ""} ranked models`
                  : "Ranked by weighted benchmark score"}
              </div>
            </div>
            <div className="finder-results-actions">
              <label className="checkbox-row">
                <input
                  checked={approvedOnly}
                  onChange={(event) => onApprovedOnlyChange(event.target.checked)}
                  type="checkbox"
                />
                <span>Approved models only</span>
              </label>
              {rankingEntries.length > 8 ? (
                <button className="btn btn-ghost" onClick={() => onShowAllRankingsChange(!showAllRankings)} type="button">
                  {showingAllRankings ? "Show top 8" : `Show all ${rankingEntries.length}`}
                </button>
              ) : null}
            </div>
          </div>

          <div className="usecase-status-row">
            <span className={selectedUseCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
              {selectedUseCase.status === "preview" ? "Preview lens" : "Ready lens"}
            </span>
            <span className="tag">{Math.round(selectedMinCoverage * 100)}% minimum coverage</span>
          </div>
          {selectedUseCase.status === "preview" ? (
            <div className="preview-note">
              Preview lenses are useful for exploration, but they still rely on thinner or more uneven benchmark coverage
              than the ready lenses.
            </div>
          ) : null}

          {!rankings || rankingEntries.length === 0 ? (
            <EmptyState message={noRankingsMessage} />
          ) : (
            <div className="stack">
              {visibleRankings.map((entry) => (
                <RankedModelCard
                  benchmarksById={benchmarksById}
                  catalogMode={catalogMode}
                  entry={entry}
                  familyLookup={familyLookup}
                  inCompare={compareIds.includes(toCatalogIdForMode(entry.model.id, catalogMode, familyLookup))}
                  key={`${entry.model.id}-${entry.rank}`}
                  onToggleCompare={onToggleCompare}
                  forceExpanded={showExpandedExportContent}
                  selectedUseCase={selectedUseCase}
                />
              ))}
              {remainingRankings > 0 ? (
                <div className="hint">
                  {remainingRankings} more ranked models are available. Expand the list before shortlisting if you need a
                  broader compare set.
                </div>
              ) : null}
            </div>
          )}
        </section>
      ) : null}
    </section>
  );
}

function Methodology({ benchmarks, benchmarksById, catalogMode, selectedUseCaseId, useCases }) {
  const groupedUseCases = groupUseCasesBySegment(useCases);
  const selectedLens = useCases.find((useCase) => useCase.id === selectedUseCaseId) || useCases.find((useCase) => useCase.id === "coding") || useCases[0] || null;
  const benchmarksWithUsage = [...benchmarks]
    .map((benchmark) => ({
      ...benchmark,
      usedBy: useCases.filter((useCase) => Object.prototype.hasOwnProperty.call(useCase.weights || {}, benchmark.id)),
    }))
    .sort((left, right) => {
      if (left.tier !== right.tier) {
        return left.tier - right.tier;
      }
      return left.name.localeCompare(right.name);
    });

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Methodology</h2>
          <p>How this app ranks models, what each source measures, and how to interpret the outputs responsibly.</p>
        </div>
        <div className="hint">This is the decision logic behind every use-case ranking.</div>
      </div>

      <div className="method-grid">
        <article className="panel method-card">
          <div className="panel-head">What this app is doing</div>
          <div className="method-copy">
            This is a weighted decision system over benchmark evidence. It is not claiming one universal “best model”.
            Each use case defines its own evidence mix, minimum coverage threshold, and required benchmarks.
          </div>
          <div className="method-list">
            <div><strong>Score:</strong> weighted normalized composite over the full configured evidence stack, not a raw percentage.</div>
            <div><strong>Coverage:</strong> how much of the use-case evidence stack a model actually covers.</div>
            <div><strong>Required evidence:</strong> models missing any required benchmark are excluded from that lens.</div>
          </div>
        </article>

        <article className="panel method-card">
          <div className="panel-head">How ranking works</div>
          <div className="method-steps">
            <div className="method-step"><strong>1.</strong> Pick the benchmarks that belong to the selected lens.</div>
            <div className="method-step"><strong>2.</strong> Normalize each benchmark against the current model pool, including inverting lower-is-better metrics like cost or hallucination rate.</div>
            <div className="method-step"><strong>3.</strong> Apply the lens weights across the full configured evidence stack; missing optional benchmarks contribute zero and lower coverage.</div>
            <div className="method-step"><strong>4.</strong> Exclude any model missing required benchmarks or falling below the lens minimum coverage threshold.</div>
            <div className="method-step"><strong>5.</strong> Sort the remaining models by weighted score, then coverage.</div>
          </div>
        </article>

        <article className="panel method-card">
          <div className="panel-head">How to read results</div>
          <div className="method-list">
            <div><strong>#1 rank:</strong> strongest evidence mix for that lens in the current dataset.</div>
            <div><strong>High coverage matters:</strong> two models can have similar scores, but the one covering more of the evidence stack is usually the safer pick.</div>
            <div><strong>Empty lens:</strong> means no model currently satisfies the required evidence stack for that use case.</div>
            <div><strong>Preview lens:</strong> useful for exploration, but still thinner or more uneven than ready lenses.</div>
            <div><strong>{catalogMode === "family" ? "Families mode" : "Individual models mode"}:</strong> {catalogMode === "family" ? "individual models are first grouped into canonical models, then rolled into a family card using the best available benchmark evidence per family." : "you are looking at individual model cards with no family aggregation."}</div>
          </div>
          <div className="method-badges">
            <span className="method-badge"><SourceBadge score={{ source_type: "primary", verified: true }} /> direct primary row</span>
            <span className="method-badge"><SourceBadge score={{ source_type: "secondary", verified: false }} /> lower-trust / derived / self-reported</span>
            <span className="method-badge"><SourceBadge score={{ source_type: "manual", verified: false }} /> manual entry</span>
          </div>
        </article>

        <article className="panel method-card">
          <div className="panel-head">How to use this tool</div>
          <div className="method-list">
            <div><strong>Start with a use case lens:</strong> that gives you the right weighting for the task you actually care about.</div>
            <div><strong>Use families first:</strong> it is the best default for procurement and shortlist decisions.</div>
            <div><strong>Switch to individual models second:</strong> use it when you need to choose between reasoning, max, mini, or context-window variants.</div>
            <div><strong>Open the benchmark rows:</strong> check source, caveat, and missing evidence before trusting a high rank.</div>
          </div>
        </article>
      </div>

      {selectedLens ? (
        <section className="panel methodology-focus">
          <div className="panel-head">How to read the current lens</div>
          <div className="method-focus-head">
            <div className="method-focus-title">
              <span className="usecase-icon">{selectedLens.icon}</span>
              <div>
                <div className="title">{selectedLens.label}</div>
                <div className="method-subtle">{selectedLens.description}</div>
              </div>
            </div>
            <div className="usecase-status-row">
              <span className={selectedLens.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
                {selectedLens.status === "preview" ? "Preview lens" : "Ready lens"}
              </span>
              <span className="tag">{Math.round((selectedLens.min_coverage ?? 0.5) * 100)}% minimum coverage</span>
            </div>
          </div>
          <div className="method-grid">
            <div className="method-card method-card-soft">
              <div className="detail-label">Weights</div>
              <div className="weight-list">
                {Object.entries(selectedLens.weights || {})
                  .sort((left, right) => right[1] - left[1])
                  .map(([benchmarkId, weight]) => (
                    <div key={benchmarkId} className="weight-row">
                      <span>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}</span>
                      <span>{Math.round(weight * 100)}%</span>
                    </div>
                  ))}
              </div>
            </div>
            <div className="method-card method-card-soft">
              <div className="detail-label">Required evidence</div>
              <div className="usecase-chip-list">
                {(selectedLens.required_benchmarks || []).map((benchmarkId) => (
                  <span key={benchmarkId} className="usecase-chip usecase-chip-required">
                    {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
              <div className="method-subtle">
                Models must have these benchmarks to appear in the ranking. If nobody satisfies the full stack yet,
                the lens will return no ranked models.
              </div>
            </div>
          </div>
          <div className="usecase-notes">
            {Object.entries(selectedLens.benchmark_notes || {}).map(([benchmarkId, note]) => (
              <div key={benchmarkId} className="usecase-note-item">
                <strong>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}:</strong>
                <span>{note}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="stack">
        <div className="section-head">
          <div>
            <h3>Use-case lenses</h3>
            <p>Every lens is a different ranking recipe. The weights below are the actual scoring logic.</p>
          </div>
        </div>
        {groupedUseCases.map((group) => (
          <section key={group.id} className="stack stack-tight">
            <div className="usecase-section-head">
              <div className="eyebrow">{group.title}</div>
              <div className="usecase-section-copy">{group.description}</div>
            </div>
            <div className="methodology-usecases">
              {group.items.map((useCase) => (
                <article key={useCase.id} className="panel method-card">
                  <div className="method-focus-head">
                    <div className="method-focus-title">
                      <span className="usecase-icon">{useCase.icon}</span>
                      <div>
                        <div className="title">{useCase.label}</div>
                        <div className="method-subtle">{useCase.description}</div>
                      </div>
                    </div>
                    <div className="usecase-status-row">
                      <span className={useCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
                        {useCase.status === "preview" ? "Preview" : "Ready"}
                      </span>
                      <span className="tag">{Math.round((useCase.min_coverage ?? 0.5) * 100)}% min coverage</span>
                    </div>
                  </div>
                  <div className="usecase-chip-list">
                    {(useCase.required_benchmarks || []).map((benchmarkId) => (
                      <span key={benchmarkId} className="usecase-chip usecase-chip-required">
                        {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                      </span>
                    ))}
                  </div>
                  <div className="weight-list">
                    {Object.entries(useCase.weights || {})
                      .sort((left, right) => right[1] - left[1])
                      .map(([benchmarkId, weight]) => (
                        <div key={benchmarkId} className="weight-row">
                          <span>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}</span>
                          <span>{Math.round(weight * 100)}%</span>
                        </div>
                      ))}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </section>

      <section className="stack">
        <div className="section-head">
          <div>
            <h3>Benchmark source library</h3>
            <p>What each benchmark is, who publishes it, why it matters, and where it is used.</p>
          </div>
        </div>
        <div className="methodology-benchmarks">
          {benchmarksWithUsage.map((benchmark) => {
            const context = getBenchmarkContext(benchmark);
            return (
              <article key={benchmark.id} className="panel method-card">
                <div className="method-focus-head">
                  <div>
                    <div className="title">{benchmark.name}</div>
                    <div className="method-subtle">{benchmark.short} · {benchmark.category}</div>
                  </div>
                  <div className="usecase-status-row">
                    <span className="tag">Tier {benchmark.tier}</span>
                    <span className="tag">{benchmark.higher_is_better ? "Higher is better" : "Lower is better"}</span>
                  </div>
                </div>
                <div className="method-list">
                  <div><strong>Metric:</strong> {benchmark.metric}</div>
                  <div><strong>Source:</strong> {context.source}</div>
                  <div><strong>Why it matters:</strong> {context.why}</div>
                  {context.caveat ? <div><strong>Caveat:</strong> {context.caveat}</div> : null}
                  <div><strong>Used in:</strong> {benchmark.usedBy.length ? benchmark.usedBy.map((useCase) => useCase.label).join(", ") : "Not currently used in a ranking lens."}</div>
                </div>
                {benchmark.url ? (
                  <a className="bench-source" href={benchmark.url} rel="noreferrer" target="_blank">
                    Open source leaderboard
                  </a>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </section>
  );
}

function RankedModelCard({
  benchmarksById,
  catalogMode,
  entry,
  familyLookup,
  forceExpanded = false,
  inCompare,
  onToggleCompare,
  selectedUseCase,
}) {
  const [expanded, setExpanded] = useState(false);
  const isTop = entry.rank === 1;
  const criticalMissing = entry.critical_missing_benchmarks || [];
  const compareId = toCatalogIdForMode(entry.model.id, catalogMode, familyLookup);
  const isExpanded = forceExpanded || expanded;
  const ageMeta = getModelAgeMeta(entry.model);
  const licenseLabel = getModelLicenseLabel(entry.model);
  const metadataLinks = getModelMetadataLinks(entry.model);
  const recommendationSummary = getRecommendationSummary(entry.model, selectedUseCase?.id);
  const detailPills = [
    { label: "Benchmark coverage", value: `${Math.round(entry.coverage * 100)}%` },
    { label: "Composite score", value: Math.round(entry.score) },
    { label: "Context", value: entry.model.context_window || "Unknown" },
    { label: "Released", value: entry.model.release_date || "Unknown" },
    ageMeta ? { label: "Age", value: ageMeta.label } : null,
  ].filter(Boolean);

  return (
    <article className={isTop ? "card card-top card-with-status-rail" : "card card-with-status-rail"}>
      {recommendationSummary ? <RecommendationRail summary={recommendationSummary} /> : null}
      <div className="card-shell">
        <div className="card-body">
          <div className="rank-pill">{entry.rank}</div>
          <div className="card-main">
            <div className="card-headline">
              <span className="title">{entry.model.name}</span>
              <ProviderBadge
                countryCode={entry.model.provider_country_code}
                countryFlag={entry.model.provider_country_flag}
                countryName={entry.model.provider_country_name}
                provider={entry.model.provider}
              />
              <CatalogStatusBadge model={entry.model} />
              <ApprovalBadge model={entry.model} useCaseId={selectedUseCase?.id} />
              <TypeBadge type={entry.model.type} />
              {licenseLabel ? <span className="tag tag-license">License: {licenseLabel}</span> : null}
              {isTop ? <span className="tag tag-top">Top pick</span> : null}
              {criticalMissing.length ? (
                <span className="tag tag-warning">Critical gaps: {criticalMissing.map((id) => benchmarksById[id]?.short || id.replaceAll("_", " ")).join(", ")}</span>
              ) : null}
            </div>
            <ScoreBar score={entry.score} />
          </div>
          <div className="card-actions">
            <button
              aria-label={inCompare ? `Remove ${entry.model.name} from compare` : `Add ${entry.model.name} to compare`}
              className={inCompare ? "btn btn-secondary btn-active" : "btn btn-secondary"}
              onClick={() => onToggleCompare(compareId)}
              type="button"
            >
              {inCompare ? "In compare" : "Add to compare"}
            </button>
            <button
              aria-expanded={isExpanded}
              aria-label={isExpanded ? `Hide evidence for ${entry.model.name}` : `View evidence for ${entry.model.name}`}
              className="link-btn"
              onClick={() => setExpanded((value) => !value)}
              type="button"
            >
              {isExpanded ? "Hide evidence" : "View evidence"}
            </button>
          </div>
        </div>
        {isExpanded ? (
          <div className="card-details">
            <div className="model-detail-summary">
              {detailPills.map((item) => (
                <span key={item.label} className="detail-pill">
                  {item.label} <strong>{item.value}</strong>
                </span>
              ))}
            </div>
            <div className="detail-label">Benchmark breakdown</div>
            {criticalMissing.length ? (
              <div className="critical-gaps">
                <strong>Critical evidence missing:</strong>{" "}
                {criticalMissing.map((id) => benchmarksById[id]?.short || id.replaceAll("_", " ")).join(", ")}
              </div>
            ) : null}
            <div className="detail-list">
              {entry.breakdown.map((item) => (
                <div key={item.benchmark_id} className="detail-row">
                  <span className="detail-short">{benchmarksById[item.benchmark_id]?.short || item.benchmark_id.replaceAll("_", " ")}</span>
                  <div className="mini-bar">
                    <div
                      className={`mini-fill mini-fill-${getBenchmarkTone(benchmarksById[item.benchmark_id], item.raw_value)}`}
                      style={{ width: `${item.normalised}%` }}
                    />
                  </div>
                  <span className="detail-value">
                    <SourceBadge score={{ source_type: item.source_type, verified: item.verified }} />
                    {formatBenchmarkValue(benchmarksById[item.benchmark_id], item.raw_value)}
                  </span>
                  <span className="detail-weight">{Math.round(item.weight * 100)}% weight</span>
                  {item.variant_model_name && item.variant_model_name !== entry.model.name ? <span className="detail-note">via {item.variant_model_name}</span> : null}
                  {getBenchmarkScaleDescriptor(benchmarksById[item.benchmark_id], item.raw_value) ? (
                    <span className="detail-note">Relative speed: {getBenchmarkScaleDescriptor(benchmarksById[item.benchmark_id], item.raw_value)}</span>
                  ) : null}
                  {item.notes ? <span className="detail-note">{item.notes}</span> : null}
                </div>
              ))}
              {entry.missing_benchmarks.length ? (
                <div className="missing">
                  Missing optional evidence lowers this score and coverage: {entry.missing_benchmarks.map((id) => benchmarksById[id]?.short || id.replaceAll("_", " ")).join(", ")}
                </div>
              ) : null}
            </div>
            <div className="small-meta">
              Context: {entry.model.context_window || "Unknown"} · Released: {entry.model.release_date || "Unknown"}
              {ageMeta ? ` · Age: ${ageMeta.label}` : ""}{licenseLabel ? ` · License: ${licenseLabel}` : ""}
            </div>
            {metadataLinks.length ? (
              <div className="metadata-link-row">
                {metadataLinks.map((entryLink) => (
                  <a
                    className="metadata-link"
                    href={entryLink.url}
                    key={`${entry.model.id}-${entryLink.label}`}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {entryLink.label}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function ModelBrowser({
  approvedOnly,
  benchmarksById,
  browserOnlyCompared,
  browserSort,
  catalogMode,
  compareIds,
  exactModelsById,
  expandedId,
  exportMode,
  filteredModelsCount,
  hasMoreResults,
  inferenceLocationFilter,
  inferenceLocations,
  visibleModels,
  onAddToCompare,
  onApprovedOnlyChange,
  onBrowserOnlyComparedChange,
  onBrowserSortChange,
  onCatalogModeChange,
  onClearFilters,
  onExpandedIdChange,
  onInferenceLocationFilterChange,
  onLoadMore,
  onProviderFilterChange,
  onQueryChange,
  onRecommendationFilterChange,
  onTypeFilterChange,
  providerFilter,
  providers,
  query,
  rankingByCatalogId,
  recommendationFilter,
  selectedUseCase,
  typeFilter,
}) {
  const defaultRecommendationFilter = selectedUseCase ? DASHBOARD_DEFAULT_RECOMMENDATION_FILTER : DEFAULT_RECOMMENDATION_FILTER;
  const hasActiveFilters =
    query.trim() !== "" ||
    providerFilter !== "All" ||
    inferenceLocationFilter !== DEFAULT_INFERENCE_LOCATION_FILTER ||
    typeFilter !== "All" ||
    approvedOnly ||
    recommendationFilter !== defaultRecommendationFilter ||
    browserOnlyCompared ||
    browserSort !== "smart";

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Model Browser</h2>
          <p>
            Search and explore all tracked models with their full benchmark profiles.
            {catalogMode === "family" ? " Families mode combines individual models into canonical models before rolling them into a family card." : ""}
          </p>
        </div>
        <ViewModeToggle mode={catalogMode} onChange={onCatalogModeChange} />
      </div>

      <article className="panel browser-toolbar">
        <div className="toolbar toolbar-wide">
          <label className="field">
            <span className="field-label">Search models</span>
            <input
              className="input"
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search models, providers, or family names…"
              type="text"
              value={query}
            />
          </label>
          <label className="field">
            <span className="field-label">Provider</span>
            <select className="input select" onChange={(event) => onProviderFilterChange(event.target.value)} value={providerFilter}>
              {providers.map((provider) => (
                <option key={provider} value={provider}>
                  {provider}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Model type</span>
            <select className="input select" onChange={(event) => onTypeFilterChange(event.target.value)} value={typeFilter}>
              <option value="All">All types</option>
              <option value="proprietary">Proprietary</option>
              <option value="open_weights">Open weights</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Inference location</span>
            <select
              className="input select"
              onChange={(event) => onInferenceLocationFilterChange(event.target.value)}
              value={inferenceLocationFilter}
            >
              {inferenceLocations.map((location) => (
                <option key={location} value={location}>
                  {location === DEFAULT_INFERENCE_LOCATION_FILTER ? "All locations" : location}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Sort order</span>
            <select className="input select" onChange={(event) => onBrowserSortChange(event.target.value)} value={browserSort}>
              {BROWSER_SORT_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.id === "smart"
                    ? selectedUseCase
                      ? `${option.label} (${selectedUseCase.label})`
                      : "Smart order (coverage first)"
                    : option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Recommendation</span>
            <select
              className="input select"
              disabled={!selectedUseCase}
              onChange={(event) => onRecommendationFilterChange(event.target.value)}
              value={recommendationFilter}
            >
              {RECOMMENDATION_FILTER_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {!selectedUseCase && option.id === DEFAULT_RECOMMENDATION_FILTER
                    ? "Select a lens first"
                    : option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="browser-toolbar-footer">
          <label className="checkbox-row">
            <input
              checked={approvedOnly}
              onChange={(event) => onApprovedOnlyChange(event.target.checked)}
              type="checkbox"
            />
            <span>Approved models only</span>
          </label>
          <label className="checkbox-row">
            <input
              checked={browserOnlyCompared}
              onChange={(event) => onBrowserOnlyComparedChange(event.target.checked)}
              type="checkbox"
            />
            <span>Show compared models only</span>
          </label>
          <div className="browser-meta">
            <span className="hint">
              {filteredModelsCount.toLocaleString()} results
              {selectedUseCase ? ` · tuned to ${selectedUseCase.label}` : ""}
              {!selectedUseCase && recommendationFilter !== defaultRecommendationFilter ? " · recommendation filter inactive without a lens" : ""}
            </span>
            {hasActiveFilters ? (
              <button className="btn btn-ghost btn-inline" onClick={onClearFilters} type="button">
                Clear filters
              </button>
            ) : null}
          </div>
        </div>
      </article>

      <div className="stack">
        {!visibleModels.length ? (
          <EmptyState
            message={
              browserOnlyCompared
                ? "No compared models match the current filters. Clear filters or add more models to compare."
                : "No models match your current filters."
            }
          />
        ) : null}
        {visibleModels.map((model) => (
          <ModelBrowserCard
            benchmarksById={benchmarksById}
            key={model.id}
            compareIds={compareIds}
            exactModelsById={exactModelsById}
            expanded={exportMode || expandedId === model.id}
            exportMode={exportMode}
            lensEntry={rankingByCatalogId[model.id]}
            model={model}
            onAddToCompare={onAddToCompare}
            onToggle={() => onExpandedIdChange(expandedId === model.id ? null : model.id)}
            selectedUseCase={selectedUseCase}
          />
        ))}
        {hasMoreResults ? (
          <div className="list-footer">
            <button className="btn btn-secondary" onClick={onLoadMore} type="button">
              Load {DEFAULT_BROWSER_LIMIT} more
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function ModelBrowserCard({
  benchmarksById,
  compareIds,
  exactModelsById,
  expanded,
  exportMode,
  lensEntry,
  model,
  onAddToCompare,
  onToggle,
  selectedUseCase,
}) {
  const [showBenchmarkNotes, setShowBenchmarkNotes] = useState(false);
  const showExpandedNotes = exportMode || showBenchmarkNotes;
  const scoredBenchmarks = Object.entries(model.scores).filter(([, score]) => score?.value != null);
  const coverage = Math.round((scoredBenchmarks.length / Math.max(1, Object.keys(model.scores).length)) * 100);
  const isFamily = Boolean(model.family && model.family.member_count > 1);
  const familyBenchmarkWins = isFamily ? getFamilyBenchmarkWins(model) : {};
  const familyVariants = isFamily ? getFamilyVariants(model, exactModelsById, familyBenchmarkWins) : [];
  const legacyAdvisoryMemberModels = isFamily ? familyVariants : null;
  const legacyAdvisoryInline = getLegacyAdvisoryInline(model, legacyAdvisoryMemberModels);
  const sortedBenchmarkIds = sortBenchmarkIdsForLens(model, selectedUseCase, benchmarksById);
  const openRouterLabel = getPreferredOpenRouterLabel(model, selectedUseCase);
  const openRouterDetail = getOpenRouterPopularityDetail(model, selectedUseCase);
  const inferenceSummaryLabel = getInferenceSummaryLabel(model.inference_summary);
  const pricingReferenceLabel = getModelPricingReferenceLabel(model);
  const licenseLabel = getModelLicenseLabel(model);
  const metadataLinks = getModelMetadataLinks(model);
  const lensEligibility = selectedUseCase ? getLensEligibilitySummary(model, selectedUseCase, benchmarksById) : null;
  const ageMeta = getModelAgeMeta(model);
  const recommendationSummary = getRecommendationSummary(model, selectedUseCase?.id);
  const inferenceSectionLabel = isFamily ? "Family Inference Footprint" : "Inference";
  const inferenceSectionCaption = isFamily
    ? `Union across ${familyVariants.length || model.family?.member_count || 0} variants. Pricing and locations below are aggregated at the family level.`
    : inferenceSummaryLabel;
  const benchmarkSectionLabel = isFamily ? "Benchmarks by Winning Variant" : "Benchmarks";
  const benchmarkSectionCaption = isFamily
    ? "Each row shows the best family result for that benchmark and names the variant that supplies it."
    : "";
  const detailPills = [
    { label: "Benchmark coverage", value: `${coverage}%` },
    lensEntry ? { label: "Composite score", value: Math.round(lensEntry.score) } : null,
    { label: isFamily ? "Context range" : "Context", value: model.context_window || "Unknown" },
    { label: isFamily ? "Release range" : "Released", value: model.release_date || "Unknown" },
    ageMeta ? { label: "Age", value: ageMeta.label } : null,
    openRouterDetail ? { label: "OpenRouter", value: openRouterDetail } : null,
  ].filter(Boolean);

  return (
    <article className="card card-with-status-rail">
      {recommendationSummary ? <RecommendationRail summary={recommendationSummary} /> : null}
      <div className="card-shell">
        <div className="card-body">
          <div className="card-main">
            <div className="card-headline">
              <span className="title">{model.name}</span>
              <ProviderBadge
                countryCode={model.provider_country_code}
                countryFlag={model.provider_country_flag}
                countryName={model.provider_country_name}
                provider={model.provider}
              />
              <CatalogStatusBadge model={model} />
              <ApprovalBadge model={model} useCaseId={selectedUseCase?.id} />
              <LegacyAdvisoryBadge model={model} memberModels={legacyAdvisoryMemberModels} />
              <TypeBadge type={model.type} />
              {licenseLabel ? <span className="tag tag-license">License: {licenseLabel}</span> : null}
              {isFamily ? <span className="tag tag-family">{model.family.member_count} variants</span> : null}
              {selectedUseCase ? (
                lensEntry ? (
                  <span className="tag tag-top">
                    #{lensEntry.rank} in {selectedUseCase.label}
                  </span>
                ) : (
                  <span className={lensEligibility?.status === "missing_required" ? "tag tag-warning" : "tag"}>
                    {lensEligibility?.badgeLabel || `Not ranked in ${selectedUseCase.label}`}
                  </span>
                )
              ) : null}
              {openRouterLabel ? <span className="tag">{openRouterLabel}</span> : null}
            </div>
            <div className="submeta">
              <span>Context: {model.context_window || "Unknown"}</span>
              <span>Released: {model.release_date || "Unknown"}</span>
              {ageMeta ? <span>Age: {ageMeta.label}</span> : null}
              {lensEntry ? <span className="submeta-score">Score {Math.round(lensEntry.score)}</span> : null}
              {selectedUseCase && !lensEntry && lensEligibility?.inlineLabel ? (
                <span className={lensEligibility.status === "missing_required" ? "lens-gap-note lens-gap-note-warning" : "lens-gap-note"}>
                  {lensEligibility.inlineLabel}
                </span>
              ) : null}
            </div>
            {legacyAdvisoryInline ? (
              <div className="legacy-inline-note" title={legacyAdvisoryInline.title}>
                <strong>{legacyAdvisoryInline.headline}</strong> {legacyAdvisoryInline.body}
              </div>
            ) : null}
          </div>
          <div className="card-actions">
            <button
              className={compareIds.includes(model.id) ? "btn btn-secondary btn-active" : "btn btn-secondary"}
              onClick={() => onAddToCompare(model.id)}
              type="button"
            >
              {compareIds.includes(model.id) ? "In compare" : "Add to compare"}
            </button>
            <button
              aria-expanded={expanded}
              aria-label={expanded ? `Hide details for ${model.name}` : `Show details for ${model.name}`}
              className="link-btn"
              onClick={onToggle}
              type="button"
            >
              {expanded ? "Hide Details" : "Show Details"}
            </button>
          </div>
        </div>
        {expanded ? (
          <div className="card-details">
          <div className="model-detail-summary">
            {detailPills.map((item) => (
              <span key={item.label} className="detail-pill">
                {item.label} <strong>{item.value}</strong>
              </span>
            ))}
          </div>
          {selectedUseCase && !lensEntry && lensEligibility?.detailMessage ? (
            <div className="note">
              <strong>Why this {isFamily ? "family" : "exact model"} is not ranked in {selectedUseCase.label}:</strong> {lensEligibility.detailMessage}
            </div>
          ) : null}
          {(licenseLabel || metadataLinks.length || model.intended_use_short || model.limitations_short || model.training_cutoff || (model.capabilities || []).length || (model.supported_languages || []).length || (model.base_models || []).length) ? (
            <div className="stack stack-tight">
              <div className="details-head">
                <div className="detail-copy">
                  <div className="detail-label">Model Card Metadata</div>
                  <div className="detail-caption">
                    Structured metadata pulled from the linked model card where available.
                  </div>
                </div>
              </div>
              {metadataLinks.length ? (
                <div className="metadata-link-row">
                  {metadataLinks.map((entry) => (
                    <a
                      className="metadata-link"
                      href={entry.url}
                      key={`${model.id}-${entry.label}`}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {entry.label}
                    </a>
                  ))}
                </div>
              ) : null}
              <div className="metadata-summary-grid">
                {licenseLabel ? (
                  <div className="metadata-summary-item">
                    <strong>License</strong>
                    <span>{licenseLabel}</span>
                  </div>
                ) : null}
                {model.training_cutoff ? (
                  <div className="metadata-summary-item">
                    <strong>Training cutoff</strong>
                    <span>{model.training_cutoff}</span>
                  </div>
                ) : null}
                {model.base_models?.length ? (
                  <div className="metadata-summary-item">
                    <strong>Base model</strong>
                    <span>{model.base_models.join(", ")}</span>
                  </div>
                ) : null}
                {model.supported_languages?.length ? (
                  <div className="metadata-summary-item">
                    <strong>Languages</strong>
                    <span>{model.supported_languages.join(", ")}</span>
                  </div>
                ) : null}
                {model.capabilities?.length ? (
                  <div className="metadata-summary-item">
                    <strong>Capabilities</strong>
                    <span>{model.capabilities.join(", ")}</span>
                  </div>
                ) : null}
              </div>
              {model.intended_use_short ? (
                <div className="note">
                  <strong>Intended use:</strong> {model.intended_use_short}
                </div>
              ) : null}
              {model.limitations_short ? (
                <div className="note">
                  <strong>Limitations:</strong> {model.limitations_short}
                </div>
              ) : null}
            </div>
          ) : null}
          {isFamily ? (
            <>
              <div className="note">
                <strong>Family overview:</strong> this card is an aggregate. Benchmark rows use the best available variant per benchmark, while pricing and routing show the family-wide range and routing union. Use the variant cards below for exact model-level operating details.
              </div>
              <div className="stack stack-tight">
                <div className="details-head">
                  <div className="detail-copy">
                    <div className="detail-label">Variant Details</div>
                    <div className="detail-caption">
                      Exact prices, context windows, routing footprint, and the family benchmark rows each variant supplies.
                    </div>
                  </div>
                </div>
                {familyVariants.length ? (
                  <div className="family-variant-grid">
                    {familyVariants.map((variant) => (
                      <FamilyVariantCard
                        benchmarkWins={familyBenchmarkWins[variant.id] || []}
                        benchmarksById={benchmarksById}
                        isRepresentative={variant.id === model.family?.representative_id}
                        key={variant.id}
                        selectedUseCase={selectedUseCase}
                        variant={variant}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="member-chips">
                    {model.family.member_names.map((memberName) => (
                      <span key={memberName} className="member-chip">
                        {memberName}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : null}
          <div className="stack stack-tight">
            <div className="details-head">
              <div className="detail-copy">
                <div className="detail-label">{inferenceSectionLabel}</div>
                {inferenceSectionCaption ? <div className="detail-caption">{inferenceSectionCaption}</div> : null}
              </div>
            </div>
            {model.inference_destinations?.length ? (
              <div className="inference-grid">
                {model.inference_destinations.map((destination) => (
                  <InferenceDestinationCard
                    key={destination.id}
                    destination={destination}
                    pricingReferenceLabel={pricingReferenceLabel}
                    pricingReferencePrefix={isFamily ? "Family price range" : "Reference price"}
                  />
                ))}
              </div>
            ) : (
              <div className="inference-empty">
                No hyperscaler routing snapshot is tracked for this {isFamily ? "family" : "model"} yet.
              </div>
            )}
          </div>
          <div className="stack stack-tight">
            <div className="details-head">
              <div className="detail-copy">
                <div className="detail-label">{benchmarkSectionLabel}</div>
                {benchmarkSectionCaption ? <div className="detail-caption">{benchmarkSectionCaption}</div> : null}
              </div>
              <button
                aria-pressed={showExpandedNotes}
                className="link-btn"
                onClick={() => setShowBenchmarkNotes((value) => !value)}
                type="button"
              >
                {showExpandedNotes ? "Hide Notes" : "Show Notes"}
              </button>
            </div>
            <div className="bench-grid">
              {sortedBenchmarkIds.map((benchmarkId) => {
                const score = model.scores[benchmarkId];
                const benchmark = benchmarksById[benchmarkId];
                const label = benchmark?.short || benchmarkId.replaceAll("_", " ");
                const variantName = score?.family_variant_name;
                const variantMetaLabel = variantName ? (isFamily ? `Best family score from ${variantName}` : `via ${variantName}`) : "";
                const provenance = benchmarkId === "terminal_bench" ? score?.notes : "";
                const benchmarkContext = getBenchmarkContext(benchmark);
                const normalizedValue =
                  score?.value != null ? normalizeBenchmarkValue(benchmark, score.value) : 0;
                const benchmarkTone = getBenchmarkTone(benchmark, score?.value);
                const benchmarkScaleDescriptor = getBenchmarkScaleDescriptor(benchmark, score?.value);
                return (
                  <div key={benchmarkId} className="bench-row">
                    {benchmark?.url ? (
                      <a className="bench-short bench-link" href={benchmark.url} rel="noreferrer" target="_blank">
                        {label}
                      </a>
                    ) : (
                      <span className="bench-short">{label}</span>
                    )}
                    {score?.value != null ? (
                      <>
                        <div className="mini-bar">
                          <div
                            className={`mini-fill mini-fill-${benchmarkTone}`}
                            style={{ width: `${normalizedValue}%` }}
                          />
                        </div>
                        <span className={`bench-score bench-score-${benchmarkTone}`}>
                          <SourceBadge score={score} />
                          {formatBenchmarkValue(benchmark, score.value)}
                        </span>
                        <div className="bench-meta">
                          {variantMetaLabel ? <span className="bench-meta-item">{variantMetaLabel}</span> : null}
                          {benchmarkScaleDescriptor ? <span className="bench-meta-item">Relative speed: {benchmarkScaleDescriptor}</span> : null}
                          {score?.collected_at ? (
                            <span className="bench-meta-item">Updated {formatDate(score.collected_at)}</span>
                          ) : null}
                          {benchmark?.url ? (
                            <a className="bench-source" href={benchmark.url} rel="noreferrer" target="_blank">
                              Source: {benchmarkContext.source}
                            </a>
                          ) : (
                            <span className="bench-source bench-source-static">Source: {benchmarkContext.source}</span>
                          )}
                        </div>
                        {showExpandedNotes && provenance ? <span className="bench-provenance">{provenance}</span> : null}
                        {showExpandedNotes ? <span className="bench-context">Why it matters: {benchmarkContext.why}</span> : null}
                        {showExpandedNotes && benchmarkContext.caveat ? (
                          <span className="bench-caveat">Caveat: {benchmarkContext.caveat}</span>
                        ) : null}
                      </>
                    ) : (
                      <>
                        <span className="bench-empty">No data</span>
                        <div className="bench-meta">
                          {benchmark?.url ? (
                            <a className="bench-source" href={benchmark.url} rel="noreferrer" target="_blank">
                              Source: {benchmarkContext.source}
                            </a>
                          ) : (
                            <span className="bench-source bench-source-static">Source: {benchmarkContext.source}</span>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function getFamilyBenchmarkWins(model) {
  return Object.entries(model?.scores || {}).reduce((winsByVariantId, [benchmarkId, score]) => {
    if (score?.value == null || !score?.family_variant_id) {
      return winsByVariantId;
    }
    const variantId = String(score.family_variant_id);
    if (!winsByVariantId[variantId]) {
      winsByVariantId[variantId] = [];
    }
    winsByVariantId[variantId].push(benchmarkId);
    return winsByVariantId;
  }, {});
}

function getFamilyVariants(model, exactModelsById, benchmarkWinsByVariantId) {
  const representativeId = model.family?.representative_id || "";
  return (model.family?.member_ids || [])
    .map((memberId) => exactModelsById?.[memberId])
    .filter(Boolean)
    .sort((left, right) => {
      const leftRepresentative = left.id === representativeId ? 1 : 0;
      const rightRepresentative = right.id === representativeId ? 1 : 0;
      if (leftRepresentative !== rightRepresentative) {
        return rightRepresentative - leftRepresentative;
      }

      const leftWins = (benchmarkWinsByVariantId[left.id] || []).length;
      const rightWins = (benchmarkWinsByVariantId[right.id] || []).length;
      if (leftWins !== rightWins) {
        return rightWins - leftWins;
      }

      return left.name.localeCompare(right.name);
    });
}

function FamilyVariantCard({ benchmarkWins, benchmarksById, isRepresentative, selectedUseCase, variant }) {
  const ageMeta = getModelAgeMeta(variant);
  const pricingLabel = getModelPricingReferenceLabel(variant);
  const licenseLabel = getModelLicenseLabel(variant);
  const metadataLinks = getModelMetadataLinks(variant);
  const inferenceSummaryLabel = getInferenceSummaryLabel(variant.inference_summary);
  const inferenceLocations = getModelInferenceCountries(variant);
  const benchmarkWinSet = new Set(benchmarkWins);
  const orderedBenchmarkWins = sortBenchmarkIdsForLens(variant, selectedUseCase, benchmarksById).filter((benchmarkId) =>
    benchmarkWinSet.has(benchmarkId),
  );
  const visibleBenchmarkWins = orderedBenchmarkWins.slice(0, 6);
  const visibleLocations = inferenceLocations.slice(0, 6);
  const platformNames = Array.from(
    new Set((variant.inference_destinations || []).map((destination) => destination.name).filter(Boolean)),
  );

  return (
    <article className="family-variant-card">
      <div className="family-variant-head">
        <div className="family-variant-title-row">
          <div className="family-variant-title">{variant.name}</div>
          {isRepresentative ? <span className="tag tag-detail">Representative</span> : null}
          {orderedBenchmarkWins.length ? (
            <span className="tag tag-detail">
              {orderedBenchmarkWins.length} benchmark row{orderedBenchmarkWins.length === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>
        <div className="family-variant-meta">
          <span>Context: {variant.context_window || "Unknown"}</span>
          <span>Released: {variant.release_date || "Unknown"}</span>
          {ageMeta ? <span>Age: {ageMeta.label}</span> : null}
          {licenseLabel ? <span>License: {licenseLabel}</span> : null}
        </div>
      </div>
      <div className="family-variant-stat">{pricingLabel ? `Price: ${pricingLabel}` : "Price: unavailable"}</div>
      {metadataLinks.length ? (
        <div className="metadata-link-row">
          {metadataLinks.map((entry) => (
            <a
              className="metadata-link"
              href={entry.url}
              key={`${variant.id}-${entry.label}`}
              rel="noreferrer"
              target="_blank"
            >
              {entry.label}
            </a>
          ))}
        </div>
      ) : null}
      <div className="family-variant-stat">
        {inferenceSummaryLabel ? `Routing: ${inferenceSummaryLabel}` : "Routing: no tracked destinations"}
      </div>
      {platformNames.length ? <div className="family-variant-muted">Platforms: {platformNames.join(", ")}</div> : null}
      {visibleLocations.length ? (
        <div className="family-variant-chip-row">
          {visibleLocations.map((location) => (
            <span className="family-variant-chip" key={`${variant.id}-${location}`}>
              {location}
            </span>
          ))}
          {inferenceLocations.length > visibleLocations.length ? (
            <span className="family-variant-chip family-variant-chip-muted">+{inferenceLocations.length - visibleLocations.length} more</span>
          ) : null}
        </div>
      ) : null}
      {orderedBenchmarkWins.length ? (
        <>
          <div className="family-variant-subtitle">Family benchmark rows supplied by this variant</div>
          <div className="family-variant-chip-row">
            {visibleBenchmarkWins.map((benchmarkId) => (
              <span className="family-variant-chip" key={`${variant.id}-${benchmarkId}`}>
                {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
              </span>
            ))}
            {orderedBenchmarkWins.length > visibleBenchmarkWins.length ? (
              <span className="family-variant-chip family-variant-chip-muted">
                +{orderedBenchmarkWins.length - visibleBenchmarkWins.length} more
              </span>
            ) : null}
          </div>
        </>
      ) : (
        <div className="family-variant-muted">
          This variant does not currently supply a benchmark-leading row in the family card.
        </div>
      )}
    </article>
  );
}

function InferenceDestinationCard({ destination, pricingReferenceLabel, pricingReferencePrefix = "Reference price" }) {
  const visibleRegions = sortInferenceRegions(destination.regions || []);
  const compactSummary = [destination.location_scope, ...(destination.deployment_modes || [])].filter(Boolean);
  const pricingNote = destination.pricing_note || destination.pricing_label || "Pricing reference unavailable";
  const pricingSummary = pricingReferenceLabel
    ? `${pricingReferencePrefix}: ${pricingReferenceLabel}`
    : `${pricingReferencePrefix} unavailable`;

  return (
    <article className="inference-card">
      <div className="inference-card-head">
        <div className="inference-title-block">
          <div className="inference-cloud">{destination.hyperscaler}</div>
          <div className="inference-title-row">
            <div className="inference-title">{destination.name}</div>
            <span className="tag tag-inference-scope">{destination.availability_scope}</span>
          </div>
        </div>
      </div>
      <div className="inference-copy">{destination.availability_note}</div>
      <div className="inference-summary-line">
        {compactSummary.map((item) => (
          <span key={`${destination.id}-${item}`} className="inference-summary-pill">
            {item}
          </span>
        ))}
      </div>
      <div className="inference-price">{pricingSummary}</div>
      {visibleRegions.length ? (
        <div className="inference-region-row">
          {visibleRegions.map((region) => (
            <span key={region} className="region-chip">
              {region}
            </span>
          ))}
        </div>
      ) : null}
      <div className="inference-foot">
        <span>{pricingNote}</span>
        <div className="inference-links">
          {(destination.sources || []).map((source) => (
            <a
              key={`${destination.id}-${source.label}`}
              className="inference-link"
              href={source.url}
              rel="noreferrer"
              target="_blank"
            >
              {source.label}
            </a>
          ))}
        </div>
      </div>
    </article>
  );
}

function waitForExportRender() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(resolve);
    });
  });
}

async function prepareExportDataForSnapshot({ activeTab, data }) {
  const sourceRunsByLogId = {};
  const sourceRunsByEntry = await Promise.all(
    (data.history || []).map(async (entry) => {
      const sourceRuns = await data.loadSourceRuns(entry.id);
      sourceRunsByLogId[entry.id] = sourceRuns;
      return sourceRuns;
    }),
  );

  if (activeTab === "history") {
    const sourceRuns = sourceRunsByEntry.flat();
    await Promise.all(sourceRuns.map((sourceRun) => data.loadRawSourceRecords(sourceRun.id)));
  }

  return { sourceRunsByLogId };
}

function Compare({
  benchmarks,
  benchmarksById,
  catalogMode,
  compareIds,
  compareQuery,
  compareSuggestions,
  exportMode,
  models,
  onAddToCompare,
  onCatalogModeChange,
  onCompareQueryChange,
  rankingByCatalogId,
  selectedUseCase,
}) {
  const [showSourceNotes, setShowSourceNotes] = useState(false);
  const showExpandedSourceNotes = exportMode || showSourceNotes;
  const selectedModels = models.filter((model) => compareIds.includes(model.id));
  const benchmarksWithData = benchmarks.filter((benchmark) =>
    selectedModels.some((model) => model.scores[benchmark.id]?.value != null),
  );
  const orderedBenchmarks = [...benchmarksWithData].sort((left, right) => compareBenchmarkSort(left, right, selectedUseCase));

  function winnerForBenchmark(benchmark) {
    const withData = selectedModels.filter((model) => model.scores[benchmark.id]?.value != null);
    if (withData.length < 2) {
      return null;
    }

    return withData.reduce((best, model) => {
      const current = model.scores[benchmark.id].value;
      const bestValue = best.scores[benchmark.id].value;
      return benchmark.higher_is_better ? (current > bestValue ? model : best) : current < bestValue ? model : best;
    });
  }

  const winCounts = selectedModels.reduce((acc, model) => ({ ...acc, [model.id]: 0 }), {});
  benchmarksWithData.forEach((benchmark) => {
    const winner = winnerForBenchmark(benchmark);
    if (winner) {
      winCounts[winner.id] += 1;
    }
  });
  const hasLensMetrics = Boolean(selectedUseCase) && selectedModels.some((model) => rankingByCatalogId[model.id]);
  const commonCoverageCount = benchmarksWithData.filter((benchmark) =>
    selectedModels.every((model) => model.scores[benchmark.id]?.value != null),
  ).length;
  const disagreementCount = benchmarksWithData.filter((benchmark) => {
    const values = selectedModels
      .map((model) => model.scores[benchmark.id]?.value)
      .filter((value) => value != null)
      .map((value) => Number(value));
    return new Set(values).size > 1;
  }).length;
  const leadingModelId = hasLensMetrics
    ? selectedModels
        .filter((model) => rankingByCatalogId[model.id])
        .sort((left, right) => rankingByCatalogId[right.id].score - rankingByCatalogId[left.id].score)[0]?.id
    : selectedModels
        .slice()
        .sort((left, right) => (winCounts[right.id] || 0) - (winCounts[left.id] || 0))[0]?.id;

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Compare Models</h2>
          <p>
            Side-by-side benchmark comparison. Add models from the Model Browser or search below.
            {catalogMode === "family" ? " Family mode uses the best available underlying evidence per benchmark after canonical grouping." : ""}
          </p>
        </div>
        <ViewModeToggle mode={catalogMode} onChange={onCatalogModeChange} />
      </div>

      <div className="panel">
        <div className="panel-head">
          {selectedModels.length === 0 ? "Add models to compare" : `Comparing ${selectedModels.length} model${selectedModels.length > 1 ? "s" : ""}`}
        </div>
        <div className="compare-pills">
          {selectedModels.length ? (
            selectedModels.map((model) => (
              <span key={model.id} className="compare-pill">
                <span>{model.name}</span>
                <button aria-label={`Remove ${model.name} from compare`} onClick={() => onAddToCompare(model.id)} type="button">
                  ×
                </button>
              </span>
            ))
          ) : (
            <span className="hint">No models selected yet</span>
          )}
        </div>
        <label className="field">
          <span className="field-label">Search to add a model</span>
          <input
            className="input"
            onChange={(event) => onCompareQueryChange(event.target.value)}
            placeholder="Search to add a model…"
            type="text"
            value={compareQuery}
          />
        </label>
        {compareQuery && compareSuggestions.length ? (
          <div className="suggestions">
            {compareSuggestions.map((model) => (
              <button
                key={model.id}
                className="suggestion"
                onClick={() => {
                  onAddToCompare(model.id);
                  onCompareQueryChange("");
                }}
                type="button"
              >
                <span>{model.name}</span>
                <ProviderBadge
                  countryCode={model.provider_country_code}
                  countryFlag={model.provider_country_flag}
                  countryName={model.provider_country_name}
                  provider={model.provider}
                />
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {selectedModels.length >= 2 && benchmarksWithData.length ? (
        <>
          <div className="compare-insights panel">
            <div className="compare-insights-head">
              <div className="panel-head">Comparison snapshot</div>
              <button
                aria-pressed={showExpandedSourceNotes}
                className="btn btn-ghost btn-inline"
                onClick={() => setShowSourceNotes((value) => !value)}
                type="button"
              >
                {showExpandedSourceNotes ? "Hide source notes" : "Show source notes"}
              </button>
            </div>
            <div className="compare-insights-grid">
              <div className="finder-metric">
                <strong>{commonCoverageCount}</strong>
                <span>shared benchmarks</span>
              </div>
              <div className="finder-metric">
                <strong>{disagreementCount}</strong>
                <span>benchmarks with disagreement</span>
              </div>
              <div className="finder-metric">
                <strong>{selectedUseCase ? selectedUseCase.label : "General"}</strong>
                <span>{hasLensMetrics ? "weighted lens in focus" : "benchmark-by-benchmark comparison"}</span>
              </div>
            </div>
          </div>

          <div className="compare-summary" style={{ gridTemplateColumns: `repeat(${selectedModels.length}, minmax(0, 1fr))` }}>
            {selectedModels.map((model) => (
              <div key={model.id} className={leadingModelId === model.id ? "summary summary-top" : "summary"}>
                <div className="summary-title">{model.name}</div>
                <ProviderBadge
                  countryCode={model.provider_country_code}
                  countryFlag={model.provider_country_flag}
                  countryName={model.provider_country_name}
                  provider={model.provider}
                />
                {model.family && model.family.member_count > 1 ? <div className="summary-foot">{model.family.member_count} models</div> : null}
                <div className="summary-score">
                  <span>
                    {hasLensMetrics && rankingByCatalogId[model.id]
                      ? Math.round(rankingByCatalogId[model.id].score)
                      : winCounts[model.id]}
                  </span>
                  <small>{hasLensMetrics ? "lens score" : "wins"}</small>
                </div>
                <div className="summary-foot">
                  {hasLensMetrics && rankingByCatalogId[model.id]
                    ? `#${rankingByCatalogId[model.id].rank} in ${selectedUseCase.label}`
                    : `of ${benchmarksWithData.length} benchmarks`}
                </div>
                <div className="summary-foot">
                  {Math.round(
                    (benchmarksWithData.filter((benchmark) => model.scores[benchmark.id]?.value != null).length /
                      Math.max(benchmarksWithData.length, 1)) *
                      100,
                  )}
                  % comparison coverage
                </div>
                {getPreferredOpenRouterLabel(model, selectedUseCase) ? (
                  <div className="summary-foot">
                    {getPreferredOpenRouterLabel(model, selectedUseCase)}
                    {getOpenRouterPopularityDetail(model, selectedUseCase)
                      ? ` · ${getOpenRouterPopularityDetail(model, selectedUseCase)}`
                      : ""}
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          <div className="compare-matrix">
            {orderedBenchmarks.map((benchmark) => {
              const winner = winnerForBenchmark(benchmark);
              const weight = selectedUseCase?.weights?.[benchmark.id];
              return (
                <article key={benchmark.id} className="compare-row">
                  <div className="compare-benchmark">
                    <a href={benchmark.url} rel="noreferrer" target="_blank">
                      {benchmark.short}
                    </a>
                    <div className="metric">{benchmark.metric}</div>
                    {weight ? <div className="compare-weight">{Math.round(weight * 100)}% lens weight</div> : null}
                  </div>
                  <div className="compare-cells" style={{ gridTemplateColumns: `repeat(${selectedModels.length}, minmax(0, 1fr))` }}>
                    {selectedModels.map((model) => {
                      const score = model.scores[benchmark.id];
                      const isWinnerModel = winner?.id === model.id;
                      return (
                        <div key={model.id} className={isWinnerModel ? "compare-cell compare-cell-winner" : "compare-cell"}>
                          <div className="cell-model">{model.name}</div>
                          {score?.value != null ? (
                            <>
                              <span className={isWinnerModel ? "score score-winner" : "score"}>
                                <SourceBadge score={score} />
                                {isWinnerModel ? "★ " : ""}
                                {formatBenchmarkValue(benchmarksById[benchmark.id], score.value)}
                              </span>
                              {score.family_variant_name ? <span className="cell-variant">via {score.family_variant_name}</span> : null}
                              {showExpandedSourceNotes && benchmark.id === "terminal_bench" && score.notes ? (
                                <span className="cell-note">{score.notes}</span>
                              ) : null}
                            </>
                          ) : (
                            <span className="cell-empty">No data</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </article>
              );
            })}
          </div>
        </>
      ) : (
        <EmptyState message="Add at least 2 models to compare." />
      )}
    </section>
  );
}

function History({
  exportMode,
  expandedHistoryId,
  history,
  loadRawSourceRecords,
  marketSnapshots,
  marketSnapshotsError,
  marketSnapshotsLoading,
  onToggleEntry,
  rawRecordsBySourceRunId,
  rawRecordsLoadingBySourceRunId,
  sourceRunsByLogId,
  sourceRunsLoadingByLogId,
  updateState,
}) {
  const [expandedSourceRunIds, setExpandedSourceRunIds] = useState({});
  const [marketScope, setMarketScope] = useState("global");
  const [selectedMarketSnapshotDate, setSelectedMarketSnapshotDate] = useState("");
  const entries = [...history].sort((left, right) => String(right.started_at).localeCompare(String(left.started_at)));
  const marketScopeOptions = useMemo(
    () =>
      [
        {
          id: "global",
          label: "Global weekly rankings",
          rows: marketSnapshots.filter((row) => row.scope === "global"),
        },
        {
          id: "programming",
          label: "Programming usage",
          rows: marketSnapshots.filter((row) => row.scope === "category" && row.category_slug === "programming"),
        },
      ].filter((option) => option.rows.length),
    [marketSnapshots],
  );
  const marketRowsForScope = useMemo(
    () => marketScopeOptions.find((option) => option.id === marketScope)?.rows || [],
    [marketScope, marketScopeOptions],
  );
  const marketSnapshotDates = useMemo(
    () =>
      Array.from(new Set(marketRowsForScope.map((row) => row.snapshot_date)))
        .sort((left, right) => String(right).localeCompare(String(left)))
        .slice(0, 8),
    [marketRowsForScope],
  );
  const marketRowsForDate = useMemo(
    () =>
      marketRowsForScope
        .filter((row) => row.snapshot_date === selectedMarketSnapshotDate)
        .sort((left, right) => left.rank - right.rank || String(left.model_name).localeCompare(String(right.model_name))),
    [marketRowsForScope, selectedMarketSnapshotDate],
  );
  const marketLeader = marketRowsForDate[0] || null;
  const marketTotalTokens = marketRowsForDate.reduce((sum, row) => sum + (Number(row.total_tokens) || 0), 0);

  function toggleSourceRun(sourceRunId) {
    setExpandedSourceRunIds((current) => {
      const isExpanded = Boolean(current[sourceRunId]);
      if (!isExpanded && !rawRecordsBySourceRunId[sourceRunId]?.length) {
        loadRawSourceRecords(sourceRunId);
      }
      return { ...current, [sourceRunId]: !isExpanded };
    });
  }

  useEffect(() => {
    if (!marketScopeOptions.length) {
      if (marketScope !== "global") {
        setMarketScope("global");
      }
      return;
    }

    if (!marketScopeOptions.some((option) => option.id === marketScope)) {
      setMarketScope(marketScopeOptions[0].id);
    }
  }, [marketScope, marketScopeOptions]);

  useEffect(() => {
    if (!marketSnapshotDates.length) {
      if (selectedMarketSnapshotDate) {
        setSelectedMarketSnapshotDate("");
      }
      return;
    }

    if (!marketSnapshotDates.includes(selectedMarketSnapshotDate)) {
      setSelectedMarketSnapshotDate(marketSnapshotDates[0]);
    }
  }, [marketSnapshotDates, selectedMarketSnapshotDate]);

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Update History</h2>
          <p>A log of each time this dashboard&apos;s data was refreshed.</p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">How to trigger an update</div>
        <p className="panel-copy">
          Click <strong>Update Now</strong> in the header. The frontend will trigger the backend update job, poll for
          completion, and refresh the loaded models and benchmarks.
        </p>
      </div>

      <div className="panel market-history-panel">
        <div className="market-history-header">
          <div>
            <div className="panel-head">OpenRouter market snapshots</div>
            <p className="panel-copy">
              Stored popularity snapshots from OpenRouter. These are separate from benchmark scores and show adoption,
              not capability.
            </p>
          </div>
          {marketScopeOptions.length ? (
            <div className="market-scope-switch" role="tablist" aria-label="Market snapshot scope">
              {marketScopeOptions.map((option) => (
                <button
                  key={option.id}
                  aria-selected={marketScope === option.id}
                  className={marketScope === option.id ? "market-scope-btn market-scope-btn-active" : "market-scope-btn"}
                  onClick={() => setMarketScope(option.id)}
                  role="tab"
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {marketSnapshotsLoading ? <div className="history-sources-empty">Loading market snapshots...</div> : null}
        {marketSnapshotsError ? <div className="history-errors">{marketSnapshotsError}</div> : null}
        {!marketSnapshotsLoading && !marketSnapshotsError && !marketScopeOptions.length ? (
          <div className="history-sources-empty">No market snapshots stored yet. Run an update or reload the backend to ingest them.</div>
        ) : null}

        {!marketSnapshotsLoading && !marketSnapshotsError && marketRowsForDate.length ? (
          <>
            <div className="market-snapshot-metrics">
              <div className="finder-metric">
                <strong>{formatSnapshotDateLabel(selectedMarketSnapshotDate)}</strong>
                <span>snapshot date</span>
              </div>
              <div className="finder-metric">
                <strong>{marketRowsForDate.length}</strong>
                <span>models stored</span>
              </div>
              <div className="finder-metric">
                <strong>{marketLeader ? marketLeader.model_name : "—"}</strong>
                <span>top model</span>
              </div>
              <div className="finder-metric">
                <strong>{formatTokenVolume(marketTotalTokens)}</strong>
                <span>{marketScope === "programming" ? "programming tokens" : "weekly tokens"}</span>
              </div>
            </div>

            <div className="market-date-chips" role="tablist" aria-label="Market snapshot dates">
              {marketSnapshotDates.map((snapshotDate) => (
                <button
                  key={snapshotDate}
                  aria-selected={selectedMarketSnapshotDate === snapshotDate}
                  className={selectedMarketSnapshotDate === snapshotDate ? "market-date-chip market-date-chip-active" : "market-date-chip"}
                  onClick={() => setSelectedMarketSnapshotDate(snapshotDate)}
                  role="tab"
                  type="button"
                >
                  {formatSnapshotDateLabel(snapshotDate)}
                </button>
              ))}
            </div>

            <div className="market-table-wrap">
              <table className="market-table">
                <thead>
                  <tr>
                    <th scope="col">Rank</th>
                    <th scope="col">Model</th>
                    <th scope="col">Provider</th>
                    <th scope="col">Tokens</th>
                    <th scope="col">{marketScope === "programming" ? "Volume" : "Share"}</th>
                    <th scope="col">{marketScope === "programming" ? "Requests" : "Change"}</th>
                  </tr>
                </thead>
                <tbody>
                  {marketRowsForDate.map((row) => (
                    <tr key={`${row.scope}-${row.category_slug}-${row.snapshot_date}-${row.model_id}`}>
                      <td>{row.rank}</td>
                      <td>
                        <div className="market-model-cell">
                          <strong>{row.model_name}</strong>
                          {row.source_url ? (
                            <a href={row.source_url} rel="noreferrer" target="_blank">
                              Source
                            </a>
                          ) : null}
                        </div>
                      </td>
                      <td>{row.provider}</td>
                      <td>{formatTokenVolume(row.total_tokens)}</td>
                      <td>
                        {marketScope === "programming"
                          ? row.volume != null
                            ? formatScore(row.volume)
                            : "—"
                          : row.share != null
                            ? formatPercent(row.share)
                            : "—"}
                      </td>
                      <td>
                        {marketScope === "programming"
                          ? row.request_count != null
                            ? formatScore(row.request_count)
                            : "—"
                          : row.change_ratio != null
                            ? formatSignedPercent(row.change_ratio)
                            : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>

      <div className="history-list">
        {entries.length ? (
          entries.map((entry) => {
            const sourceRuns = sourceRunsByLogId[entry.id] || [];
            const failedSources = sourceRuns.filter((sourceRun) => sourceRun.status === "failed").length;
            const entryExpanded = exportMode || expandedHistoryId === entry.id;
            const auditSummary = parseAuditSummaryPayload(entry.audit_summary?.summary_json);
            const newModelCount = Number(auditSummary.new_model_count || 0);
            const familyDeltaCandidateCount = Number(auditSummary.family_delta_candidate_count || 0);

            return (
              <article key={entry.id} className="history-item history-entry">
                <button
                  aria-expanded={entryExpanded}
                  className="history-toggle"
                  onClick={() => onToggleEntry(entry.id)}
                  type="button"
                >
                  <div className="history-dot" />
                  <div className="history-main">
                    <div className="history-date">{formatDate(entry.started_at)}</div>
                    <div className="history-note">
                      Status: {entry.status} · {entry.scores_added} scores added · {entry.scores_updated} scores updated
                    </div>
                    {newModelCount ? (
                      <div className="history-note">
                        {newModelCount} new model{newModelCount === 1 ? "" : "s"} discovered
                        {familyDeltaCandidateCount ? ` · ${familyDeltaCandidateCount} in already-approved families` : ""}
                      </div>
                    ) : null}
                    {sourceRuns.length ? (
                      <div className="history-source-summary">
                        {sourceRuns.length} source runs · {failedSources} failed ·{" "}
                        {sourceRuns.reduce((total, sourceRun) => total + (sourceRun.records_found || 0), 0)} raw records
                      </div>
                    ) : null}
                    {Array.isArray(entry.errors) && entry.errors.length ? (
                      <div className="history-errors">{entry.errors.map((error) => error.error_message || "Unknown error").join("; ")}</div>
                    ) : null}
                  </div>
                  <span className="history-chevron">{entryExpanded ? "▲" : "▼"}</span>
                </button>
                {entryExpanded ? (
                  <div className="history-sources">
                    {sourceRunsLoadingByLogId[entry.id] ? (
                      <div className="history-sources-empty">Loading source runs...</div>
                    ) : sourceRuns.length ? (
                      sourceRuns.map((sourceRun) => {
                        const sourceRunExpanded = exportMode || Boolean(expandedSourceRunIds[sourceRun.id]);

                        return (
                          <div key={sourceRun.id} className="history-source-card">
                            <button
                              aria-expanded={sourceRunExpanded}
                              className="history-source-row"
                              onClick={() => toggleSourceRun(sourceRun.id)}
                              type="button"
                            >
                              <div>
                                <div className="history-source-name">{sourceRun.source_name}</div>
                                <div className="history-source-meta">
                                  {sourceRun.benchmark_id || "n/a"} · {sourceRun.records_found} raw records
                                </div>
                              </div>
                              <div className="history-source-status">
                                <span className={sourceRun.status === "completed" ? "pill pill-good" : sourceRun.status === "failed" ? "pill pill-bad" : "pill"}>
                                  {sourceRun.status}
                                </span>
                                <span className="history-source-chevron">{sourceRunExpanded ? "▲" : "▼"}</span>
                                {sourceRun.error_message ? <div className="history-source-error">{sourceRun.error_message}</div> : null}
                              </div>
                            </button>
                            {sourceRunExpanded ? (
                              <HistorySourceRunDetails
                                rawRecords={rawRecordsBySourceRunId[sourceRun.id] || []}
                                rawRecordsLoading={rawRecordsLoadingBySourceRunId[sourceRun.id]}
                                sourceRun={sourceRun}
                              />
                            ) : null}
                          </div>
                        );
                      })
                    ) : (
                      <div className="history-sources-empty">No source-run detail stored for this update.</div>
                    )}
                  </div>
                ) : null}
              </article>
            );
          })
        ) : (
          <EmptyState message="No update logs yet. Trigger an update to populate history." />
        )}
      </div>

      <div className="note">
        <strong>Why manual updates?</strong> Automatic scraping of benchmark leaderboards is unreliable, so the backend
        keeps a human-triggered update flow and stores every run in the database.
      </div>

      {updateState.errors?.length ? (
        <div className="panel">
          <div className="panel-head">Latest update errors</div>
          <div className="history-errors">
            {updateState.errors.map((error) => error.error_message || "Unknown error").join("; ")}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function HistorySourceRunDetails({ rawRecords, rawRecordsLoading, sourceRun }) {
  if (rawRecordsLoading) {
    return <div className="history-raw-empty">Loading raw-record detail...</div>;
  }

  if (!rawRecords.length) {
    return <div className="history-raw-empty">No raw-record detail stored for this source run.</div>;
  }

  const resolutionCounts = rawRecords.reduce((acc, row) => {
    const key = row.resolution_status || "unresolved";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const skippedAggregate = rawRecords.filter((row) => row.resolution_status === "skipped_aggregate").slice(0, 5);
  const unresolved = rawRecords.filter((row) => row.resolution_status === "unresolved").slice(0, 5);

  return (
    <div className="history-raw-panel">
      <div className="history-raw-summary">
        <span className="pill">resolved {resolutionCounts.resolved || 0}</span>
        <span className="pill">skipped aggregate {resolutionCounts.skipped_aggregate || 0}</span>
        <span className="pill">unresolved {resolutionCounts.unresolved || 0}</span>
      </div>
      {sourceRun.source_name === "terminal_bench" ? (
        <div className="history-raw-note">
          Terminal-Bench keeps multi-model aggregate submissions as raw provenance and excludes them from the model catalog.
        </div>
      ) : null}
      {skippedAggregate.length ? (
        <div className="history-raw-list">
          <div className="detail-label">Aggregate provenance kept raw</div>
          {skippedAggregate.map((row) => (
            <div key={row.id} className="history-raw-row">
              <span className="history-raw-name">{row.raw_model_name}</span>
              <span className="history-raw-meta">{row.raw_value || "n/a"}</span>
            </div>
          ))}
        </div>
      ) : null}
      {unresolved.length ? (
        <div className="history-raw-list">
          <div className="detail-label">Still unresolved</div>
          {unresolved.map((row) => (
            <div key={row.id} className="history-raw-row">
              <span className="history-raw-name">{row.raw_model_name}</span>
              <span className="history-raw-meta">{row.raw_value || "n/a"}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AdminPanel({
  benchmarks,
  models,
  onApplyInferenceRouteApprovalBulk,
  onApplyFamilyApprovalBulk,
  onRefreshSelectedUseCaseRankings,
  onSaveInternalBenchmarkScore,
  onSaveInternalWeight,
  onSaveModelApproval,
  onSaveModelDuplicateMerge,
  onSaveModelIdentityCuration,
  onSaveProvider,
  providers,
  selectedUseCaseId,
  useCases,
}) {
  const internalBenchmark = useMemo(
    () => benchmarks.find((benchmark) => benchmark.id === INTERNAL_VIEW_BENCHMARK_ID) || null,
    [benchmarks],
  );
  const [providerDrafts, setProviderDrafts] = useState({});
  const [modelDrafts, setModelDrafts] = useState({});
  const [modelCurationDrafts, setModelCurationDrafts] = useState({});
  const [internalWeightDrafts, setInternalWeightDrafts] = useState({});
  const [internalScoreDrafts, setInternalScoreDrafts] = useState({});
  const [adminFocus, setAdminFocus] = useState("all");
  const [approvalUseCaseId, setApprovalUseCaseId] = useState(selectedUseCaseId || useCases[0]?.id || "");
  const [bulkApprovalUseCaseIds, setBulkApprovalUseCaseIds] = useState(
    selectedUseCaseId ? [selectedUseCaseId] : (useCases[0]?.id ? [useCases[0].id] : []),
  );
  const [familyApprovalScope, setFamilyApprovalScope] = useState(DEFAULT_FAMILY_APPROVAL_SCOPE);
  const [approvalFamilyFilters, setApprovalFamilyFilters] = useState([]);
  const [visibleApprovalFamilyCount, setVisibleApprovalFamilyCount] = useState(10);
  const [approvalOriginFilter, setApprovalOriginFilter] = useState(DEFAULT_ORIGIN_FILTER);
  const [approvalRecommendationFilter, setApprovalRecommendationFilter] = useState(DEFAULT_RECOMMENDATION_FILTER);
  const [approvalHyperscalerFilter, setApprovalHyperscalerFilter] = useState(DEFAULT_HYPERSCALER_FILTER);
  const [approvalInferenceProviderFilter, setApprovalInferenceProviderFilter] = useState(DEFAULT_INFERENCE_PROVIDER_FILTER);
  const [approvalInferenceLocationFilter, setApprovalInferenceLocationFilter] = useState(DEFAULT_INFERENCE_LOCATION_FILTER);
  const [reviewSignalFilter, setReviewSignalFilter] = useState(DEFAULT_REVIEW_SIGNAL_FILTER);
  const [providerSearch, setProviderSearch] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [internalScoreSearch, setInternalScoreSearch] = useState("");
  const [providerChangedOnly, setProviderChangedOnly] = useState(false);
  const [modelApprovalFilter, setModelApprovalFilter] = useState("all");
  const [internalWeightChangedOnly, setInternalWeightChangedOnly] = useState(false);
  const [internalScoreFilter, setInternalScoreFilter] = useState("all");
  const [providerSavingId, setProviderSavingId] = useState("");
  const [modelSavingId, setModelSavingId] = useState("");
  const [modelCurationSavingId, setModelCurationSavingId] = useState("");
  const [internalWeightSavingId, setInternalWeightSavingId] = useState("");
  const [internalScoreSavingId, setInternalScoreSavingId] = useState("");
  const [providerBulkSaving, setProviderBulkSaving] = useState(false);
  const [modelBulkSaving, setModelBulkSaving] = useState(false);
  const [internalWeightBulkSaving, setInternalWeightBulkSaving] = useState(false);
  const [internalScoreBulkSaving, setInternalScoreBulkSaving] = useState(false);
  const [internalWeightBulkText, setInternalWeightBulkText] = useState("");
  const [internalWeightBulkResult, setInternalWeightBulkResult] = useState(null);
  const [internalScoreBulkText, setInternalScoreBulkText] = useState("");
  const [internalScoreBulkResult, setInternalScoreBulkResult] = useState(null);
  const [familyDeltaNotes, setFamilyDeltaNotes] = useState("");
  const [familyDeltaSaving, setFamilyDeltaSaving] = useState(false);
  const [bulkInferenceRouteApproval, setBulkInferenceRouteApproval] = useState(true);
  const [bulkInferenceRouteNotes, setBulkInferenceRouteNotes] = useState("");
  const [bulkInferenceRouteSaving, setBulkInferenceRouteSaving] = useState(false);
  const [bulkRecommendationStatus, setBulkRecommendationStatus] = useState("unrated");
  const [bulkRecommendationNotes, setBulkRecommendationNotes] = useState("");
  const [message, setMessage] = useState("");

  const deferredProviderSearch = useDeferredValue(providerSearch);
  const deferredModelSearch = useDeferredValue(modelSearch);
  const deferredInternalScoreSearch = useDeferredValue(internalScoreSearch);
  const approvalUseCase = useMemo(
    () => useCases.find((useCase) => useCase.id === approvalUseCaseId) || null,
    [approvalUseCaseId, useCases],
  );

  useEffect(() => {
    setProviderDrafts((current) =>
      Object.fromEntries(
        providers.map((provider) => [provider.id, current[provider.id] || createProviderDraft(provider)]),
      ),
    );
  }, [providers]);

  useEffect(() => {
    if (!approvalUseCaseId) {
      return;
    }
    setModelDrafts((current) => {
      const next = { ...current };
      models.forEach((model) => {
        const draftKey = buildModelApprovalDraftKey(model.id, approvalUseCaseId);
        next[draftKey] = next[draftKey] || createModelDraft(model, approvalUseCaseId);
      });
      return next;
    });
  }, [approvalUseCaseId, models]);

  useEffect(() => {
    if (approvalUseCaseId && useCases.some((useCase) => useCase.id === approvalUseCaseId)) {
      return;
    }
    setApprovalUseCaseId(selectedUseCaseId && useCases.some((useCase) => useCase.id === selectedUseCaseId) ? selectedUseCaseId : (useCases[0]?.id || ""));
  }, [approvalUseCaseId, selectedUseCaseId, useCases]);

  useEffect(() => {
    const validIds = new Set(useCases.map((useCase) => useCase.id));
    setBulkApprovalUseCaseIds((current) => {
      const filtered = current.filter((useCaseId) => validIds.has(useCaseId));
      if (filtered.length) {
        return filtered;
      }
      if (selectedUseCaseId && validIds.has(selectedUseCaseId)) {
        return [selectedUseCaseId];
      }
      if (approvalUseCaseId && validIds.has(approvalUseCaseId)) {
        return [approvalUseCaseId];
      }
      return useCases[0]?.id ? [useCases[0].id] : [];
    });
  }, [approvalUseCaseId, selectedUseCaseId, useCases]);

  useEffect(() => {
    setInternalWeightDrafts((current) =>
      Object.fromEntries(useCases.map((useCase) => [useCase.id, current[useCase.id] || createInternalWeightDraft(useCase)])),
    );
  }, [useCases]);

  useEffect(() => {
    setInternalScoreDrafts((current) =>
      Object.fromEntries(models.map((model) => [model.id, current[model.id] || createInternalScoreDraft(model)])),
    );
  }, [models]);

  const filteredProviders = useMemo(() => {
    const search = deferredProviderSearch.toLowerCase().trim();
    return [...providers]
      .filter((provider) => {
        if (providerChangedOnly && !isProviderDirty(provider)) {
          return false;
        }
        if (!search) {
          return true;
        }
        return [
          provider.name,
          provider.country_code,
          provider.country_name,
          summarizeOriginCountries(provider.origin_countries),
          provider.origin_basis,
          provider.source_url,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(search);
      })
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [deferredProviderSearch, providerChangedOnly, providerDrafts, providers]);

  const approvalReviewSignals = useMemo(
    () => buildApprovalReviewSignals(models, approvalUseCaseId),
    [approvalUseCaseId, models],
  );
  const allApprovalFamilies = useMemo(() => buildApprovalFamilyOptions(models), [models]);

  useEffect(() => {
    const validFamilyIds = new Set(allApprovalFamilies.map((family) => family.id));
    setApprovalFamilyFilters((current) => current.filter((familyId) => validFamilyIds.has(familyId)));
  }, [allApprovalFamilies]);

  const selectedApprovalFamilyIds = useMemo(() => new Set(approvalFamilyFilters), [approvalFamilyFilters]);

  function matchesApprovalModelFilters(model, { includeFamilyFilter = true } = {}) {
    const currentApproval = getModelApprovalRecord(model, approvalUseCaseId);
    const isDirty = isModelDirty(model);
    const reviewSignal = approvalReviewSignals[model.id] || null;
    const search = deferredModelSearch.toLowerCase().trim();

    if (modelApprovalFilter === "changed" && !isDirty) {
      return false;
    }
    if (modelApprovalFilter === "pending" && currentApproval?.approved_for_use) {
      return false;
    }
    if (modelApprovalFilter === "approved" && !currentApproval?.approved_for_use) {
      return false;
    }
    if (includeFamilyFilter && selectedApprovalFamilyIds.size && !selectedApprovalFamilyIds.has(model.family_id)) {
      return false;
    }
    if (
      approvalOriginFilter !== DEFAULT_ORIGIN_FILTER &&
      !getModelOriginCountries(model).includes(approvalOriginFilter)
    ) {
      return false;
    }
    if (
      approvalRecommendationFilter !== DEFAULT_RECOMMENDATION_FILTER &&
      !matchesRecommendationFilter(model, approvalUseCaseId, approvalRecommendationFilter)
    ) {
      return false;
    }
    if (
      approvalHyperscalerFilter !== DEFAULT_HYPERSCALER_FILTER &&
      !getModelHyperscalers(model).includes(approvalHyperscalerFilter)
    ) {
      return false;
    }
    if (
      approvalInferenceProviderFilter !== DEFAULT_INFERENCE_PROVIDER_FILTER &&
      !getModelInferenceProviderIds(model).includes(approvalInferenceProviderFilter)
    ) {
      return false;
    }
    if (
      approvalInferenceLocationFilter !== DEFAULT_INFERENCE_LOCATION_FILTER &&
      !getModelInferenceCountries(model).includes(approvalInferenceLocationFilter)
    ) {
      return false;
    }
    if (reviewSignalFilter === "unrated" && reviewSignal?.isReviewed !== false) {
      return false;
    }
    if (reviewSignalFilter === "needs_review" && !reviewSignal?.needsReview) {
      return false;
    }
    if (reviewSignalFilter === "suggested" && reviewSignal?.status !== "suggested_approve") {
      return false;
    }
    if (reviewSignalFilter === "new_only" && reviewSignal?.status !== "new_model") {
      return false;
    }
    if (reviewSignalFilter === "reviewed_no" && reviewSignal?.status !== "reviewed_not_approved") {
      return false;
    }
    if (!search) {
      return true;
    }
    return [
      model.name,
      model.family_name,
      model.provider,
      model.provider_country_name,
      getModelOriginCountries(model).join(" "),
      currentApproval?.approval_notes,
      currentApproval?.recommendation_notes,
      formatRecommendationStatusLabel(currentApproval?.recommendation_status),
      reviewSignal?.summary,
      getModelHyperscalers(model).join(" "),
      getModelInferenceProviders(model).map((provider) => provider.label).join(" "),
      getModelInferenceCountries(model).join(" "),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(search);
  }

  const approvalFamilyCandidateModels = useMemo(
    () => models.filter((model) => matchesApprovalModelFilters(model, { includeFamilyFilter: false })),
    [
      approvalHyperscalerFilter,
      approvalInferenceLocationFilter,
      approvalInferenceProviderFilter,
      approvalOriginFilter,
      approvalRecommendationFilter,
      approvalReviewSignals,
      approvalUseCaseId,
      deferredModelSearch,
      modelApprovalFilter,
      modelDrafts,
      models,
      reviewSignalFilter,
    ],
  );
  const filteredApprovalFamilies = useMemo(
    () => buildApprovalFamilyOptions(approvalFamilyCandidateModels),
    [approvalFamilyCandidateModels],
  );
  const filteredApprovalFamilyMap = useMemo(
    () => new Map(filteredApprovalFamilies.map((family) => [family.id, family])),
    [filteredApprovalFamilies],
  );
  const allApprovalFamilyMap = useMemo(
    () => new Map(allApprovalFamilies.map((family) => [family.id, family])),
    [allApprovalFamilies],
  );
  const selectedApprovalFamilies = useMemo(
    () =>
      approvalFamilyFilters
        .map((familyId) => {
          const family = filteredApprovalFamilyMap.get(familyId) || allApprovalFamilyMap.get(familyId);
          if (!family) {
            return null;
          }
          return filteredApprovalFamilyMap.get(familyId)
            ? family
            : {
                ...family,
                count: 0,
              };
        })
        .filter(Boolean),
    [allApprovalFamilyMap, approvalFamilyFilters, filteredApprovalFamilyMap],
  );
  const visibleApprovalFamilies = useMemo(() => {
    const selectedIds = new Set(approvalFamilyFilters);
    const remainingFamilies = filteredApprovalFamilies.filter((family) => !selectedIds.has(family.id));
    const visibleRemainingCount = Math.max(0, visibleApprovalFamilyCount - selectedApprovalFamilies.length);
    return [...selectedApprovalFamilies, ...remainingFamilies.slice(0, visibleRemainingCount)];
  }, [approvalFamilyFilters, filteredApprovalFamilies, selectedApprovalFamilies, visibleApprovalFamilyCount]);
  const hasMoreApprovalFamilies = useMemo(() => {
    const hiddenCount = filteredApprovalFamilies.filter((family) => !approvalFamilyFilters.includes(family.id)).length;
    const visibleRemainingCount = Math.max(0, visibleApprovalFamilyCount - selectedApprovalFamilies.length);
    return hiddenCount > visibleRemainingCount;
  }, [approvalFamilyFilters, filteredApprovalFamilies, selectedApprovalFamilies, visibleApprovalFamilyCount]);

  const filteredModels = useMemo(() => {
    return [...models]
      .filter((model) => matchesApprovalModelFilters(model))
      .sort((left, right) => {
        const providerComparison = String(left.provider || "").localeCompare(String(right.provider || ""));
        if (providerComparison !== 0) {
          return providerComparison;
        }
        return String(left.name || "").localeCompare(String(right.name || ""));
      });
  }, [
    selectedApprovalFamilyIds,
    approvalOriginFilter,
    approvalRecommendationFilter,
    approvalHyperscalerFilter,
    approvalInferenceProviderFilter,
    approvalInferenceLocationFilter,
    approvalReviewSignals,
    approvalUseCaseId,
    deferredModelSearch,
    modelApprovalFilter,
    modelDrafts,
    models,
    reviewSignalFilter,
  ]);

  const filteredInternalScoreModels = useMemo(() => {
    const search = deferredInternalScoreSearch.toLowerCase().trim();
    return [...models]
      .filter((model) => {
        const hasScore = model.scores?.[INTERNAL_VIEW_BENCHMARK_ID]?.value != null;
        const isDirty = isInternalScoreDirty(model);
        if (internalScoreFilter === "changed" && !isDirty) {
          return false;
        }
        if (internalScoreFilter === "missing" && hasScore) {
          return false;
        }
        if (internalScoreFilter === "scored" && !hasScore) {
          return false;
        }
        if (!search) {
          return true;
        }
        return [
          model.name,
          model.provider,
          model.provider_country_name,
          internalScoreDrafts[model.id]?.notes,
          model.scores?.[INTERNAL_VIEW_BENCHMARK_ID]?.notes,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(search);
      })
      .sort((left, right) => {
        const providerComparison = String(left.provider || "").localeCompare(String(right.provider || ""));
        if (providerComparison !== 0) {
          return providerComparison;
        }
        return String(left.name || "").localeCompare(String(right.name || ""));
      });
  }, [deferredInternalScoreSearch, internalScoreDrafts, internalScoreFilter, models]);

  const approvalHyperscalers = useMemo(
    () => [
      DEFAULT_HYPERSCALER_FILTER,
      ...Array.from(new Set(models.flatMap((model) => getModelHyperscalers(model)))).sort((left, right) => left.localeCompare(right)),
    ],
    [models],
  );
  const approvalInferenceProviders = useMemo(() => {
    const providersById = new Map();
    models.forEach((model) => {
      getModelInferenceProviders(model).forEach((provider) => {
        if (
          approvalHyperscalerFilter !== DEFAULT_HYPERSCALER_FILTER &&
          provider.hyperscaler !== approvalHyperscalerFilter
        ) {
          return;
        }
        providersById.set(provider.id, provider);
      });
    });
    return Array.from(providersById.values()).sort((left, right) => {
      const hyperscalerComparison = String(left.hyperscaler || "").localeCompare(String(right.hyperscaler || ""));
      if (hyperscalerComparison !== 0) {
        return hyperscalerComparison;
      }
      return String(left.label || "").localeCompare(String(right.label || ""));
    });
  }, [approvalHyperscalerFilter, models]);
  const approvalOrigins = useMemo(
    () => [
      DEFAULT_ORIGIN_FILTER,
      ...Array.from(new Set(models.flatMap((model) => getModelOriginCountries(model)))).sort((left, right) => left.localeCompare(right)),
    ],
    [models],
  );
  const approvalInferenceLocations = useMemo(
    () => [
      DEFAULT_INFERENCE_LOCATION_FILTER,
      ...sortInferenceCountries(models.flatMap((model) => getModelInferenceCountries(model))),
    ],
    [models],
  );
  useEffect(() => {
    if (!approvalOrigins.includes(approvalOriginFilter)) {
      setApprovalOriginFilter(DEFAULT_ORIGIN_FILTER);
    }
  }, [approvalOriginFilter, approvalOrigins]);
  useEffect(() => {
    if (!approvalHyperscalers.includes(approvalHyperscalerFilter)) {
      setApprovalHyperscalerFilter(DEFAULT_HYPERSCALER_FILTER);
    }
  }, [approvalHyperscalerFilter, approvalHyperscalers]);
  useEffect(() => {
    if (
      approvalInferenceProviderFilter !== DEFAULT_INFERENCE_PROVIDER_FILTER &&
      !approvalInferenceProviders.some((provider) => provider.id === approvalInferenceProviderFilter)
    ) {
      setApprovalInferenceProviderFilter(DEFAULT_INFERENCE_PROVIDER_FILTER);
    }
  }, [approvalInferenceProviderFilter, approvalInferenceProviders]);
  useEffect(() => {
    if (!approvalInferenceLocations.includes(approvalInferenceLocationFilter)) {
      setApprovalInferenceLocationFilter(DEFAULT_INFERENCE_LOCATION_FILTER);
    }
  }, [approvalInferenceLocationFilter, approvalInferenceLocations]);
  const pendingReviewCount = useMemo(
    () => Object.values(approvalReviewSignals).filter((signal) => signal?.needsReview).length,
    [approvalReviewSignals],
  );
  const suggestedReviewCount = useMemo(
    () => Object.values(approvalReviewSignals).filter((signal) => signal?.status === "suggested_approve").length,
    [approvalReviewSignals],
  );
  const selectedBulkUseCases = useMemo(
    () => useCases.filter((useCase) => bulkApprovalUseCaseIds.includes(useCase.id)),
    [bulkApprovalUseCaseIds, useCases],
  );
  const selectedInferenceProvider = useMemo(
    () => approvalInferenceProviders.find((provider) => provider.id === approvalInferenceProviderFilter) || null,
    [approvalInferenceProviderFilter, approvalInferenceProviders],
  );
  const selectedInferenceRouteLocationKey = useMemo(
    () => buildInferenceLocationKey(approvalInferenceLocationFilter),
    [approvalInferenceLocationFilter],
  );
  const hasSelectedInferenceRoute = Boolean(
    approvalUseCaseId &&
      approvalInferenceProviderFilter !== DEFAULT_INFERENCE_PROVIDER_FILTER &&
      approvalInferenceLocationFilter !== DEFAULT_INFERENCE_LOCATION_FILTER &&
      selectedInferenceRouteLocationKey,
  );
  const bulkApprovalPreview = useMemo(() => {
    if (!selectedApprovalFamilies.length) {
      return [];
    }
    return selectedBulkUseCases.map((useCase) => {
      const reviewSignals = buildApprovalReviewSignals(models, useCase.id);
      const { candidateCount, referenceApprovedCount } = selectedApprovalFamilies.reduce(
        (totals, family) => {
          const familyModels = models.filter((model) => model.family_id === family.id);
          totals.referenceApprovedCount += familyModels.filter((model) => isModelApprovedForUseCase(model, useCase.id)).length;
          totals.candidateCount += familyModels.filter((model) => {
            if (familyApprovalScope === "delta") {
              return Boolean(reviewSignals[model.id]?.canApplyFamilyDelta);
            }
            return !isModelApprovedForUseCase(model, useCase.id);
          }).length;
          return totals;
        },
        { candidateCount: 0, referenceApprovedCount: 0 },
      );
      return {
        useCaseId: useCase.id,
        label: useCase.label,
        icon: useCase.icon,
        candidateCount,
        referenceApprovedCount,
      };
    });
  }, [familyApprovalScope, models, selectedApprovalFamilies, selectedBulkUseCases]);
  const bulkApprovalCandidateCount = useMemo(
    () => bulkApprovalPreview.reduce((total, entry) => total + Number(entry.candidateCount || 0), 0),
    [bulkApprovalPreview],
  );
  const approvedCount = useMemo(
    () => models.filter((model) => isModelApprovedForUseCase(model, approvalUseCaseId)).length,
    [approvalUseCaseId, models],
  );
  const scoredInternalCount = useMemo(
    () => models.filter((model) => model.scores?.[INTERNAL_VIEW_BENCHMARK_ID]?.value != null).length,
    [models],
  );
  const useCaseLookup = useMemo(
    () => buildAdminLookupIndex(useCases, (useCase) => [useCase.id, useCase.label]),
    [useCases],
  );
  const modelLookup = useMemo(
    () => buildAdminLookupIndex(models, (model) => [model.id, model.name]),
    [models],
  );
  const providerErrorsById = useMemo(
    () =>
      Object.fromEntries(
        providers.map((provider) => [provider.id, getProviderValidationErrors(provider, providerDrafts[provider.id])]),
      ),
    [providerDrafts, providers],
  );
  const internalWeightErrorsById = useMemo(
    () =>
      Object.fromEntries(
        useCases.map((useCase) => [useCase.id, getInternalWeightValidationErrors(useCase, internalWeightDrafts[useCase.id])]),
      ),
    [internalWeightDrafts, useCases],
  );
  const internalScoreErrorsById = useMemo(
    () =>
      Object.fromEntries(
        models.map((model) => [model.id, getInternalScoreValidationErrors(internalScoreDrafts[model.id])]),
      ),
    [internalScoreDrafts, models],
  );

  function updateProviderDraft(providerId, field, value) {
    setProviderDrafts((current) => {
      const nextDraft = {
        ...(current[providerId] || {}),
        [field]: value,
      };

      if (field === "country_code" || field === "country_name") {
        const parsed = parseOriginCountriesInput(nextDraft.origin_countries_input || "");
        if (parsed.countries.length <= 1) {
          nextDraft.origin_countries_input = formatOriginCountriesInput(
            nextDraft.country_name || nextDraft.country_code
              ? [{ code: nextDraft.country_code || null, name: nextDraft.country_name || nextDraft.country_code }]
              : [],
          );
        }
      }

      if (field === "origin_countries_input") {
        const parsed = parseOriginCountriesInput(value);
        if (parsed.countries.length === 1) {
          nextDraft.country_code = parsed.countries[0].code || "";
          nextDraft.country_name = parsed.countries[0].name || "";
        } else if (parsed.countries.length > 1) {
          nextDraft.country_code = "";
          nextDraft.country_name = summarizeOriginCountries(parsed.countries);
        } else if (!String(value || "").trim()) {
          nextDraft.country_code = "";
          nextDraft.country_name = "";
        }
      }

      return {
        ...current,
        [providerId]: nextDraft,
      };
    });
  }

  function updateModelDraft(modelId, field, value) {
    const draftKey = buildModelApprovalDraftKey(modelId, approvalUseCaseId);
    setModelDrafts((current) => ({
      ...current,
      [draftKey]: {
        ...(current[draftKey] || {}),
        [field]: value,
      },
    }));
  }

  function updateModelCurationDraft(modelId, field, value) {
    setModelCurationDrafts((current) => ({
      ...current,
      [modelId]: {
        ...createModelCurationDraft(models.find((candidate) => candidate.id === modelId)),
        ...(current[modelId] || {}),
        [field]: value,
      },
    }));
  }

  function updateInternalWeightDraft(useCaseId, field, value) {
    setInternalWeightDrafts((current) => ({
      ...current,
      [useCaseId]: {
        ...(current[useCaseId] || {}),
        [field]: value,
      },
    }));
  }

  function updateInternalScoreDraft(modelId, field, value) {
    setInternalScoreDrafts((current) => ({
      ...current,
      [modelId]: {
        ...(current[modelId] || {}),
        [field]: value,
      },
    }));
  }

  function isProviderDirty(provider) {
    const draft = providerDrafts[provider.id];
    if (!draft) {
      return false;
    }
    const currentOriginCountriesInput = formatOriginCountriesInput(
      provider.origin_countries,
      provider.country_code,
      provider.country_name,
    );
    return (
      (draft.country_code || "") !== (provider.country_code || "") ||
      (draft.country_name || "") !== (provider.country_name || "") ||
      (draft.origin_countries_input || "") !== currentOriginCountriesInput ||
      (draft.origin_basis || "") !== (provider.origin_basis || "") ||
      (draft.source_url || "") !== (provider.source_url || "") ||
      (draft.verified_at || "") !== (provider.verified_at || "")
    );
  }

  function isModelDirty(model) {
    if (!approvalUseCaseId) {
      return false;
    }
    const draftKey = buildModelApprovalDraftKey(model.id, approvalUseCaseId);
    const draft = modelDrafts[draftKey];
    if (!draft) {
      return false;
    }
    const currentApproval = createModelDraft(model, approvalUseCaseId);
    return (
      Boolean(draft.approved_for_use) !== Boolean(currentApproval.approved_for_use) ||
      (draft.approval_notes || "") !== (currentApproval.approval_notes || "") ||
      (draft.recommendation_status || "unrated") !== (currentApproval.recommendation_status || "unrated") ||
      (draft.recommendation_notes || "") !== (currentApproval.recommendation_notes || "")
    );
  }

  function isInternalWeightDirty(useCase) {
    const draft = internalWeightDrafts[useCase.id];
    if (!draft) {
      return false;
    }
    return Math.abs(parsePercentInputToShare(draft.weightPercent) - Number(useCase.internal_view_weight || 0)) > 0.0001;
  }

  function isInternalScoreDirty(model) {
    const draft = internalScoreDrafts[model.id];
    if (!draft) {
      return false;
    }
    const score = model.scores?.[INTERNAL_VIEW_BENCHMARK_ID];
    const draftValue = parseOptionalNumber(draft.value);
    const currentValue = score?.value != null ? Number(score.value) : null;
    return (
      draftValue !== currentValue ||
      (draft.notes || "") !== (score?.notes || "")
    );
  }

  const dirtyProviderIds = useMemo(
    () => providers.filter((provider) => isProviderDirty(provider)).map((provider) => provider.id),
    [providerDrafts, providers],
  );
  const dirtyModelDraftEntries = useMemo(
    () =>
      Object.entries(modelDrafts).flatMap(([draftKey, draft]) => {
        const { modelId, useCaseId } = parseModelApprovalDraftKey(draftKey);
        const model = models.find((candidate) => candidate.id === modelId);
        if (!model || !useCaseId || !useCases.some((useCase) => useCase.id === useCaseId)) {
          return [];
        }
        const currentApproval = createModelDraft(model, useCaseId);
        const isDirty =
          Boolean(draft?.approved_for_use) !== Boolean(currentApproval.approved_for_use) ||
          (draft?.approval_notes || "") !== (currentApproval.approval_notes || "") ||
          (draft?.recommendation_status || "unrated") !== (currentApproval.recommendation_status || "unrated") ||
          (draft?.recommendation_notes || "") !== (currentApproval.recommendation_notes || "");
        return isDirty
          ? [
              {
                draftKey,
                model,
                modelId,
                useCaseId,
                draft,
              },
            ]
          : [];
      }),
    [modelDrafts, models, useCases],
  );
  const dirtyInternalWeightIds = useMemo(
    () => useCases.filter((useCase) => isInternalWeightDirty(useCase)).map((useCase) => useCase.id),
    [internalWeightDrafts, useCases],
  );
  const dirtyInternalScoreIds = useMemo(
    () => models.filter((model) => isInternalScoreDirty(model)).map((model) => model.id),
    [internalScoreDrafts, models],
  );
  const invalidDirtyProviderCount = dirtyProviderIds.filter((providerId) => providerErrorsById[providerId]?.length).length;
  const invalidDirtyInternalWeightCount = dirtyInternalWeightIds.filter((useCaseId) => internalWeightErrorsById[useCaseId]?.length).length;
  const invalidDirtyInternalScoreCount = dirtyInternalScoreIds.filter((modelId) => internalScoreErrorsById[modelId]?.length).length;
  const filteredUseCases = useMemo(
    () =>
      useCases.filter((useCase) => {
        if (!internalWeightChangedOnly) {
          return true;
        }
        return isInternalWeightDirty(useCase);
      }),
    [internalWeightChangedOnly, internalWeightDrafts, useCases],
  );
  const dirtyModelIds = useMemo(
    () => dirtyModelDraftEntries.map((entry) => entry.draftKey),
    [dirtyModelDraftEntries],
  );
  const showProvidersSection = adminFocus === "all" || adminFocus === "providers";
  const showApprovalsSection = adminFocus === "all" || adminFocus === "approvals";
  const showInternalWeightsSection = adminFocus === "all" || adminFocus === "internal_weights";
  const showInternalScoresSection = adminFocus === "all" || adminFocus === "internal_scores";

  function buildProviderSavePayload(draft) {
    const parsed = parseOriginCountriesInput(draft.origin_countries_input || "");
    return {
      country_code: draft.country_code || "",
      country_name: draft.country_name || "",
      origin_countries: parsed.countries,
      origin_basis: draft.origin_basis || "",
      source_url: draft.source_url || "",
      verified_at: draft.verified_at || "",
    };
  }

  function buildModelApprovalSavePayload(useCaseId, draft) {
    return {
      use_case_id: useCaseId,
      approved_for_use: Boolean(draft?.approved_for_use),
      approval_notes: draft?.approval_notes || "",
      recommendation_status: draft?.recommendation_status || "unrated",
      recommendation_notes: draft?.recommendation_notes || "",
    };
  }

  async function handleSaveProvider(provider) {
    const draft = providerDrafts[provider.id];
    if (!draft || providerErrorsById[provider.id]?.length) {
      return;
    }
    setProviderSavingId(provider.id);
    const success = await onSaveProvider(provider.id, buildProviderSavePayload(draft));
    setProviderSavingId("");
    if (success) {
      setMessage(`Saved provider origin for ${provider.name}.`);
    }
  }

  async function handleSaveModel(model) {
    if (!approvalUseCaseId) {
      return;
    }
    const draftKey = buildModelApprovalDraftKey(model.id, approvalUseCaseId);
    const draft = modelDrafts[draftKey];
    if (!draft) {
      return;
    }
    setModelSavingId(draftKey);
    const success = await onSaveModelApproval(model.id, buildModelApprovalSavePayload(approvalUseCaseId, draft));
    setModelSavingId("");
    if (success) {
      setMessage(`Saved ${approvalUseCase?.label || approvalUseCaseId} review state for ${model.name}.`);
    }
  }

  async function handleSaveModelIdentityCuration(model, targetModel) {
    const draft = {
      ...createModelCurationDraft(model),
      ...(modelCurationDrafts[model.id] || {}),
    };
    if (!targetModel || targetModel.id === model.id) {
      return;
    }
    setModelCurationSavingId(`identity:${model.id}`);
    const updatedModel = await onSaveModelIdentityCuration(model.id, {
      target_model_id: targetModel.id,
      variant_label: draft.identity_variant_label || "",
      notes: draft.identity_notes || "",
    });
    setModelCurationSavingId("");
    if (updatedModel) {
      setMessage(`Saved durable family mapping for ${model.name} using ${targetModel.name}.`);
    }
  }

  async function handleMergeModelDuplicate(model, targetModel) {
    const draft = {
      ...createModelCurationDraft(model),
      ...(modelCurationDrafts[model.id] || {}),
    };
    if (!targetModel || targetModel.id === model.id) {
      return;
    }
    setModelCurationSavingId(`duplicate:${model.id}`);
    const mergedTarget = await onSaveModelDuplicateMerge(model.id, {
      target_model_id: targetModel.id,
      notes: draft.duplicate_notes || "",
    });
    setModelCurationSavingId("");
    if (mergedTarget) {
      setMessage(`Merged ${model.name} into ${mergedTarget.name} and stored a future duplicate rule.`);
    }
  }

  async function handleSaveInternalWeight(useCase) {
    const draft = internalWeightDrafts[useCase.id];
    if (!draft || internalWeightErrorsById[useCase.id]?.length) {
      return;
    }
    setInternalWeightSavingId(useCase.id);
    const success = await onSaveInternalWeight(useCase.id, {
      weight: parsePercentInputToShare(draft.weightPercent),
    });
    setInternalWeightSavingId("");
    if (success) {
      setMessage(`Saved internal view weight for ${useCase.label}.`);
    }
  }

  async function handleSaveInternalScore(model) {
    const draft = internalScoreDrafts[model.id];
    if (!draft || internalScoreErrorsById[model.id]?.length) {
      return;
    }
    setInternalScoreSavingId(model.id);
    const normalizedValue = parseOptionalNumber(draft.value);
    const success = await onSaveInternalBenchmarkScore(model.id, INTERNAL_VIEW_BENCHMARK_ID, {
      value: normalizedValue,
      raw_value: normalizedValue == null ? null : String(normalizedValue),
      notes: draft.notes || "",
    });
    setInternalScoreSavingId("");
    if (success) {
      setMessage(
        normalizedValue == null
          ? `Cleared internal view score for ${model.name}.`
          : `Saved internal view score for ${model.name}.`,
      );
    }
  }

  async function handleSaveAllProviders() {
    const dirtyProviders = providers.filter(
      (provider) => isProviderDirty(provider) && !(providerErrorsById[provider.id] || []).length,
    );
    if (!dirtyProviders.length) {
      return;
    }

    setProviderBulkSaving(true);
    let savedCount = 0;
    for (const provider of dirtyProviders) {
      const success = await onSaveProvider(provider.id, buildProviderSavePayload(providerDrafts[provider.id]));
      if (success) {
        savedCount += 1;
      }
    }
    setProviderBulkSaving(false);
    if (savedCount) {
      setMessage(`Saved ${savedCount} provider change${savedCount === 1 ? "" : "s"}.`);
    }
  }

  async function handleSaveAllModels() {
    if (!dirtyModelDraftEntries.length) {
      return;
    }

    setModelBulkSaving(true);
    let savedCount = 0;
    for (const entry of dirtyModelDraftEntries) {
      const success = await onSaveModelApproval(
        entry.modelId,
        buildModelApprovalSavePayload(entry.useCaseId, entry.draft),
        { refreshRankings: false },
      );
      if (success) {
        savedCount += 1;
      }
    }
    if (savedCount && approvalUseCaseId === selectedUseCaseId) {
      await onRefreshSelectedUseCaseRankings(approvalUseCaseId);
    }
    setModelBulkSaving(false);
    if (savedCount) {
      setMessage(`Saved ${savedCount} model review change${savedCount === 1 ? "" : "s"}.`);
    }
  }

  function handleApplyBulkRecommendationToFilteredModels() {
    if (!approvalUseCaseId || !filteredModels.length) {
      return;
    }
    setModelDrafts((current) => {
      const next = { ...current };
      filteredModels.forEach((model) => {
        const draftKey = buildModelApprovalDraftKey(model.id, approvalUseCaseId);
        next[draftKey] = {
          ...(next[draftKey] || createModelDraft(model, approvalUseCaseId)),
          recommendation_status: bulkRecommendationStatus,
          recommendation_notes: bulkRecommendationNotes,
        };
      });
      return next;
    });
    setMessage(
      `Applied ${formatRecommendationStatusLabel(bulkRecommendationStatus).toLowerCase()} recommendation draft to ${filteredModels.length} filtered model${filteredModels.length === 1 ? "" : "s"} for ${approvalUseCase?.label || approvalUseCaseId}. Save changes to persist.`,
    );
  }

  async function handleApplyInferenceRouteBulk() {
    if (!hasSelectedInferenceRoute || !filteredModels.length) {
      return;
    }
    setBulkInferenceRouteSaving(true);
    const result = await onApplyInferenceRouteApprovalBulk(approvalUseCaseId, {
      model_ids: filteredModels.map((model) => model.id),
      destination_id: approvalInferenceProviderFilter,
      location_key: selectedInferenceRouteLocationKey,
      location_label: approvalInferenceLocationFilter,
      approved_for_use: bulkInferenceRouteApproval,
      approval_notes: bulkInferenceRouteNotes,
    });
    setBulkInferenceRouteSaving(false);
    if (!result) {
      return;
    }
    setBulkInferenceRouteNotes("");
    setMessage(
      `${bulkInferenceRouteApproval ? "Approved" : "Blocked"} ${result.updated_count} inference route change${Number(result.updated_count) === 1 ? "" : "s"} for ${selectedInferenceProvider?.label || "the selected provider"} in ${approvalInferenceLocationFilter}. Positive route approvals also ensure the base lens approval is on.`,
    );
  }

  function toggleBulkApprovalUseCase(useCaseId) {
    setBulkApprovalUseCaseIds((current) => {
      if (current.includes(useCaseId)) {
        return current.length === 1 ? current : current.filter((candidate) => candidate !== useCaseId);
      }
      return [...current, useCaseId];
    });
  }

  function toggleApprovalFamilyFilter(familyId) {
    if (!familyId || familyId === DEFAULT_APPROVAL_FAMILY_FILTER) {
      setApprovalFamilyFilters([]);
      return;
    }
    setApprovalFamilyFilters((current) => (
      current.includes(familyId)
        ? current.filter((candidate) => candidate !== familyId)
        : [...current, familyId]
    ));
  }

  async function handleApplyFamilyBulk() {
    if (
      !selectedApprovalFamilies.length ||
      !bulkApprovalUseCaseIds.length ||
      !bulkApprovalCandidateCount
    ) {
      return;
    }
    setFamilyDeltaSaving(true);
    let totalUpdatedCount = 0;
    let updatedFamilyCount = 0;
    for (const family of selectedApprovalFamilies) {
      const result = await onApplyFamilyApprovalBulk(family.id, {
        use_case_ids: bulkApprovalUseCaseIds,
        approval_notes: familyDeltaNotes,
        scope: familyApprovalScope,
      });
      if (!result) {
        continue;
      }
      updatedFamilyCount += 1;
      totalUpdatedCount += Number(result.total_updated_count || 0);
    }
    setFamilyDeltaSaving(false);
    if (updatedFamilyCount) {
      setFamilyDeltaNotes("");
      setMessage(
        totalUpdatedCount
          ? `Approved ${totalUpdatedCount} family approval change${totalUpdatedCount === 1 ? "" : "s"} across ${selectedApprovalFamilies.length} famil${selectedApprovalFamilies.length === 1 ? "y" : "ies"} and ${bulkApprovalUseCaseIds.length} lens${bulkApprovalUseCaseIds.length === 1 ? "" : "es"}.`
          : `No matching family approvals needed updates across ${selectedApprovalFamilies.length} selected famil${selectedApprovalFamilies.length === 1 ? "y" : "ies"}.`,
      );
    }
  }

  async function handleSaveAllInternalWeights() {
    const dirtyUseCases = useCases.filter(
      (useCase) => isInternalWeightDirty(useCase) && !(internalWeightErrorsById[useCase.id] || []).length,
    );
    if (!dirtyUseCases.length) {
      return;
    }

    setInternalWeightBulkSaving(true);
    let savedCount = 0;
    for (const useCase of dirtyUseCases) {
      const success = await onSaveInternalWeight(useCase.id, {
        weight: parsePercentInputToShare(internalWeightDrafts[useCase.id]?.weightPercent),
      });
      if (success) {
        savedCount += 1;
      }
    }
    setInternalWeightBulkSaving(false);
    if (savedCount) {
      setMessage(`Saved ${savedCount} internal weight${savedCount === 1 ? "" : "s"}.`);
    }
  }

  async function handleSaveAllInternalScores() {
    const dirtyModels = models.filter(
      (model) => isInternalScoreDirty(model) && !(internalScoreErrorsById[model.id] || []).length,
    );
    if (!dirtyModels.length) {
      return;
    }

    setInternalScoreBulkSaving(true);
    let savedCount = 0;
    for (const model of dirtyModels) {
      const draft = internalScoreDrafts[model.id];
      const normalizedValue = parseOptionalNumber(draft?.value);
      const success = await onSaveInternalBenchmarkScore(model.id, INTERNAL_VIEW_BENCHMARK_ID, {
        value: normalizedValue,
        raw_value: normalizedValue == null ? null : String(normalizedValue),
        notes: draft?.notes || "",
      });
      if (success) {
        savedCount += 1;
      }
    }
    setInternalScoreBulkSaving(false);
    if (savedCount) {
      setMessage(`Saved ${savedCount} internal score${savedCount === 1 ? "" : "s"}.`);
    }
  }

  function handleApplyInternalWeightBulk() {
    const parsedRows = parseBulkEditorRows(internalWeightBulkText);
    if (!parsedRows.length) {
      setInternalWeightBulkResult({
        tone: "warning",
        title: "Nothing to apply",
        lines: ["Paste one row per lens, for example: `coding<TAB>10`."],
      });
      return;
    }

    const nextDrafts = { ...internalWeightDrafts };
    let appliedCount = 0;
    const issues = [];

    parsedRows.forEach((row, index) => {
      const [lookup = "", weightValue = ""] = row.cells;
      if (!lookup) {
        return;
      }
      if (index === 0 && isBulkWeightHeaderRow(row.cells)) {
        return;
      }
      const matchedUseCase = resolveAdminLookup(useCaseLookup, lookup);
      if (matchedUseCase === undefined) {
        issues.push(`Line ${row.lineNumber}: no lens matched "${lookup}".`);
        return;
      }
      if (matchedUseCase === null) {
        issues.push(`Line ${row.lineNumber}: "${lookup}" matches more than one lens. Use the exact lens id.`);
        return;
      }

      const normalizedWeight = normalizePercentInput(weightValue);
      const errors = getInternalWeightValidationErrors(matchedUseCase, { weightPercent: normalizedWeight });
      if (errors.length) {
        issues.push(`Line ${row.lineNumber}: ${errors[0]}`);
        return;
      }

      nextDrafts[matchedUseCase.id] = {
        ...(nextDrafts[matchedUseCase.id] || createInternalWeightDraft(matchedUseCase)),
        weightPercent: normalizedWeight,
      };
      appliedCount += 1;
    });

    if (appliedCount) {
      setInternalWeightDrafts(nextDrafts);
    }
    setInternalWeightBulkResult({
      tone: issues.length ? "warning" : "info",
      title: issues.length ? "Applied with issues" : "Applied",
      lines: [
        appliedCount
          ? `Prepared ${appliedCount} internal weight update${appliedCount === 1 ? "" : "s"} in draft state.`
          : "No internal weight rows were applied.",
        ...issues.slice(0, 6),
      ],
    });
    if (appliedCount) {
      setMessage(`Prepared ${appliedCount} internal weight update${appliedCount === 1 ? "" : "s"} from bulk paste.`);
    }
  }

  function handleApplyInternalScoreBulk() {
    const parsedRows = parseBulkEditorRows(internalScoreBulkText);
    if (!parsedRows.length) {
      setInternalScoreBulkResult({
        tone: "warning",
        title: "Nothing to apply",
        lines: ["Paste one row per model, for example: `gpt-5-4<TAB>88<TAB>Preferred for coding`."],
      });
      return;
    }

    const nextDrafts = { ...internalScoreDrafts };
    let appliedCount = 0;
    const issues = [];

    parsedRows.forEach((row, index) => {
      const [lookup = "", value = "", ...noteParts] = row.cells;
      if (!lookup) {
        return;
      }
      if (index === 0 && isBulkScoreHeaderRow(row.cells)) {
        return;
      }
      const matchedModel = resolveAdminLookup(modelLookup, lookup);
      if (matchedModel === undefined) {
        issues.push(`Line ${row.lineNumber}: no model matched "${lookup}".`);
        return;
      }
      if (matchedModel === null) {
        issues.push(`Line ${row.lineNumber}: "${lookup}" matches more than one model. Use the exact model id.`);
        return;
      }

      const normalizedValue = normalizeOptionalNumberInput(value);
      const notes = noteParts.join(row.delimiter === "\t" ? "\t" : ",").trim();
      const errors = getInternalScoreValidationErrors({ value: normalizedValue, notes });
      if (errors.length) {
        issues.push(`Line ${row.lineNumber}: ${errors[0]}`);
        return;
      }

      nextDrafts[matchedModel.id] = {
        ...(nextDrafts[matchedModel.id] || createInternalScoreDraft(matchedModel)),
        value: normalizedValue,
        notes,
      };
      appliedCount += 1;
    });

    if (appliedCount) {
      setInternalScoreDrafts(nextDrafts);
    }
    setInternalScoreBulkResult({
      tone: issues.length ? "warning" : "info",
      title: issues.length ? "Applied with issues" : "Applied",
      lines: [
        appliedCount
          ? `Prepared ${appliedCount} internal score update${appliedCount === 1 ? "" : "s"} in draft state.`
          : "No internal score rows were applied.",
        ...issues.slice(0, 6),
      ],
    });
    if (appliedCount) {
      setMessage(`Prepared ${appliedCount} internal score update${appliedCount === 1 ? "" : "s"} from bulk paste.`);
    }
  }

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Admin</h2>
          <p>Maintain provider origin metadata, approvals, and Internal View signals without row-by-row busywork.</p>
        </div>
      </div>

      <article className="panel stack">
        <div className="panel-head">Editing Focus</div>
        <div className="admin-subtle">
          Use focus mode to work one section at a time. Bulk paste works well with spreadsheet data copied as tab-separated rows.
        </div>
        <div aria-label="Admin focus" className="toggle-group admin-focus-group" role="group">
          {ADMIN_FOCUS_OPTIONS.map((option) => (
            <button
              key={option.id}
              className={adminFocus === option.id ? "toggle-btn toggle-btn-active" : "toggle-btn"}
              onClick={() => setAdminFocus(option.id)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </article>

      {message ? <Banner tone="info" title="Saved" message={message} /> : null}
      {dirtyProviderIds.length || dirtyModelIds.length || dirtyInternalWeightIds.length || dirtyInternalScoreIds.length ? (
        <div className="admin-savebar">
          <div className="admin-savebar-copy">
            <strong>{dirtyProviderIds.length + dirtyModelIds.length + dirtyInternalWeightIds.length + dirtyInternalScoreIds.length}</strong> unsaved change
            {dirtyProviderIds.length + dirtyModelIds.length + dirtyInternalWeightIds.length + dirtyInternalScoreIds.length === 1 ? "" : "s"}
            {invalidDirtyProviderCount ? ` · ${invalidDirtyProviderCount} provider row${invalidDirtyProviderCount === 1 ? "" : "s"} need valid data before saving` : ""}
            {invalidDirtyInternalWeightCount ? `${invalidDirtyProviderCount ? " · " : " · "}${invalidDirtyInternalWeightCount} internal weight row${invalidDirtyInternalWeightCount === 1 ? "" : "s"} need valid percentages before saving` : ""}
            {invalidDirtyInternalScoreCount ? `${invalidDirtyProviderCount || invalidDirtyInternalWeightCount ? " · " : " · "}${invalidDirtyInternalScoreCount} internal score row${invalidDirtyInternalScoreCount === 1 ? "" : "s"} need valid numeric values before saving` : ""}
            .
          </div>
          <div className="admin-savebar-actions">
            {dirtyProviderIds.length ? (
              <button
                className="btn btn-secondary"
                disabled={providerBulkSaving || invalidDirtyProviderCount > 0}
                onClick={handleSaveAllProviders}
                type="button"
              >
                {providerBulkSaving ? "Saving providers…" : `Save ${dirtyProviderIds.length} provider change${dirtyProviderIds.length === 1 ? "" : "s"}`}
              </button>
            ) : null}
            {dirtyInternalWeightIds.length ? (
              <button
                className="btn btn-secondary"
                disabled={internalWeightBulkSaving || invalidDirtyInternalWeightCount > 0}
                onClick={handleSaveAllInternalWeights}
                type="button"
              >
                {internalWeightBulkSaving
                  ? "Saving internal weights…"
                  : `Save ${dirtyInternalWeightIds.length} internal weight${dirtyInternalWeightIds.length === 1 ? "" : "s"}`}
              </button>
            ) : null}
            {dirtyModelIds.length ? (
              <button className="btn btn-primary" disabled={modelBulkSaving} onClick={handleSaveAllModels} type="button">
                {modelBulkSaving ? "Saving reviews…" : `Save ${dirtyModelIds.length} review change${dirtyModelIds.length === 1 ? "" : "s"}`}
              </button>
            ) : null}
            {dirtyInternalScoreIds.length ? (
              <button
                className="btn btn-primary"
                disabled={internalScoreBulkSaving || invalidDirtyInternalScoreCount > 0}
                onClick={handleSaveAllInternalScores}
                type="button"
              >
                {internalScoreBulkSaving
                  ? "Saving internal scores…"
                  : `Save ${dirtyInternalScoreIds.length} internal score${dirtyInternalScoreIds.length === 1 ? "" : "s"}`}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {showProvidersSection ? (
      <article className="panel stack">
        <div className="panel-head">Provider Directory</div>
        <div className="admin-subtle">
          Provider origin lives at the provider level. Changes here automatically flow into the model catalog.
        </div>
        <div className="admin-toolbar">
          <label className="field">
            <span className="field-label">Search providers</span>
            <input
              className="input"
              onChange={(event) => setProviderSearch(event.target.value)}
              placeholder="Search providers…"
              type="text"
              value={providerSearch}
            />
          </label>
          <label className="checkbox-row admin-checkbox-inline">
            <input
              checked={providerChangedOnly}
              onChange={(event) => setProviderChangedOnly(event.target.checked)}
              type="checkbox"
            />
            <span>Changed only</span>
          </label>
        </div>
        <div className="admin-subtle">Showing {filteredProviders.length} of {providers.length} providers.</div>
        <div className="admin-list">
          {filteredProviders.map((provider) => {
            const draft = providerDrafts[provider.id] || {};
            const flag = countryFlagFromCode(draft.country_code || provider.country_code);
            const isSaving = providerSavingId === provider.id || providerBulkSaving;
            const errors = providerErrorsById[provider.id] || [];
            return (
              <div key={provider.id} className="admin-row">
                <div className="admin-row-head">
                  <div className="admin-row-title">
                    <span className="title">{provider.name}</span>
                    <span className="tag">{flag ? `${flag} ` : ""}{draft.country_name || provider.country_name || "Origin unset"}</span>
                  </div>
                  <div className="hint">ID: {provider.id}</div>
                </div>
                <div className="admin-grid">
                  <label className="field">
                    <span className="field-label">Country code</span>
                    <input
                      className="input"
                      maxLength={2}
                      onChange={(event) => updateProviderDraft(provider.id, "country_code", event.target.value.toUpperCase())}
                      placeholder="US"
                      pattern="[A-Z]{2}"
                      type="text"
                      value={draft.country_code || ""}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Country name</span>
                    <input
                      className="input"
                      onChange={(event) => updateProviderDraft(provider.id, "country_name", event.target.value)}
                      placeholder="United States"
                      type="text"
                      value={draft.country_name || ""}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Verified at</span>
                    <input
                      className="input"
                      onChange={(event) => updateProviderDraft(provider.id, "verified_at", parseDateTimeLocalInput(event.target.value))}
                      type="datetime-local"
                      value={formatDateTimeLocalInput(draft.verified_at || "")}
                    />
                  </label>
                </div>
                <label className="field">
                  <span className="field-label">Origin countries</span>
                  <textarea
                    className="input admin-textarea"
                    onChange={(event) => updateProviderDraft(provider.id, "origin_countries_input", event.target.value)}
                    placeholder={"US | United States\nGB | United Kingdom"}
                    rows={2}
                    value={draft.origin_countries_input || ""}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Source URL</span>
                  <input
                    className="input"
                    onChange={(event) => updateProviderDraft(provider.id, "source_url", event.target.value)}
                    placeholder="https://example.com/source"
                    type="url"
                    value={draft.source_url || ""}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Origin basis</span>
                  <textarea
                    className="input admin-textarea"
                    onChange={(event) => updateProviderDraft(provider.id, "origin_basis", event.target.value)}
                    rows={3}
                    value={draft.origin_basis || ""}
                  />
                </label>
                {errors.length ? (
                  <div className="admin-errors">
                    {errors.map((error) => (
                      <div key={error}>{error}</div>
                    ))}
                  </div>
                ) : null}
                <div className="admin-actions">
                  <button
                    className="btn btn-secondary"
                    disabled={isSaving || !isProviderDirty(provider) || errors.length > 0}
                    onClick={() => handleSaveProvider(provider)}
                    type="button"
                  >
                    {isSaving ? "Saving…" : "Save provider"}
                  </button>
                </div>
              </div>
            );
          })}
          {!filteredProviders.length ? <EmptyState message="No providers match the current search." /> : null}
        </div>
      </article>
      ) : null}

      {showApprovalsSection ? (
      <article className="panel stack">
        <div className="panel-head">Model Approval</div>
        <div className="admin-subtle">
          Base approval is tracked per exact model and per lens, with optional route-specific overlays by inference provider and location. {approvedCount} of {models.length} models are currently approved for {approvalUseCase?.label || "the selected lens"}.
          {" "}
          {pendingReviewCount} newly discovered model{pendingReviewCount === 1 ? "" : "s"} still need review, and {suggestedReviewCount} of those already match an approved family pattern.
        </div>
        <div className="admin-toolbar">
          <label className="field">
            <span className="field-label">Lens</span>
            <select className="input select" onChange={(event) => setApprovalUseCaseId(event.target.value)} value={approvalUseCaseId}>
              {useCases.map((useCase) => (
                <option key={useCase.id} value={useCase.id}>
                  {useCase.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Search exact models</span>
            <input
              className="input"
              onChange={(event) => setModelSearch(event.target.value)}
              placeholder="Search exact models…"
              type="text"
              value={modelSearch}
            />
          </label>
          <div className="field">
            <span className="field-label">Families</span>
            <div className="admin-chip-grid">
              <button
                className={!selectedApprovalFamilies.length ? "admin-chip admin-chip-active" : "admin-chip"}
                onClick={() => toggleApprovalFamilyFilter(DEFAULT_APPROVAL_FAMILY_FILTER)}
                type="button"
              >
                All families
              </button>
              {visibleApprovalFamilies.map((family) => {
                const selected = approvalFamilyFilters.includes(family.id);
                return (
                  <button
                    key={family.id}
                    className={selected ? "admin-chip admin-chip-active" : "admin-chip"}
                    onClick={() => toggleApprovalFamilyFilter(family.id)}
                    type="button"
                  >
                    {`${family.label} (${family.count})`}
                  </button>
                );
              })}
            </div>
            <div className="admin-subtle">
              Ordered by OpenRouter popularity. This list reflects the current approval filters, excluding the family selection itself. Selected families stay visible even if they no longer match the other filters.
            </div>
            {!visibleApprovalFamilies.length && !selectedApprovalFamilies.length ? (
              <div className="admin-subtle">No families match the current approval filters.</div>
            ) : null}
            {hasMoreApprovalFamilies ? (
              <div className="admin-actions admin-actions-start">
                <button
                  className="btn btn-ghost btn-inline"
                  onClick={() => setVisibleApprovalFamilyCount((current) => current + 10)}
                  type="button"
                >
                  Load 10 more families
                </button>
              </div>
            ) : null}
          </div>
          <label className="field">
            <span className="field-label">Origin</span>
            <select className="input select" onChange={(event) => setApprovalOriginFilter(event.target.value)} value={approvalOriginFilter}>
              {approvalOrigins.map((origin) => (
                <option key={origin} value={origin}>
                  {origin === DEFAULT_ORIGIN_FILTER ? "All origins" : origin}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Recommendation</span>
            <select
              className="input select"
              onChange={(event) => setApprovalRecommendationFilter(event.target.value)}
              value={approvalRecommendationFilter}
            >
              {RECOMMENDATION_FILTER_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Hyperscaler</span>
            <select
              className="input select"
              onChange={(event) => setApprovalHyperscalerFilter(event.target.value)}
              value={approvalHyperscalerFilter}
            >
              {approvalHyperscalers.map((hyperscaler) => (
                <option key={hyperscaler} value={hyperscaler}>
                  {hyperscaler === DEFAULT_HYPERSCALER_FILTER ? "All hyperscalers" : hyperscaler}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Inference provider</span>
            <select
              className="input select"
              onChange={(event) => setApprovalInferenceProviderFilter(event.target.value)}
              value={approvalInferenceProviderFilter}
            >
              <option value={DEFAULT_INFERENCE_PROVIDER_FILTER}>All inference providers</option>
              {approvalInferenceProviders.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.hyperscaler ? `${provider.label} · ${provider.hyperscaler}` : provider.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Review signal</span>
            <select className="input select" onChange={(event) => setReviewSignalFilter(event.target.value)} value={reviewSignalFilter}>
              {MODEL_REVIEW_FILTER_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Inference location</span>
            <select
              className="input select"
              onChange={(event) => setApprovalInferenceLocationFilter(event.target.value)}
              value={approvalInferenceLocationFilter}
            >
              {approvalInferenceLocations.map((location) => (
                <option key={location} value={location}>
                  {location === DEFAULT_INFERENCE_LOCATION_FILTER ? "All locations" : location}
                </option>
              ))}
            </select>
          </label>
          <div aria-label="Approval filter" className="toggle-group admin-filter-toggle" role="group">
            {MODEL_APPROVAL_FILTER_OPTIONS.map((option) => (
              <button
                key={option.id}
                className={modelApprovalFilter === option.id ? "toggle-btn toggle-btn-active" : "toggle-btn"}
                onClick={() => setModelApprovalFilter(option.id)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {filteredModels.length ? (
          <div className="admin-bulk-editor">
            <div className="detail-label">Bulk recommendation drafts</div>
            <div className="admin-subtle">
              This uses the current Admin filters, including origin, family, hyperscaler, inference location, review signal, and search. It only changes recommendation fields for {approvalUseCase?.label || "the selected lens"} and leaves approval unchanged.
            </div>
            <div className="admin-grid admin-grid-two">
              <label className="field">
                <span className="field-label">Recommendation status</span>
                <select
                  className="input select"
                  onChange={(event) => setBulkRecommendationStatus(event.target.value)}
                  value={bulkRecommendationStatus}
                >
                  {RECOMMENDATION_STATUS_OPTIONS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="admin-inline-note">
                Applying this writes draft changes to {filteredModels.length} filtered model{filteredModels.length === 1 ? "" : "s"}. Use the save bar to persist them to the database.
              </div>
            </div>
            <label className="field">
              <span className="field-label">Recommendation notes</span>
              <textarea
                className="input admin-textarea"
                onChange={(event) => setBulkRecommendationNotes(event.target.value)}
                placeholder="Optional note applied to all filtered models for this lens."
                rows={3}
                value={bulkRecommendationNotes}
              />
            </label>
            <div className="admin-actions admin-actions-start">
              <button
                className="btn btn-secondary"
                disabled={!approvalUseCaseId || !filteredModels.length}
                onClick={handleApplyBulkRecommendationToFilteredModels}
                type="button"
              >
                {`Apply to ${filteredModels.length} filtered model${filteredModels.length === 1 ? "" : "s"}`}
              </button>
            </div>
          </div>
        ) : null}
        {hasSelectedInferenceRoute ? (
          <div className="admin-bulk-editor">
            <div className="detail-label">Bulk inference route approval</div>
            <div className="admin-subtle">
              This writes route-specific approval rows for <strong>{selectedInferenceProvider?.label || "the selected inference provider"}</strong> in <strong>{approvalInferenceLocationFilter}</strong> across the current filtered models. Once a model has any route-specific rows for this lens, missing routes are treated as unreviewed rather than inheriting the base approval.
            </div>
            <div className="admin-grid admin-grid-two">
              <label className="field">
                <span className="field-label">Route decision</span>
                <select
                  className="input select"
                  onChange={(event) => setBulkInferenceRouteApproval(event.target.value === "approved")}
                  value={bulkInferenceRouteApproval ? "approved" : "blocked"}
                >
                  <option value="approved">Approved on this route</option>
                  <option value="blocked">Not approved on this route</option>
                </select>
              </label>
              <div className="admin-inline-note">
                Positive route approvals auto-enable the base model approval for this lens if it was still off. Blocking a route does not change the base recommendation or approval state.
              </div>
            </div>
            <label className="field">
              <span className="field-label">Route notes</span>
              <textarea
                className="input admin-textarea"
                onChange={(event) => setBulkInferenceRouteNotes(event.target.value)}
                placeholder="Optional note for this provider/location policy, for example data residency or platform-specific constraints."
                rows={3}
                value={bulkInferenceRouteNotes}
              />
            </label>
            <div className="admin-actions admin-actions-start">
              <button
                className="btn btn-secondary"
                disabled={bulkInferenceRouteSaving || !filteredModels.length}
                onClick={handleApplyInferenceRouteBulk}
                type="button"
              >
                {bulkInferenceRouteSaving
                  ? "Applying route approval…"
                  : `Apply to ${filteredModels.length} filtered model${filteredModels.length === 1 ? "" : "s"}`}
              </button>
            </div>
          </div>
        ) : (
          <div className="admin-subtle">
            Select both an <strong>Inference provider</strong> and an <strong>Inference location</strong> to write route-specific approvals for the current lens.
          </div>
        )}
        {selectedApprovalFamilies.length ? (
          <div className="admin-bulk-editor">
            <div className="detail-label">Bulk family approval</div>
            <div className="admin-subtle">
              Select one or more lenses, then approve either the full selected families or only the newly discovered family delta. The single `Lens` selector above still controls the exact-model review list below.
            </div>
            <div className="admin-grid admin-grid-two">
              <label className="field">
                <span className="field-label">Bulk scope</span>
                <select className="input select" onChange={(event) => setFamilyApprovalScope(event.target.value)} value={familyApprovalScope}>
                  {FAMILY_APPROVAL_SCOPE_OPTIONS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="admin-inline-note">
                {familyApprovalScope === "delta"
                  ? "Delta mode only touches newly discovered, still-unreviewed members, and only for lenses that already have approved reference models in each selected family."
                  : `Family mode approves every exact model in the ${selectedApprovalFamilies.length} selected famil${selectedApprovalFamilies.length === 1 ? "y" : "ies"} for the selected lenses, including rows previously reviewed as not approved.`}
              </div>
            </div>
            <div className="field">
              <span className="field-label">Bulk lenses</span>
              <div className="admin-chip-grid">
                {useCases.map((useCase) => {
                  const selected = bulkApprovalUseCaseIds.includes(useCase.id);
                  return (
                    <label
                      key={useCase.id}
                      className={selected ? "admin-chip admin-chip-active" : "admin-chip"}
                    >
                      <input
                        checked={selected}
                        onChange={() => toggleBulkApprovalUseCase(useCase.id)}
                        type="checkbox"
                      />
                      <span>{useCase.icon} {useCase.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
            <label className="field">
              <span className="field-label">Bulk notes</span>
              <textarea
                className="input admin-textarea"
                onChange={(event) => setFamilyDeltaNotes(event.target.value)}
                placeholder="Optional note to apply to the new family members."
                rows={2}
                value={familyDeltaNotes}
              />
            </label>
            <div className="admin-preview-list">
              {bulkApprovalPreview.map((entry) => (
                <div key={entry.useCaseId} className="admin-preview-row">
                  <span>{entry.icon} {entry.label}</span>
                  <span>
                    {entry.candidateCount} candidate{entry.candidateCount === 1 ? "" : "s"}
                    {familyApprovalScope === "delta" ? ` · ${entry.referenceApprovedCount} approved reference${entry.referenceApprovedCount === 1 ? "" : "s"}` : ""}
                  </span>
                </div>
              ))}
            </div>
            <div className="admin-actions admin-actions-start">
              <button
                className="btn btn-primary"
                disabled={familyDeltaSaving || !bulkApprovalUseCaseIds.length || !bulkApprovalCandidateCount}
                onClick={handleApplyFamilyBulk}
                type="button"
              >
                {familyDeltaSaving
                  ? "Applying bulk family approval…"
                  : `${familyApprovalScope === "delta" ? "Approve family delta" : "Approve family"} (${bulkApprovalCandidateCount})`}
              </button>
            </div>
          </div>
        ) : null}
        <div className="admin-subtle">Showing {filteredModels.length} of {models.length} models.</div>
        <div className="admin-list">
          {filteredModels.map((model) => {
            const approval = getModelApprovalRecord(model, approvalUseCaseId);
            const reviewSignal = approvalReviewSignals[model.id] || null;
            const draftKey = buildModelApprovalDraftKey(model.id, approvalUseCaseId);
            const draft = modelDrafts[draftKey] || createModelDraft(model, approvalUseCaseId);
            const curationDraft = {
              ...createModelCurationDraft(model),
              ...(modelCurationDrafts[model.id] || {}),
            };
            const isSaving = modelSavingId === draftKey || modelBulkSaving;
            const identityTargetModel = resolveAdminLookup(modelLookup, curationDraft.identity_target_lookup);
            const duplicateTargetModel = resolveAdminLookup(modelLookup, curationDraft.duplicate_target_lookup);
            const isIdentitySaving = modelCurationSavingId === `identity:${model.id}`;
            const isDuplicateSaving = modelCurationSavingId === `duplicate:${model.id}`;
            const originCountries = getModelOriginCountries(model);
            const inferenceCountries = getModelInferenceCountries(model);
            const selectedRouteSummary = hasSelectedInferenceRoute
              ? getModelInferenceRouteApprovalSummary(
                  model,
                  approvalUseCaseId,
                  approvalInferenceProviderFilter,
                  approvalInferenceLocationFilter,
                )
              : null;
            return (
              <div key={model.id} className="admin-row">
                <div className="admin-row-head">
                  <div className="admin-row-title">
                    <span className="title">{model.name}</span>
                    <ProviderBadge
                      countryCode={model.provider_country_code}
                      countryFlag={model.provider_country_flag}
                      countryName={model.provider_country_name}
                      provider={model.provider}
                    />
                    <CatalogStatusBadge model={model} />
                    {approval?.approved_for_use ? <span className="tag tag-approval">Approved</span> : <span className="tag">Not approved</span>}
                    <RecommendationBadge model={model} useCaseId={approvalUseCaseId} />
                    {model.family_name ? <span className="tag tag-family">{model.family_name}</span> : null}
                    {reviewSignal?.isReviewed === false ? <span className="tag">Unrated</span> : null}
                    {reviewSignal?.status === "suggested_approve" ? <span className="tag tag-approval-partial">Suggested approve</span> : null}
                    {reviewSignal?.status === "new_model" ? <span className="tag tag-warning">New model</span> : null}
                    {reviewSignal?.status === "reviewed_not_approved" ? <span className="tag">Reviewed not approved</span> : null}
                    {selectedRouteSummary ? (
                      <span className={selectedRouteSummary.className} title={selectedRouteSummary.title}>
                        {selectedRouteSummary.label}
                      </span>
                    ) : null}
                    {originCountries.map((country) => (
                      <span key={`${model.id}-origin-${country}`} className="tag">
                        Origin: {country}
                      </span>
                    ))}
                    {inferenceCountries.map((country) => (
                      <span key={`${model.id}-${country}`} className="tag">
                        {country}
                      </span>
                    ))}
                  </div>
                  <div className="hint">
                    {reviewSignal?.summary ? `${reviewSignal.summary} · ` : ""}
                    {approval?.approval_updated_at
                      ? `Last updated ${formatDate(approval.approval_updated_at)}`
                      : model.discovered_at
                        ? `Discovered ${formatDate(model.discovered_at)}`
                        : "No approval update yet"}
                  </div>
                </div>
                {selectedRouteSummary?.detail ? <div className="admin-subtle">{selectedRouteSummary.detail}</div> : null}
                <label className="checkbox-row">
                  <input
                    checked={Boolean(draft.approved_for_use)}
                    onChange={(event) => updateModelDraft(model.id, "approved_for_use", event.target.checked)}
                    type="checkbox"
                  />
                  <span>Approved for use</span>
                </label>
                <label className="field">
                  <span className="field-label">Recommendation</span>
                  <select
                    className="input select"
                    onChange={(event) => updateModelDraft(model.id, "recommendation_status", event.target.value)}
                    value={draft.recommendation_status || "unrated"}
                  >
                    {RECOMMENDATION_STATUS_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="field-label">Approval notes</span>
                  <textarea
                    className="input admin-textarea"
                    onChange={(event) => updateModelDraft(model.id, "approval_notes", event.target.value)}
                    placeholder="Optional notes about procurement, policy, or rollout constraints."
                    rows={3}
                    value={draft.approval_notes || ""}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Recommendation notes</span>
                  <textarea
                    className="input admin-textarea"
                    onChange={(event) => updateModelDraft(model.id, "recommendation_notes", event.target.value)}
                    placeholder="Why this is a default, fallback, or discouraged option for this lens."
                    rows={3}
                    value={draft.recommendation_notes || ""}
                  />
                </label>
                <div className="admin-bulk-editor">
                  <div className="detail-label">Catalog curation</div>
                  <div className="admin-subtle">
                    Use this when a variant landed in the wrong family or when this row is a duplicate of another exact model. These changes are remembered for future updates and DB rebuilds.
                  </div>
                  <div className="admin-grid admin-grid-two">
                    <div className="stack">
                      <label className="field">
                        <span className="field-label">Copy family from model</span>
                        <input
                          className="input"
                          onChange={(event) => updateModelCurationDraft(model.id, "identity_target_lookup", event.target.value)}
                          placeholder="Exact model id or name"
                          type="text"
                          value={curationDraft.identity_target_lookup || ""}
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">Variant label</span>
                        <input
                          className="input"
                          onChange={(event) => updateModelCurationDraft(model.id, "identity_variant_label", event.target.value)}
                          placeholder="Optional variant label"
                          type="text"
                          value={curationDraft.identity_variant_label || ""}
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">Family mapping notes</span>
                        <textarea
                          className="input admin-textarea"
                          onChange={(event) => updateModelCurationDraft(model.id, "identity_notes", event.target.value)}
                          placeholder="Why this exact model belongs in that family or canonical group."
                          rows={2}
                          value={curationDraft.identity_notes || ""}
                        />
                      </label>
                      <div className="admin-subtle">
                        {identityTargetModel === undefined
                          ? "Enter a target model id or name."
                          : identityTargetModel === null
                            ? "That lookup matches more than one model. Use the exact model id."
                            : identityTargetModel.id === model.id
                              ? "Choose a different model as the family reference."
                              : `Will copy ${identityTargetModel.family_name || "family"} / ${identityTargetModel.canonical_model_name || "canonical model"} from ${identityTargetModel.name}.`}
                      </div>
                      <div className="admin-actions admin-actions-start">
                        <button
                          className="btn btn-secondary"
                          disabled={
                            isIdentitySaving ||
                            !identityTargetModel ||
                            identityTargetModel === null ||
                            identityTargetModel.id === model.id
                          }
                          onClick={() => handleSaveModelIdentityCuration(model, identityTargetModel)}
                          type="button"
                        >
                          {isIdentitySaving ? "Saving family mapping…" : "Save family mapping"}
                        </button>
                      </div>
                    </div>
                    <div className="stack">
                      <label className="field">
                        <span className="field-label">Merge duplicate into model</span>
                        <input
                          className="input"
                          onChange={(event) => updateModelCurationDraft(model.id, "duplicate_target_lookup", event.target.value)}
                          placeholder="Canonical target id or name"
                          type="text"
                          value={curationDraft.duplicate_target_lookup || ""}
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">Duplicate merge notes</span>
                        <textarea
                          className="input admin-textarea"
                          onChange={(event) => updateModelCurationDraft(model.id, "duplicate_notes", event.target.value)}
                          placeholder="Why this row should redirect to the selected canonical model."
                          rows={2}
                          value={curationDraft.duplicate_notes || ""}
                        />
                      </label>
                      <div className="admin-subtle">
                        {duplicateTargetModel === undefined
                          ? "Pick the canonical exact model this duplicate should resolve to."
                          : duplicateTargetModel === null
                            ? "That lookup matches more than one model. Use the exact model id."
                            : duplicateTargetModel.id === model.id
                              ? "Choose a different canonical target."
                              : `This row will be merged into ${duplicateTargetModel.name} now, and future matches will resolve there automatically.`}
                      </div>
                      <div className="admin-actions admin-actions-start">
                        <button
                          className="btn btn-secondary"
                          disabled={
                            isDuplicateSaving ||
                            !duplicateTargetModel ||
                            duplicateTargetModel === null ||
                            duplicateTargetModel.id === model.id
                          }
                          onClick={() => handleMergeModelDuplicate(model, duplicateTargetModel)}
                          type="button"
                        >
                          {isDuplicateSaving ? "Merging duplicate…" : "Merge duplicate"}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="admin-actions">
                  <button
                    className="btn btn-secondary"
                    disabled={isSaving || !isModelDirty(model)}
                    onClick={() => handleSaveModel(model)}
                    type="button"
                  >
                    {isSaving ? "Saving…" : "Save review state"}
                  </button>
                </div>
              </div>
            );
          })}
          {!filteredModels.length ? <EmptyState message="No exact models match the current search." /> : null}
        </div>
      </article>
      ) : null}

      {showInternalWeightsSection ? (
      <article className="panel stack">
        <div className="panel-head">Internal View Weighting</div>
        <div className="admin-subtle">
          Internal View is an optional manual benchmark signal. Set its share for each lens here. Missing internal scores do not reduce eligibility coverage; they only affect score when present.
        </div>
        {!internalBenchmark ? (
          <EmptyState message="Internal benchmark is not available in the current catalog." />
        ) : (
          <>
          <div className="admin-toolbar">
            <label className="checkbox-row admin-checkbox-inline">
              <input
                checked={internalWeightChangedOnly}
                onChange={(event) => setInternalWeightChangedOnly(event.target.checked)}
                type="checkbox"
              />
              <span>Changed only</span>
            </label>
            <div className="admin-subtle">Showing {filteredUseCases.length} of {useCases.length} lenses.</div>
          </div>
          <div className="admin-bulk-editor">
            <div className="detail-label">Bulk paste internal weights</div>
            <div className="admin-subtle">Paste a lens id or lens label plus a percent in tab-separated columns. Blank percent clears the weight. Example: `coding` then tab then `10`.</div>
            <textarea
              className="input admin-textarea admin-bulk-textarea"
              onChange={(event) => setInternalWeightBulkText(event.target.value)}
              placeholder={`coding\t10\nrag_groundedness\t5`}
              rows={4}
              value={internalWeightBulkText}
            />
            <div className="admin-actions admin-actions-start">
              <button className="btn btn-secondary" onClick={handleApplyInternalWeightBulk} type="button">
                Apply to drafts
              </button>
              <button className="btn btn-ghost btn-inline" onClick={() => setInternalWeightBulkText("")} type="button">
                Clear pasted text
              </button>
            </div>
            {internalWeightBulkResult ? (
              <Banner
                tone={internalWeightBulkResult.tone}
                title={internalWeightBulkResult.title}
                message={internalWeightBulkResult.lines.join(" ")}
              />
            ) : null}
          </div>
          <div className="admin-list">
            {filteredUseCases.map((useCase) => {
              const draft = internalWeightDrafts[useCase.id] || {};
              const errors = internalWeightErrorsById[useCase.id] || [];
              const isSaving = internalWeightSavingId === useCase.id || internalWeightBulkSaving;
              return (
                <div key={useCase.id} className="admin-row">
                  <div className="admin-row-head">
                    <div className="admin-row-title">
                      <span className="title">{useCase.icon} {useCase.label}</span>
                      <span className="tag">{useCase.status === "preview" ? "Preview" : "Ready"}</span>
                    </div>
                    <div className="hint">Base min coverage {Math.round((useCase.min_coverage ?? 0.5) * 100)}%</div>
                  </div>
                  <div className="admin-grid admin-grid-two">
                    <label className="field">
                      <span className="field-label">Internal share %</span>
                      <input
                        className="input"
                        inputMode="decimal"
                        onChange={(event) => updateInternalWeightDraft(useCase.id, "weightPercent", event.target.value)}
                        placeholder="0"
                        type="text"
                        value={draft.weightPercent || ""}
                      />
                    </label>
                    <div className="admin-inline-note">
                      Current live share: {formatWeightPercentLabel(useCase.internal_view_weight)}.
                      {useCase.internal_view_weight > 0 ? ` ${internalBenchmark.short} is already blended into this lens.` : " Internal View is currently off for this lens."}
                    </div>
                  </div>
                  {errors.length ? (
                    <div className="admin-errors">
                      {errors.map((error) => (
                        <div key={error}>{error}</div>
                      ))}
                    </div>
                  ) : null}
                  <div className="admin-actions">
                    <button
                      className="btn btn-secondary"
                      disabled={isSaving || !isInternalWeightDirty(useCase) || errors.length > 0}
                      onClick={() => handleSaveInternalWeight(useCase)}
                      type="button"
                    >
                      {isSaving ? "Saving…" : "Save internal weight"}
                    </button>
                  </div>
                </div>
              );
            })}
            {!filteredUseCases.length ? <EmptyState message="No lenses match the current filter." /> : null}
          </div>
          </>
        )}
      </article>
      ) : null}

      {showInternalScoresSection ? (
      <article className="panel stack">
        <div className="panel-head">Internal View Scores</div>
        <div className="admin-subtle">
          Add or clear optional Internal View scores on exact models. Leave the value blank to remove the score for a model.
        </div>
        <div className="admin-toolbar">
          <label className="field">
            <span className="field-label">Search exact models for internal scoring</span>
            <input
              className="input"
              onChange={(event) => setInternalScoreSearch(event.target.value)}
              placeholder="Search exact models…"
              type="text"
              value={internalScoreSearch}
            />
          </label>
          <div aria-label="Internal score filter" className="toggle-group admin-filter-toggle" role="group">
            {INTERNAL_SCORE_FILTER_OPTIONS.map((option) => (
              <button
                key={option.id}
                className={internalScoreFilter === option.id ? "toggle-btn toggle-btn-active" : "toggle-btn"}
                onClick={() => setInternalScoreFilter(option.id)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <div className="admin-subtle">Showing {filteredInternalScoreModels.length} of {models.length} models. {scoredInternalCount} models already have an Internal View score.</div>
        <div className="admin-bulk-editor">
          <div className="detail-label">Bulk paste internal scores</div>
            <div className="admin-subtle">Paste a model id or exact model name, score, and optional notes in tab-separated columns. Blank score clears the internal value. Example: `gpt-5-4`, then tab, then `88`, then an optional note.</div>
          <textarea
            className="input admin-textarea admin-bulk-textarea"
            onChange={(event) => setInternalScoreBulkText(event.target.value)}
            placeholder={`gpt-5-4\t88\tPreferred for coding\nGemini 3.1 Pro Preview\t82\tStrong docs, weaker coding confidence`}
            rows={5}
            value={internalScoreBulkText}
          />
          <div className="admin-actions admin-actions-start">
            <button className="btn btn-primary" onClick={handleApplyInternalScoreBulk} type="button">
              Apply to drafts
            </button>
            <button className="btn btn-ghost btn-inline" onClick={() => setInternalScoreBulkText("")} type="button">
              Clear pasted text
            </button>
          </div>
          {internalScoreBulkResult ? (
            <Banner
              tone={internalScoreBulkResult.tone}
              title={internalScoreBulkResult.title}
              message={internalScoreBulkResult.lines.join(" ")}
            />
          ) : null}
        </div>
        <div className="admin-list">
          {filteredInternalScoreModels.map((model) => {
            const draft = internalScoreDrafts[model.id] || {};
            const score = model.scores?.[INTERNAL_VIEW_BENCHMARK_ID];
            const errors = internalScoreErrorsById[model.id] || [];
            const isSaving = internalScoreSavingId === model.id || internalScoreBulkSaving;
            return (
              <div key={model.id} className="admin-row">
                <div className="admin-row-head">
                  <div className="admin-row-title">
                    <span className="title">{model.name}</span>
                    <ProviderBadge
                      countryCode={model.provider_country_code}
                      countryFlag={model.provider_country_flag}
                      countryName={model.provider_country_name}
                      provider={model.provider}
                    />
                    {score?.value != null ? <span className="tag tag-approval">Internal score set</span> : <span className="tag">No internal score</span>}
                  </div>
                  <div className="hint">
                    {score?.collected_at ? `Last updated ${formatDate(score.collected_at)}` : "No internal score yet"}
                  </div>
                </div>
                <div className="admin-grid admin-grid-two">
                  <label className="field">
                    <span className="field-label">Internal score</span>
                    <input
                      className="input"
                      inputMode="decimal"
                      onChange={(event) => updateInternalScoreDraft(model.id, "value", event.target.value)}
                      placeholder="Blank = no score"
                      type="text"
                      value={draft.value || ""}
                    />
                  </label>
                  <div className="admin-inline-note">
                    {score?.value != null ? `Current live score: ${score.value}.` : "Current live score: none."}
                  </div>
                </div>
                <label className="field">
                  <span className="field-label">Internal notes</span>
                  <textarea
                    className="input admin-textarea"
                    onChange={(event) => updateInternalScoreDraft(model.id, "notes", event.target.value)}
                    placeholder="Optional notes about internal preference, rollout confidence, or operator feedback."
                    rows={3}
                    value={draft.notes || ""}
                  />
                </label>
                {errors.length ? (
                  <div className="admin-errors">
                    {errors.map((error) => (
                      <div key={error}>{error}</div>
                    ))}
                  </div>
                ) : null}
                <div className="admin-actions">
                  <button
                    className="btn btn-secondary"
                    disabled={isSaving || !isInternalScoreDirty(model) || errors.length > 0}
                    onClick={() => handleSaveInternalScore(model)}
                    type="button"
                  >
                    {isSaving ? "Saving…" : "Save internal score"}
                  </button>
                </div>
              </div>
            );
          })}
          {!filteredInternalScoreModels.length ? <EmptyState message="No exact models match the current search." /> : null}
        </div>
      </article>
      ) : null}
    </section>
  );
}

function countryFlagFromCode(countryCode) {
  if (!countryCode || String(countryCode).length !== 2) {
    return "";
  }
  return String(countryCode)
    .toUpperCase()
    .split("")
    .map((char) => String.fromCodePoint(127397 + char.charCodeAt(0)))
    .join("");
}

function getModelApprovalRecord(model, useCaseId) {
  if (!useCaseId) {
    return null;
  }
  return model?.use_case_approvals?.[useCaseId] || null;
}

function normalizeRecommendationStatus(value, { allowMixed = false } = {}) {
  const normalized = String(value || "").trim().toLowerCase();
  if (RECOMMENDATION_STATUS_OPTIONS.some((option) => option.id === normalized)) {
    return normalized;
  }
  if (allowMixed && normalized === "mixed") {
    return normalized;
  }
  return "unrated";
}

function getAgeDays(timestamp) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return null;
  }
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86400000));
}

function getLegacyAdvisoryMeta(model) {
  const releaseTimestamp = getPreciseReleaseTimestamp(model?.release_date);
  const releaseAgeDays = getAgeDays(releaseTimestamp);
  if (releaseAgeDays != null && releaseAgeDays >= AUTO_LEGACY_RELEASE_DAYS) {
    return {
      status: "legacy",
      label: "Legacy · consider newer",
      title: `Auto-derived because this model is ${releaseAgeDays} days old based on its exact release date. Consider a newer model unless you specifically need this one.`,
      source: "release",
      ageDays: releaseAgeDays,
    };
  }

  const openRouterAddedTimestamp = getTimestampOrZero(model?.openrouter_added_at);
  const openRouterAgeDays = getAgeDays(openRouterAddedTimestamp);
  if (openRouterAgeDays != null && openRouterAgeDays >= AUTO_LEGACY_OPENROUTER_DAYS) {
    return {
      status: "legacy",
      label: "Legacy · consider newer",
      title: `Auto-derived because this model was first added to OpenRouter ${openRouterAgeDays} days ago. Consider a newer model unless you specifically need this one.`,
      source: "openrouter",
      ageDays: openRouterAgeDays,
    };
  }

  return null;
}

function getLegacyAdvisorySummary(model, memberModels = null) {
  const relatedModels = Array.isArray(memberModels) ? memberModels.filter(Boolean) : [];
  if (relatedModels.length) {
    const legacyModels = relatedModels.filter((entry) => getLegacyAdvisoryMeta(entry));
    if (!legacyModels.length) {
      return null;
    }
    const totalCount = relatedModels.length;
    if (legacyModels.length === totalCount) {
      return {
        className: "tag tag-legacy",
        label: totalCount > 1 ? "Legacy family" : "Legacy · consider newer",
        title: `All ${totalCount} variant${totalCount === 1 ? "" : "s"} in this family are older than one year or have been on OpenRouter for over a year. Consider newer alternatives first.`,
      };
    }
    return {
      className: "tag tag-legacy",
      label: `${legacyModels.length}/${totalCount} legacy variants`,
      title: `${legacyModels.length} of ${totalCount} variants in this family are older than one year or have been on OpenRouter for over a year. Consider newer alternatives first.`,
    };
  }

  const legacyMeta = getLegacyAdvisoryMeta(model);
  if (!legacyMeta) {
    return null;
  }
  return {
    className: "tag tag-legacy",
    label: legacyMeta.label,
    title: legacyMeta.title,
  };
}

function getLegacyAdvisoryInline(model, memberModels = null) {
  const relatedModels = Array.isArray(memberModels) ? memberModels.filter(Boolean) : [];
  if (relatedModels.length) {
    const legacyModels = relatedModels.filter((entry) => getLegacyAdvisoryMeta(entry));
    if (!legacyModels.length || legacyModels.length !== relatedModels.length) {
      return null;
    }
    return {
      headline: "Legacy family.",
      body: "All tracked variants are legacy. Prefer a newer option unless you specifically need this family.",
      title: `All ${relatedModels.length} tracked variant${relatedModels.length === 1 ? "" : "s"} in this family meet the legacy advisory.`,
    };
  }

  const legacyMeta = getLegacyAdvisoryMeta(model);
  if (!legacyMeta) {
    return null;
  }
  return {
    headline: "Legacy model.",
    body: "Prefer a newer option unless you specifically need this one.",
    title: legacyMeta.title,
  };
}

function getRecommendationBreakdown(model, useCaseId) {
  if (!useCaseId) {
    return {
      status: "unrated",
      totalCount: 1,
      recommendedCount: 0,
      notRecommendedCount: 0,
      discouragedCount: 0,
      approval: null,
    };
  }

  const approval = getModelApprovalRecord(model, useCaseId);
  const recommendationStatus = normalizeRecommendationStatus(approval?.recommendation_status, { allowMixed: true });
  const totalCount = Math.max(1, Number(approval?.approval_total_count ?? 1));
  const recommendedCount = Number(
    approval?.recommended_member_count ?? (recommendationStatus === "recommended" ? 1 : 0),
  );
  const notRecommendedCount = Number(
    approval?.not_recommended_member_count ?? (recommendationStatus === "not_recommended" ? 1 : 0),
  );
  const discouragedCount = Number(
    approval?.discouraged_member_count ?? (recommendationStatus === "discouraged" ? 1 : 0),
  );
  const hasManualSignal =
    recommendationStatus === "mixed" ||
    recommendedCount > 0 ||
    notRecommendedCount > 0 ||
    discouragedCount > 0;

  if (hasManualSignal) {
    return {
      status: recommendationStatus,
      totalCount,
      recommendedCount,
      notRecommendedCount,
      discouragedCount,
      approval,
    };
  }

  return {
    status: "unrated",
    totalCount,
    recommendedCount: 0,
    notRecommendedCount: 0,
    discouragedCount: 0,
    approval,
  };
}

function formatRecommendationStatusLabel(status) {
  switch (normalizeRecommendationStatus(status, { allowMixed: true })) {
    case "recommended":
      return "Recommended";
    case "not_recommended":
      return "Not recommended";
    case "discouraged":
      return "Discouraged";
    case "mixed":
      return "Mixed recommendation";
    default:
      return "Unrated";
  }
}

function isModelApprovedForUseCase(model, useCaseId, routeContext = null) {
  if (useCaseId) {
    const approval = getModelApprovalRecord(model, useCaseId);
    const baseApproved = Boolean(approval?.approved_for_use);
    if (!baseApproved) {
      return false;
    }

    const routeEntries = approval?.inference_route_approvals || [];
    if (!routeEntries.length) {
      return true;
    }

    const destinationId = String(routeContext?.destinationId || "").trim();
    const locationKey = buildInferenceLocationKey(routeContext?.locationLabel || "");
    if (!destinationId && !locationKey) {
      return true;
    }

    const matchingEntries = routeEntries.filter((entry) => {
      if (destinationId && entry?.destination_id !== destinationId) {
        return false;
      }
      if (locationKey && entry?.location_key !== locationKey) {
        return false;
      }
      return true;
    });
    if (matchingEntries.length) {
      return matchingEntries.some((entry) => Boolean(entry?.approved_for_use));
    }
    return false;
  }
  return Boolean(model?.approved_for_use);
}

function matchesRecommendationFilter(model, useCaseId, filterValue) {
  if (!useCaseId || filterValue === DEFAULT_RECOMMENDATION_FILTER) {
    return true;
  }

  const { recommendedCount, notRecommendedCount, discouragedCount } = getRecommendationBreakdown(model, useCaseId);
  const hasAutoNotRecommended = recommendedCount === 0 &&
    notRecommendedCount === 0 &&
    discouragedCount === 0 &&
    Boolean(getLegacyAdvisoryMeta(model));

  if (filterValue === "recommended") {
    return recommendedCount > 0;
  }
  if (filterValue === "not_recommended") {
    return notRecommendedCount > 0 || hasAutoNotRecommended;
  }
  if (filterValue === "discouraged") {
    return discouragedCount > 0;
  }
  return recommendedCount === 0 && notRecommendedCount === 0 && discouragedCount === 0 && !hasAutoNotRecommended;
}

function getApprovalSummary(model, useCaseId) {
  if (useCaseId) {
    const approval = getModelApprovalRecord(model, useCaseId);
    const approvedCount = Number(approval?.approval_member_count ?? (approval?.approved_for_use ? 1 : 0));
    const totalCount = Number(approval?.approval_total_count ?? 1);
    if (!approvedCount) {
      return null;
    }
    if (totalCount > 1 && approvedCount < totalCount) {
      return {
        className: "tag tag-approval-partial",
        label: `${approvedCount}/${totalCount} approved`,
      };
    }
    return {
      className: "tag tag-approval",
      label: totalCount > 1 ? `${approvedCount}/${totalCount} approved` : "Approved",
    };
  }

  const useCaseCount = Number(model?.approval_use_case_count ?? (model?.approved_for_use ? 1 : 0));
  if (!useCaseCount) {
    return null;
  }
  return {
    className: "tag tag-approval",
    label: useCaseCount > 1 ? `Approved in ${useCaseCount} lenses` : "Approved",
  };
}

function ApprovalBadge({ model, useCaseId = "" }) {
  const summary = getApprovalSummary(model, useCaseId);
  if (!summary) {
    return null;
  }
  return <span className={summary.className}>{summary.label}</span>;
}

function getRecommendationSummary(model, useCaseId) {
  if (!useCaseId) {
    return null;
  }
  const {
    approval,
    discouragedCount,
    notRecommendedCount,
    recommendedCount,
    status: recommendationStatus,
    totalCount,
  } = getRecommendationBreakdown(model, useCaseId);

  if (recommendationStatus === "mixed") {
    const details = [
      recommendedCount ? `${recommendedCount} recommended` : "",
      notRecommendedCount ? `${notRecommendedCount} not recommended` : "",
      discouragedCount ? `${discouragedCount} discouraged` : "",
    ]
      .filter(Boolean)
      .join(" · ");
    return {
      className: "tag tag-approval-partial",
      label: "Mixed recommendation",
      railLabel: getDashboardRailLabel("mixed"),
      status: "mixed",
      title: details || "Mixed recommendation state",
    };
  }

  if (recommendationStatus === "recommended") {
    return {
      className: "tag tag-approval",
      label: totalCount > 1 && recommendedCount < totalCount ? `${recommendedCount}/${totalCount} recommended` : "Recommended",
      railLabel: getDashboardRailLabel("recommended"),
      status: "recommended",
      title: approval?.recommendation_notes || "Recommended for this lens",
    };
  }
  if (recommendationStatus === "not_recommended") {
    return {
      className: "tag tag-not-recommended",
      label: totalCount > 1 && notRecommendedCount < totalCount ? `${notRecommendedCount}/${totalCount} not recommended` : "Not recommended",
      railLabel: getDashboardRailLabel("not_recommended"),
      status: "not_recommended",
      title: approval?.recommendation_notes || "Approved but not a default recommendation",
    };
  }
  if (recommendationStatus === "discouraged") {
    return {
      className: "tag tag-warning",
      label: totalCount > 1 && discouragedCount < totalCount ? `${discouragedCount}/${totalCount} discouraged` : "Discouraged",
      railLabel: getDashboardRailLabel("discouraged"),
      status: "discouraged",
      title: approval?.recommendation_notes || "Discouraged for this lens",
    };
  }
  const legacyMeta = getLegacyAdvisoryMeta(model);
  if (legacyMeta) {
    return {
      auto: true,
      className: "tag tag-not-recommended",
      label: "Not recommended",
      railLabel: getDashboardRailLabel("not_recommended"),
      status: "not_recommended",
      title: legacyMeta.title,
    };
  }
  return {
    className: "tag tag-detail",
    label: "Unrated",
    railLabel: getDashboardRailLabel("unrated"),
    status: "unrated",
    title: "No recommendation has been saved for this lens yet.",
  };
}

function RecommendationBadge({ model, useCaseId = "" }) {
  const summary = getRecommendationSummary(model, useCaseId);
  if (!summary || summary.status === "unrated") {
    return null;
  }
  return (
    <span className={summary.className} title={summary.title}>
      {summary.label}
    </span>
  );
}

function RecommendationRail({ summary }) {
  if (!summary) {
    return null;
  }
  return (
    <div className={`card-status-rail card-status-rail-${summary.status}`} title={summary.title}>
      <span className="card-status-rail-text">{summary.railLabel || summary.label}</span>
      {summary.auto ? <span className="card-status-rail-auto">Auto</span> : null}
    </div>
  );
}

function LegacyAdvisoryBadge({ model, memberModels = null }) {
  const summary = getLegacyAdvisorySummary(model, memberModels);
  if (!summary) {
    return null;
  }
  return (
    <span className={summary.className} title={summary.title}>
      {summary.label}
    </span>
  );
}

function CatalogStatusBadge({ model }) {
  if (String(model?.catalog_status || "") !== "provisional") {
    return null;
  }
  return <span className="tag tag-provisional">OpenRouter provisional</span>;
}

function ProviderBadge({ provider, countryCode, countryFlag, countryName }) {
  const tone = PROVIDER_COLORS[provider]?.tone || PROVIDER_COLORS.default.tone;
  const label = countryFlag ? `${countryFlag} ${provider}` : provider;
  const title = countryName
    ? `Provider origin: ${countryName}${countryCode ? ` (${countryCode})` : ""}`
    : provider;
  return <span className={`badge badge-${tone}`} title={title}>{label}</span>;
}

function SourceBadge({ score }) {
  if (!score) {
    return null;
  }

  if (score.source_type === "manual") {
    return <span className="source-badge source-badge-manual">MANUAL</span>;
  }

  if (score.source_type === "secondary") {
    return <span className="source-badge source-badge-secondary">SECONDARY</span>;
  }

  return score.verified ? <span className="source-badge source-badge-verified">VERIFIED</span> : null;
}

function TypeBadge({ type }) {
  return type === "open_weights" ? <span className="badge badge-indigo">Open weights</span> : <span className="badge badge-slate">Proprietary</span>;
}

function CoverageIndicator({ coverage }) {
  const safeCoverage = Math.max(0, Math.min(100, Math.round(coverage * 100)));
  const tone = safeCoverage >= 70 ? "good" : safeCoverage >= 40 ? "warn" : "muted";
  return (
    <div className="coverage-row">
      <div className="coverage-track">
        <div className={`coverage-fill coverage-${tone}`} style={{ width: `${safeCoverage}%` }} />
      </div>
      <span className="coverage-label">{safeCoverage}% data</span>
    </div>
  );
}

function ScoreBar({ score }) {
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const tone = value >= 75 ? "good" : value >= 50 ? "warn" : "bad";
  return (
    <div className="score-row">
      <div className="score-track">
        <div className={`score-fill score-${tone}`} style={{ width: `${value}%` }} />
      </div>
      <span className={`score-value score-${tone}`}>{value}</span>
    </div>
  );
}

function normalizeOriginCountryEntry(country) {
  if (!country) {
    return null;
  }
  const code = String(country.code || "")
    .trim()
    .toUpperCase();
  const name = String(country.name || "").trim();
  if (!code && !name) {
    return null;
  }
  return {
    code: code || null,
    name: name || code,
  };
}

function normalizeOriginCountries(countries) {
  const normalized = [];
  const seen = new Set();
  (Array.isArray(countries) ? countries : []).forEach((country) => {
    const next = normalizeOriginCountryEntry(country);
    if (!next) {
      return;
    }
    const key = `${next.code || ""}|${String(next.name || "").toLowerCase()}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    normalized.push(next);
  });
  return normalized;
}

function summarizeOriginCountries(countries) {
  return normalizeOriginCountries(countries)
    .map((country) => country.name)
    .filter(Boolean)
    .join(", ");
}

function getModelOriginCountries(model) {
  const normalized = normalizeOriginCountries(model?.provider_origin_countries);
  if (normalized.length) {
    return normalized
      .map((country) => String(country.name || "").trim())
      .filter(Boolean)
      .sort((left, right) => left.localeCompare(right));
  }
  const fallback = String(model?.provider_country_name || "").trim();
  return fallback ? [fallback] : [];
}

function formatOriginCountriesInput(countries, fallbackCountryCode = "", fallbackCountryName = "") {
  const normalized = normalizeOriginCountries(countries);
  if (normalized.length) {
    return normalized
      .map((country) => (country.code ? `${country.code} | ${country.name}` : country.name))
      .join("\n");
  }
  const code = String(fallbackCountryCode || "")
    .trim()
    .toUpperCase();
  const name = String(fallbackCountryName || "").trim();
  if (!code && !name) {
    return "";
  }
  return code ? `${code} | ${name || code}` : name;
}

function parseOriginCountriesInput(value) {
  const countries = [];
  const errors = [];
  const seen = new Set();
  const lines = String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  lines.forEach((line, index) => {
    const lineNumber = index + 1;
    const parts = line.split("|").map((part) => part.trim());
    if (parts.length > 2) {
      errors.push(`Origin countries line ${lineNumber} must use either "CODE | Country" or "Country".`);
      return;
    }
    const rawCode = parts.length === 2 ? parts[0] : "";
    const rawName = parts.length === 2 ? parts[1] : parts[0];
    const code = rawCode.toUpperCase();
    const name = rawName.trim();
    if (code && !/^[A-Z]{2}$/.test(code)) {
      errors.push(`Origin countries line ${lineNumber} must use a two-letter ISO code.`);
      return;
    }
    if (!name) {
      errors.push(`Origin countries line ${lineNumber} must include a country name.`);
      return;
    }
    const key = `${code}|${name.toLowerCase()}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    countries.push({ code: code || null, name });
  });

  return { countries, errors };
}

function createProviderDraft(provider) {
  const originCountriesInput = formatOriginCountriesInput(
    provider.origin_countries,
    provider.country_code,
    provider.country_name,
  );
  return {
    country_code: provider.country_code || "",
    country_name: provider.country_name || "",
    origin_countries_input: originCountriesInput,
    origin_basis: provider.origin_basis || "",
    source_url: provider.source_url || "",
    verified_at: provider.verified_at || "",
  };
}

function buildModelApprovalDraftKey(modelId, useCaseId) {
  return `${modelId}::${useCaseId}`;
}

function parseModelApprovalDraftKey(key) {
  const separatorIndex = String(key || "").indexOf("::");
  if (separatorIndex < 0) {
    return { modelId: String(key || ""), useCaseId: "" };
  }
  return {
    modelId: key.slice(0, separatorIndex),
    useCaseId: key.slice(separatorIndex + 2),
  };
}

function createModelDraft(model, useCaseId = "") {
  const approval = getModelApprovalRecord(model, useCaseId);
  return {
    approved_for_use: Boolean(approval?.approved_for_use),
    approval_notes: approval?.approval_notes || "",
    recommendation_status: approval?.recommendation_status || "unrated",
    recommendation_notes: approval?.recommendation_notes || "",
  };
}

function createModelCurationDraft(model) {
  return {
    identity_target_lookup: "",
    identity_variant_label: model?.variant_label || "",
    identity_notes: "",
    duplicate_target_lookup: "",
    duplicate_notes: "",
  };
}

function parseAuditSummaryPayload(value) {
  if (!value) {
    return {};
  }
  if (typeof value === "object") {
    return value;
  }
  try {
    const parsed = JSON.parse(String(value));
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function buildApprovalReviewSignals(models, useCaseId) {
  if (!useCaseId) {
    return {};
  }

  const approvedCanonicalCounts = {};
  const approvedFamilyCounts = {};

  models.forEach((model) => {
    if (!isModelApprovedForUseCase(model, useCaseId)) {
      return;
    }
    if (model.canonical_model_id) {
      approvedCanonicalCounts[model.canonical_model_id] = (approvedCanonicalCounts[model.canonical_model_id] || 0) + 1;
    }
    if (model.family_id) {
      approvedFamilyCounts[model.family_id] = (approvedFamilyCounts[model.family_id] || 0) + 1;
    }
  });

  return Object.fromEntries(
    models.map((model) => {
      const approval = getModelApprovalRecord(model, useCaseId);
      const isReviewed = Boolean(approval);
      const isNewlyDiscovered = Boolean(model.discovered_update_log_id);
      const canonicalApprovedCount = Math.max(
        0,
        Number(approvedCanonicalCounts[model.canonical_model_id] || 0) - (approval?.approved_for_use ? 1 : 0),
      );
      const familyApprovedCount = Math.max(
        0,
        Number(approvedFamilyCounts[model.family_id] || 0) - (approval?.approved_for_use ? 1 : 0),
      );

      let status = "unrated";
      let summary = "No review saved yet for this lens.";
      if (approval?.approved_for_use) {
        status = "approved";
        summary = "";
      } else if (isReviewed) {
        status = "reviewed_not_approved";
        summary = "Already reviewed for this lens and left unapproved.";
      } else if (isNewlyDiscovered && canonicalApprovedCount > 0) {
        status = "suggested_approve";
        summary = `Newly discovered. ${canonicalApprovedCount} approved canonical sibling${canonicalApprovedCount === 1 ? "" : "s"} already exist.`;
      } else if (isNewlyDiscovered && familyApprovedCount > 0) {
        status = "suggested_approve";
        summary = `Newly discovered. ${familyApprovedCount} approved family member${familyApprovedCount === 1 ? "" : "s"} already exist.`;
      } else if (isNewlyDiscovered) {
        status = "new_model";
        summary = "Newly discovered. Needs first review for this lens.";
      }

      return [
        model.id,
        {
          status,
          summary,
          isReviewed,
          isNewlyDiscovered,
          needsReview: !isReviewed && isNewlyDiscovered,
          canApplyFamilyDelta: !isReviewed && isNewlyDiscovered && familyApprovedCount > 0,
          canonicalApprovedCount,
          familyApprovedCount,
        },
      ];
    }),
  );
}

function buildApprovalFamilyOptions(models) {
  return Array.from(
    new Map(
      models
        .filter((model) => model.family_id)
        .map((model) => [
          model.family_id,
          {
            id: model.family_id,
            label: model.family_name || model.family_id,
            provider: model.provider || "",
            count: 0,
          },
        ]),
    ).values(),
  )
    .map((family) => {
      const familyModels = models.filter((model) => model.family_id === family.id);
      return {
        ...family,
        ...aggregateOpenRouterSignals(familyModels),
        count: familyModels.length,
      };
    })
    .sort(compareOpenRouterFamilyFilterOption);
}

function createInternalWeightDraft(useCase) {
  return {
    weightPercent: formatWeightPercentInput(useCase?.internal_view_weight),
  };
}

function createInternalScoreDraft(model) {
  const score = model?.scores?.[INTERNAL_VIEW_BENCHMARK_ID];
  return {
    value: score?.value != null ? String(score.value) : "",
    notes: score?.notes || "",
  };
}

function formatWeightPercentInput(value) {
  if (value == null || Number(value) === 0) {
    return "";
  }
  return String(Math.round(Number(value) * 1000) / 10);
}

function formatWeightPercentLabel(value) {
  return `${formatWeightPercentInput(value) || "0"}%`;
}

function parsePercentInputToShare(value) {
  const numericValue = parseOptionalNumber(value);
  if (numericValue == null) {
    return 0;
  }
  return Math.max(0, Math.min(1, numericValue / 100));
}

function parseOptionalNumber(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function getInternalWeightValidationErrors(useCase, draft) {
  const next = {
    ...createInternalWeightDraft(useCase),
    ...(draft || {}),
  };
  const errors = [];
  if (next.weightPercent && parseOptionalNumber(next.weightPercent) == null) {
    errors.push("Internal share must be a valid number.");
  } else if (parseOptionalNumber(next.weightPercent) != null) {
    const numericValue = Number(next.weightPercent);
    if (numericValue < 0 || numericValue > 100) {
      errors.push("Internal share must be between 0 and 100.");
    }
  }
  return errors;
}

function getInternalScoreValidationErrors(draft) {
  const next = {
    value: "",
    notes: "",
    ...(draft || {}),
  };
  const errors = [];
  if (next.value && parseOptionalNumber(next.value) == null) {
    errors.push("Internal score must be a valid number or left blank.");
  }
  return errors;
}

function buildAdminLookupIndex(items, getLookupValues) {
  const index = new Map();
  items.forEach((item) => {
    getLookupValues(item).forEach((value) => {
      const normalized = slugifyText(value);
      if (!normalized) {
        return;
      }
      if (!index.has(normalized)) {
        index.set(normalized, item);
        return;
      }
      if (index.get(normalized) !== item) {
        index.set(normalized, null);
      }
    });
  });
  return index;
}

function resolveAdminLookup(index, rawValue) {
  const normalized = slugifyText(rawValue);
  if (!normalized) {
    return undefined;
  }
  return index.get(normalized);
}

function parseBulkEditorRows(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((rawLine, index) => {
      const trimmed = rawLine.trim();
      if (!trimmed) {
        return null;
      }
      const delimiter = trimmed.includes("\t") ? "\t" : ",";
      return {
        lineNumber: index + 1,
        delimiter,
        cells: trimmed.split(delimiter).map((cell) => cell.trim()),
      };
    })
    .filter(Boolean);
}

function normalizePercentInput(value) {
  return String(value || "")
    .trim()
    .replace(/%$/, "");
}

function normalizeOptionalNumberInput(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "";
  }
  const parsed = parseOptionalNumber(normalized);
  return parsed == null ? normalized : String(parsed);
}

function isBulkWeightHeaderRow(cells) {
  const first = slugifyText(cells[0]);
  const second = slugifyText(cells[1]);
  return (
    new Set(["lens", "use-case", "use-case-id", "usecase", "usecase-id", "label"]).has(first) ||
    new Set(["weight", "internal-share", "share", "percent", "weight-percent"]).has(second)
  );
}

function isBulkScoreHeaderRow(cells) {
  const first = slugifyText(cells[0]);
  const second = slugifyText(cells[1]);
  return (
    new Set(["model", "model-id", "name", "id"]).has(first) ||
    new Set(["score", "internal-score", "value"]).has(second)
  );
}

function getLensEligibilitySummary(model, selectedUseCase, benchmarksById) {
  if (!selectedUseCase) {
    return null;
  }

  const weights = Object.entries(selectedUseCase.weights || {});
  const totalCoverageWeight = weights.reduce(
    (sum, [benchmarkId, weight]) => (benchmarkId === INTERNAL_VIEW_BENCHMARK_ID ? sum : sum + Number(weight || 0)),
    0,
  );
  let availableCoverageWeight = 0;
  let availableScoreWeight = 0;
  const missingRequired = [];
  const missingOptional = [];

  weights.forEach(([benchmarkId, weight]) => {
    const numericWeight = Number(weight || 0);
    const hasScore = model?.scores?.[benchmarkId]?.value != null;
    if (hasScore) {
      availableScoreWeight += numericWeight;
      if (benchmarkId !== INTERNAL_VIEW_BENCHMARK_ID) {
        availableCoverageWeight += numericWeight;
      }
      return;
    }

    if ((selectedUseCase.required_benchmarks || []).includes(benchmarkId)) {
      missingRequired.push(benchmarkId);
    } else {
      missingOptional.push(benchmarkId);
    }
  });

  const coverage = totalCoverageWeight <= 0 ? 1 : availableCoverageWeight / totalCoverageWeight;
  const minCoverage = Number(selectedUseCase.min_coverage ?? 0.5);
  const missingRequiredLabels = missingRequired.map((benchmarkId) => benchmarksById[benchmarkId]?.short || benchmarkId);
  const missingOptionalLabels = missingOptional
    .filter((benchmarkId) => benchmarkId !== INTERNAL_VIEW_BENCHMARK_ID)
    .map((benchmarkId) => benchmarksById[benchmarkId]?.short || benchmarkId);

  if (missingRequiredLabels.length) {
    return {
      status: "missing_required",
      badgeLabel: "Missing required evidence",
      inlineLabel: `Missing ${missingRequiredLabels.join(", ")}`,
      detailMessage: `It is missing the required benchmark evidence for this lens: ${missingRequiredLabels.join(", ")}.`,
    };
  }

  if (availableScoreWeight <= 0) {
    return {
      status: "no_relevant_data",
      badgeLabel: "No lens evidence",
      inlineLabel: `No scores yet for ${selectedUseCase.label}`,
      detailMessage: `It does not have any scores yet on the benchmarks used by this lens.`,
    };
  }

  if (coverage < minCoverage) {
    const detailSuffix = missingOptionalLabels.length ? ` Missing non-internal evidence: ${missingOptionalLabels.join(", ")}.` : "";
    return {
      status: "low_coverage",
      badgeLabel: "Coverage too low",
      inlineLabel: `${Math.round(coverage * 100)}% of required coverage`,
      detailMessage: `It only covers ${Math.round(coverage * 100)}% of the non-internal evidence stack, but this lens requires ${Math.round(
        minCoverage * 100,
      )}%.${detailSuffix}`,
    };
  }

  return {
    status: "eligible_unranked",
    badgeLabel: `Not ranked in ${selectedUseCase.label}`,
    inlineLabel: "This exact variant is not surfaced in the current ranked set",
    detailMessage: "This exact variant is not surfaced as its own ranked row in the current view.",
  };
}

function getProviderValidationErrors(provider, draft) {
  const next = {
    ...createProviderDraft(provider),
    ...(draft || {}),
  };
  const errors = [];
  const parsedOriginCountries = parseOriginCountriesInput(next.origin_countries_input || "");

  if (next.country_code && !/^[A-Z]{2}$/.test(next.country_code)) {
    errors.push("Country code must use a two-letter ISO code.");
  }
  errors.push(...parsedOriginCountries.errors);
  if (next.source_url && !isValidUrl(next.source_url)) {
    errors.push("Source URL must be a valid absolute URL.");
  }
  if (next.verified_at && !isValidDateString(next.verified_at)) {
    errors.push("Verified at must be a valid date and time.");
  }

  return errors;
}

function isValidUrl(value) {
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}

function isValidDateString(value) {
  return !Number.isNaN(Date.parse(String(value)));
}

function formatDateTimeLocalInput(value) {
  if (!value) {
    return "";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }

  return [
    parsed.getFullYear(),
    padDateSegment(parsed.getMonth() + 1),
    padDateSegment(parsed.getDate()),
  ].join("-") + `T${padDateSegment(parsed.getHours())}:${padDateSegment(parsed.getMinutes())}`;
}

function parseDateTimeLocalInput(value) {
  if (!value) {
    return "";
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

function padDateSegment(value) {
  return String(value).padStart(2, "0");
}

function Banner({ message, tone, title }) {
  return (
    <div className={tone === "error" ? "banner banner-error" : "banner banner-info"}>
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}

function UpdateProgressPanel({ updateState }) {
  const progressSteps = Array.isArray(updateState.progressSteps) ? updateState.progressSteps : [];
  const currentStep =
    progressSteps.find((step) => step.status === "running")
    || progressSteps.find((step) => step.key === updateState.currentStepKey)
    || null;
  const finishedSteps = Number(updateState.finishedSteps || 0);
  const totalSteps = Number(updateState.totalSteps || progressSteps.length || 0);
  const progressPercent = Math.max(0, Math.min(100, Number(updateState.progressPercent || 0)));
  const elapsedLabel = formatElapsedTime(updateState.startedAt, updateState.completedAt);

  return (
    <section className="panel update-progress-panel">
      <div className="update-progress-header">
        <div>
          <div className="panel-head">
            {updateState.status === "running"
              ? "Update in progress"
              : updateState.status === "failed"
                ? "Update failed"
                : "Update complete"}
          </div>
          <p className="panel-copy">
            {currentStep ? `Current step: ${currentStep.label}` : updateState.message || "Preparing update plan..."}
          </p>
        </div>
        <div className="update-progress-metrics">
          <div className="finder-metric">
            <strong>{totalSteps ? `${finishedSteps}/${totalSteps}` : "—"}</strong>
            <span>steps finished</span>
          </div>
          <div className="finder-metric">
            <strong>{Math.round(progressPercent)}%</strong>
            <span>progress</span>
          </div>
          <div className="finder-metric">
            <strong>{elapsedLabel}</strong>
            <span>{updateState.status === "running" ? "elapsed" : "duration"}</span>
          </div>
        </div>
      </div>

      <div aria-hidden="true" className="update-progress-bar">
        <div className="update-progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      <div className="update-progress-steps">
        {progressSteps.map((step) => (
          <div
            key={step.key}
            className={`update-progress-step update-progress-step-${step.status || "pending"}`}
          >
            <div className="update-progress-step-main">
              <div className="update-progress-step-label">{step.label}</div>
              <div className="update-progress-step-meta">
                {step.detail || step.records_found != null
                  ? `${step.detail || "phase"}${step.records_found != null ? ` · ${step.records_found} records` : ""}`
                  : step.kind === "source"
                    ? "source ingestion"
                    : "catalog phase"}
              </div>
              {step.error_message ? <div className="history-source-error">{step.error_message}</div> : null}
            </div>
            <span
              className={
                step.status === "completed"
                  ? "pill pill-good"
                  : step.status === "failed"
                    ? "pill pill-bad"
                    : step.status === "running"
                      ? "pill"
                      : "pill pill-muted"
              }
            >
              {step.status}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function LoadingState() {
  return (
    <div className="loading">
      <div className="loading-card" />
      <div className="loading-card" />
      <div className="loading-card" />
    </div>
  );
}

function EmptyState({ message }) {
  return <div className="empty">{message}</div>;
}

function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  const hasLensParam = params.has("lens");
  const lensParam = params.get("lens");
  const lens =
    !hasLensParam
      ? DASHBOARD_DEFAULT_LENS
      : lensParam === DASHBOARD_EMPTY_LENS_QUERY_VALUE
        ? ""
        : String(lensParam || "");
  const recommendationParam = params.get("recommendation");
  return {
    approvedOnly: params.get("approved") === "1",
    compare: splitCsv(params.get("compare")),
    expandedModelId: params.get("expanded") || "",
    historyLogId: parseIntegerParam(params.get("history")),
    inferenceLocation: params.get("inferenceLocation") || DEFAULT_INFERENCE_LOCATION_FILTER,
    lens,
    mode: params.has("mode") ? sanitizeCatalogMode(params.get("mode")) : DASHBOARD_DEFAULT_CATALOG_MODE,
    onlyCompared: params.get("onlyCompared") === "1",
    provider: params.get("provider") || "All",
    query: params.get("q") || "",
    recommendation: recommendationParam
      ? sanitizeRecommendationFilter(recommendationParam)
      : getDashboardBaselineRecommendationFilter(lens),
    sort: sanitizeBrowserSort(params.get("sort")),
    tab: params.has("tab") ? sanitizeTab(params.get("tab")) : DASHBOARD_DEFAULT_TAB,
    type: VALID_MODEL_TYPES.has(params.get("type")) ? params.get("type") : "All",
  };
}

function buildUrlStateHref(state) {
  const params = new URLSearchParams();

  if (state.tab && state.tab !== DASHBOARD_DEFAULT_TAB) params.set("tab", state.tab);
  if (state.mode && state.mode !== DASHBOARD_DEFAULT_CATALOG_MODE) params.set("mode", state.mode);
  if (state.lens === "") {
    params.set("lens", DASHBOARD_EMPTY_LENS_QUERY_VALUE);
  } else if (state.lens && state.lens !== DASHBOARD_DEFAULT_LENS) {
    params.set("lens", state.lens);
  }
  if (state.query) params.set("q", state.query);
  if (state.inferenceLocation && state.inferenceLocation !== DEFAULT_INFERENCE_LOCATION_FILTER) {
    params.set("inferenceLocation", state.inferenceLocation);
  }
  if (state.provider && state.provider !== "All") params.set("provider", state.provider);
  if (state.type && state.type !== "All") params.set("type", state.type);
  if (state.approvedOnly) params.set("approved", "1");
  if (state.recommendation && state.recommendation !== getDashboardBaselineRecommendationFilter(state.lens)) {
    params.set("recommendation", state.recommendation);
  }
  if (state.sort && state.sort !== "smart") params.set("sort", state.sort);
  if (state.compare?.length) params.set("compare", state.compare.join(","));
  if (state.expandedModelId) params.set("expanded", state.expandedModelId);
  if (state.historyLogId) params.set("history", String(state.historyLogId));
  if (state.onlyCompared) params.set("onlyCompared", "1");

  const nextQuery = params.toString();
  return nextQuery ? `${window.location.pathname}?${nextQuery}` : window.location.pathname;
}

function writeUrlState(state) {
  const nextUrl = buildUrlStateHref(state);
  window.history.replaceState(null, "", nextUrl);
}

function splitCsv(value) {
  return String(value || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function parseIntegerParam(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) ? numeric : null;
}

function shouldHandleClientNavigation(event) {
  return !(
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.altKey ||
    event.ctrlKey ||
    event.shiftKey
  );
}

function sanitizeTab(value) {
  return TAB_ITEMS.some((tab) => tab.id === value) ? value : DASHBOARD_DEFAULT_TAB;
}

function sanitizeCatalogMode(value) {
  return value === "family" ? "family" : DASHBOARD_DEFAULT_CATALOG_MODE;
}

function sanitizeBrowserSort(value) {
  return BROWSER_SORT_OPTIONS.some((option) => option.id === value) ? value : "smart";
}

function sanitizeRecommendationFilter(value) {
  return RECOMMENDATION_FILTER_OPTIONS.some((option) => option.id === value)
    ? value
    : DEFAULT_RECOMMENDATION_FILTER;
}

function sanitizeRequestedLens(requestedLensId, useCases) {
  if (!requestedLensId) {
    return "";
  }
  return useCases.some((useCase) => useCase.id === requestedLensId) ? requestedLensId : "";
}

function buildFamilyLookup(familyModels) {
  const familyIdByMemberId = {};
  const representativeByFamilyId = {};

  familyModels.forEach((model) => {
    representativeByFamilyId[model.id] = model.family?.representative_id || model.id;
    model.family?.member_ids?.forEach((memberId) => {
      familyIdByMemberId[memberId] = model.id;
    });
  });

  return { familyIdByMemberId, representativeByFamilyId };
}

function mapRankingEntriesToFamilies(entries, familyModels) {
  const entryByModelId = Object.fromEntries(entries.map((entry) => [entry.model.id, entry]));
  return Object.fromEntries(
    familyModels
      .map((familyModel) => {
        const familyEntries = (familyModel.family?.member_ids || [])
          .map((memberId) => entryByModelId[memberId])
          .filter(Boolean)
          .sort((left, right) => left.rank - right.rank || right.score - left.score);

        if (!familyEntries.length) {
          return null;
        }

        const bestEntry = familyEntries[0];
        return [
          familyModel.id,
          {
            ...bestEntry,
            model: familyModel,
            via_model_name: bestEntry.model.name,
          },
        ];
      })
      .filter(Boolean),
  );
}

function remapIdsForCatalogMode(ids, currentMode, nextMode, familyLookup) {
  return Array.from(
    new Set(
      ids
        .map((id) => remapIdForCatalogMode(id, currentMode, nextMode, familyLookup))
        .filter(Boolean),
    ),
  );
}

function remapIdForCatalogMode(id, currentMode, nextMode, familyLookup) {
  if (!id || currentMode === nextMode) {
    return id;
  }
  if (currentMode === "family" && nextMode === "exact") {
    return familyLookup.representativeByFamilyId[id] || id;
  }
  if (currentMode === "exact" && nextMode === "family") {
    return familyLookup.familyIdByMemberId[id] || id;
  }
  return id;
}

function toCatalogIdForMode(modelId, catalogMode, familyLookup) {
  return catalogMode === "family" ? familyLookup.familyIdByMemberId[modelId] || modelId : modelId;
}

function sortCatalogModels(models, { rankingByCatalogId, selectedUseCase, sortKey }) {
  return [...models].sort((left, right) => {
    if (sortKey === "name") {
      return String(left.name).localeCompare(String(right.name));
    }

    if (sortKey === "release") {
      const releaseDiff = getReleaseTimestamp(right.release_date) - getReleaseTimestamp(left.release_date);
      if (releaseDiff !== 0) {
        return releaseDiff;
      }
      return String(left.name).localeCompare(String(right.name));
    }

    const leftCoverage = getModelCoveragePercent(left);
    const rightCoverage = getModelCoveragePercent(right);

    if (sortKey === "price") {
      const leftPrice = getModelPricingSortValue(left);
      const rightPrice = getModelPricingSortValue(right);
      if (leftPrice !== rightPrice) {
        return leftPrice - rightPrice;
      }
      if (leftCoverage !== rightCoverage) {
        return rightCoverage - leftCoverage;
      }
      return String(left.name).localeCompare(String(right.name));
    }

    if (sortKey === "coverage") {
      if (leftCoverage !== rightCoverage) {
        return rightCoverage - leftCoverage;
      }
      return String(left.name).localeCompare(String(right.name));
    }

    if (sortKey === "popularity") {
      const leftPopularityRank = getOpenRouterPopularityRank(left, selectedUseCase);
      const rightPopularityRank = getOpenRouterPopularityRank(right, selectedUseCase);
      if (leftPopularityRank !== rightPopularityRank) {
        return leftPopularityRank - rightPopularityRank;
      }

      const leftPopularityTokens = getOpenRouterPopularityTokens(left, selectedUseCase);
      const rightPopularityTokens = getOpenRouterPopularityTokens(right, selectedUseCase);
      if (leftPopularityTokens !== rightPopularityTokens) {
        return rightPopularityTokens - leftPopularityTokens;
      }

      return String(left.name).localeCompare(String(right.name));
    }

    if (selectedUseCase) {
      const leftRanking = rankingByCatalogId[left.id];
      const rightRanking = rankingByCatalogId[right.id];
      if (leftRanking && rightRanking && leftRanking.rank !== rightRanking.rank) {
        return leftRanking.rank - rightRanking.rank;
      }
      if (leftRanking && !rightRanking) {
        return -1;
      }
      if (!leftRanking && rightRanking) {
        return 1;
      }
      if (leftRanking && rightRanking && leftRanking.score !== rightRanking.score) {
        return rightRanking.score - leftRanking.score;
      }
    }

    if (leftCoverage !== rightCoverage) {
      return rightCoverage - leftCoverage;
    }

    return String(left.name).localeCompare(String(right.name));
  });
}

function getModelCoveragePercent(model) {
  const scoreEntries = Object.values(model.scores || {});
  const availableCount = scoreEntries.filter((score) => score?.value != null).length;
  return Math.round((availableCount / Math.max(scoreEntries.length, 1)) * 100);
}

function getReleaseTimestamp(value) {
  const parsed = Date.parse(String(value || ""));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function getModelAgeMeta(model) {
  const releaseTimestamp = getPreciseReleaseTimestamp(model?.release_date);
  if (releaseTimestamp) {
    return {
      label: formatAgeDays(releaseTimestamp),
      source: "release",
    };
  }
  const openRouterAddedTimestamp = getTimestampOrZero(model?.openrouter_added_at);
  if (openRouterAddedTimestamp) {
    return {
      label: formatAgeDays(openRouterAddedTimestamp),
      source: "openrouter",
    };
  }
  return null;
}

function getPreciseReleaseTimestamp(value) {
  const text = String(value || "").trim();
  if (!text) {
    return 0;
  }
  if (!/^\d{4}-\d{2}-\d{2}(?:[T ].*)?$/.test(text)) {
    return 0;
  }
  return getTimestampOrZero(text);
}

function getTimestampOrZero(value) {
  const parsed = Date.parse(String(value || ""));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function formatAgeDays(timestamp) {
  const diffMs = Date.now() - timestamp;
  if (!Number.isFinite(diffMs)) {
    return "Unknown";
  }
  const days = Math.max(0, Math.floor(diffMs / 86400000));
  return `${days}d`;
}

function getTopComparisonIds(rankingEntries, catalogMode, familyLookup) {
  return Array.from(
    new Set(
      rankingEntries
        .map((entry) => toCatalogIdForMode(entry.model.id, catalogMode, familyLookup))
        .filter(Boolean),
    ),
  );
}

function sortBenchmarkIdsForLens(model, selectedUseCase, benchmarksById) {
  return Object.keys(model.scores || {}).sort((leftId, rightId) => {
    const leftScore = model.scores[leftId];
    const rightScore = model.scores[rightId];
    const leftHasData = leftScore?.value != null ? 0 : 1;
    const rightHasData = rightScore?.value != null ? 0 : 1;
    if (leftHasData !== rightHasData) {
      return leftHasData - rightHasData;
    }

    const leftWeight = selectedUseCase?.weights?.[leftId] || 0;
    const rightWeight = selectedUseCase?.weights?.[rightId] || 0;
    if (leftWeight !== rightWeight) {
      return rightWeight - leftWeight;
    }

    const leftTier = Number(benchmarksById[leftId]?.tier ?? 999);
    const rightTier = Number(benchmarksById[rightId]?.tier ?? 999);
    if (leftTier !== rightTier) {
      return leftTier - rightTier;
    }

    return String(benchmarksById[leftId]?.short || leftId).localeCompare(
      String(benchmarksById[rightId]?.short || rightId),
    );
  });
}

function compareBenchmarkSort(left, right, selectedUseCase) {
  const leftWeight = selectedUseCase?.weights?.[left.id] || 0;
  const rightWeight = selectedUseCase?.weights?.[right.id] || 0;
  if (leftWeight !== rightWeight) {
    return rightWeight - leftWeight;
  }

  const leftTier = Number(left.tier ?? 999);
  const rightTier = Number(right.tier ?? 999);
  if (leftTier !== rightTier) {
    return leftTier - rightTier;
  }

  return String(left.short || left.name).localeCompare(String(right.short || right.name));
}

function getOpenRouterPopularityRank(model, selectedUseCase) {
  const wantsProgramming = selectedUseCase?.id === "coding";
  const programmingRank = Number(model.openrouter_programming_rank);
  const globalRank = Number(model.openrouter_global_rank);

  if (wantsProgramming && Number.isFinite(programmingRank) && programmingRank > 0) {
    return programmingRank;
  }
  if (Number.isFinite(globalRank) && globalRank > 0) {
    return globalRank;
  }
  if (Number.isFinite(programmingRank) && programmingRank > 0) {
    return programmingRank;
  }
  return Number.POSITIVE_INFINITY;
}

function getOpenRouterPopularityTokens(model, selectedUseCase) {
  const wantsProgramming = selectedUseCase?.id === "coding";
  const programmingTokens = Number(model.openrouter_programming_total_tokens);
  const globalTokens = Number(model.openrouter_global_total_tokens);

  if (wantsProgramming && Number.isFinite(programmingTokens)) {
    return programmingTokens;
  }
  if (Number.isFinite(globalTokens)) {
    return globalTokens;
  }
  if (Number.isFinite(programmingTokens)) {
    return programmingTokens;
  }
  return 0;
}

function getPreferredOpenRouterLabel(model, selectedUseCase) {
  const programmingRank = Number(model.openrouter_programming_rank);
  if (selectedUseCase?.id === "coding" && Number.isFinite(programmingRank) && programmingRank > 0) {
    return `#${programmingRank} on OpenRouter Coding`;
  }

  const globalRank = Number(model.openrouter_global_rank);
  if (Number.isFinite(globalRank) && globalRank > 0) {
    return `#${globalRank} on OpenRouter`;
  }

  if (Number.isFinite(programmingRank) && programmingRank > 0) {
    return `#${programmingRank} on OpenRouter Coding`;
  }

  return "";
}

function getOpenRouterPopularityDetail(model, selectedUseCase) {
  if (selectedUseCase?.id === "coding") {
    const programmingTokens = Number(model.openrouter_programming_total_tokens);
    if (Number.isFinite(programmingTokens) && programmingTokens > 0) {
      return `${formatTokenVolume(programmingTokens)} programming tokens`;
    }
  }

  const globalShare = Number(model.openrouter_global_share);
  const globalTokens = Number(model.openrouter_global_total_tokens);
  if (Number.isFinite(globalShare) && globalShare > 0) {
    return `${(globalShare * 100).toFixed(globalShare >= 0.1 ? 1 : 2).replace(/\.0$/, "")}% weekly share`;
  }
  if (Number.isFinite(globalTokens) && globalTokens > 0) {
    return `${formatTokenVolume(globalTokens)} weekly tokens`;
  }
  return "";
}

function compareOpenRouterFamilyFilterOption(left, right) {
  const leftTokens = Number(left.openrouter_global_total_tokens);
  const rightTokens = Number(right.openrouter_global_total_tokens);
  if (Number.isFinite(leftTokens) || Number.isFinite(rightTokens)) {
    const safeLeftTokens = Number.isFinite(leftTokens) ? leftTokens : 0;
    const safeRightTokens = Number.isFinite(rightTokens) ? rightTokens : 0;
    if (safeLeftTokens !== safeRightTokens) {
      return safeRightTokens - safeLeftTokens;
    }
  }

  const leftShare = Number(left.openrouter_global_share);
  const rightShare = Number(right.openrouter_global_share);
  if (Number.isFinite(leftShare) || Number.isFinite(rightShare)) {
    const safeLeftShare = Number.isFinite(leftShare) ? leftShare : 0;
    const safeRightShare = Number.isFinite(rightShare) ? rightShare : 0;
    if (safeLeftShare !== safeRightShare) {
      return safeRightShare - safeLeftShare;
    }
  }

  const leftRank = Number(left.openrouter_global_rank);
  const rightRank = Number(right.openrouter_global_rank);
  const safeLeftRank = Number.isFinite(leftRank) && leftRank > 0 ? leftRank : Number.POSITIVE_INFINITY;
  const safeRightRank = Number.isFinite(rightRank) && rightRank > 0 ? rightRank : Number.POSITIVE_INFINITY;
  if (safeLeftRank !== safeRightRank) {
    return safeLeftRank - safeRightRank;
  }

  const providerComparison = String(left.provider || "").localeCompare(String(right.provider || ""));
  if (providerComparison !== 0) {
    return providerComparison;
  }
  return String(left.label || "").localeCompare(String(right.label || ""));
}

function groupUseCasesBySegment(useCases) {
  const orderedSegments = [
    {
      id: "core",
      title: "Core evaluation lenses",
      description: "General-purpose benchmark views for model selection and frontier tracking.",
    },
    {
      id: "enterprise",
      title: "Enterprise workflows",
      description: "Operational lenses tuned for internal copilots, support, and document-heavy business work.",
    },
  ];

  return orderedSegments
    .map((segment) => ({
      ...segment,
      items: useCases.filter((useCase) => (useCase.segment || "core") === segment.id),
    }))
    .filter((segment) => segment.items.length);
}

function formatUseCaseWeights(useCase, benchmarksById) {
  return Object.entries(useCase.weights || {})
    .sort((left, right) => right[1] - left[1])
    .map(([benchmarkId, weight]) => {
      const label = benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ");
      return `${label} ${Math.round(weight * 100)}%`;
    })
    .join(", ");
}

function buildCanonicalModels(models, benchmarksById) {
  const groups = new Map();

  models.forEach((model) => {
    const canonicalName = model.canonical_model_name || model.name;
    const canonicalKey = model.canonical_model_id || model.id;
    const current = groups.get(canonicalKey) || {
      canonicalKey,
      canonicalName,
      familyId: model.family_id || null,
      familyName: model.family_name || extractFamilyName(canonicalName),
      provider: model.provider,
      members: [],
    };
    current.members.push(model);
    groups.set(canonicalKey, current);
  });

  return Array.from(groups.values())
    .map((group) => buildCanonicalModel(group, benchmarksById))
    .sort((left, right) => {
      const providerComparison = String(left.provider).localeCompare(String(right.provider));
      if (providerComparison !== 0) {
        return providerComparison;
      }
      return String(left.name).localeCompare(String(right.name));
    });
}

function aggregateUseCaseApprovals(members) {
  const approvalKeys = new Set(
    members.flatMap((member) => Object.keys(member.use_case_approvals || {})),
  );
  const approvals = {};
  Array.from(approvalKeys)
    .sort((left, right) => left.localeCompare(right))
    .forEach((useCaseId) => {
      const entries = members
        .map((member) => member.use_case_approvals?.[useCaseId])
        .filter(Boolean);
      if (!entries.length) {
        return;
      }
      const latestEntry = [...entries].sort((left, right) =>
        String(right.approval_updated_at || "").localeCompare(String(left.approval_updated_at || "")),
      )[0];
      const latestRecommendationEntry = [...entries].sort((left, right) =>
        String(right.recommendation_updated_at || "").localeCompare(String(left.recommendation_updated_at || "")),
      )[0];
      const approvedMemberCount = entries.filter((entry) => entry.approved_for_use).length;
      const recommendationBreakdowns = members.map((member) => getRecommendationBreakdown(member, useCaseId));
      const recommendedMemberCount = recommendationBreakdowns.reduce(
        (sum, breakdown) => sum + Number(breakdown.recommendedCount || 0),
        0,
      );
      const notRecommendedMemberCount = recommendationBreakdowns.reduce(
        (sum, breakdown) => sum + Number(breakdown.notRecommendedCount || 0),
        0,
      );
      const discouragedMemberCount = recommendationBreakdowns.reduce(
        (sum, breakdown) => sum + Number(breakdown.discouragedCount || 0),
        0,
      );
      const distinctRecommendationStates = [
        recommendedMemberCount ? "recommended" : "",
        notRecommendedMemberCount ? "not_recommended" : "",
        discouragedMemberCount ? "discouraged" : "",
      ].filter(Boolean);
      approvals[useCaseId] = {
        use_case_id: useCaseId,
        approved_for_use: approvedMemberCount > 0,
        approval_notes: latestEntry?.approval_notes || "",
        approval_updated_at: latestEntry?.approval_updated_at || "",
        recommendation_status: distinctRecommendationStates.length > 1 ? "mixed" : (distinctRecommendationStates[0] || "unrated"),
        recommendation_notes: latestRecommendationEntry?.recommendation_notes || "",
        recommendation_updated_at: latestRecommendationEntry?.recommendation_updated_at || "",
        approval_member_count: approvedMemberCount,
        approval_total_count: members.length,
        recommended_member_count: recommendedMemberCount,
        not_recommended_member_count: notRecommendedMemberCount,
        discouraged_member_count: discouragedMemberCount,
      };
    });
  return approvals;
}

function countApprovedUseCases(approvals) {
  return Object.values(approvals || {}).filter((approval) => approval?.approved_for_use).length;
}

function buildCanonicalModel(group, benchmarksById) {
  const { canonicalKey, canonicalName, familyId, familyName, members, provider } = group;
  const representative = chooseRepresentativeModel(members, canonicalName);
  const benchmarkIds = new Set(members.flatMap((member) => Object.keys(member.scores || {})));
  const scores = {};
  const marketSignals = aggregateOpenRouterSignals(members);
  const inferenceDestinations = mergeInferenceDestinations(members);
  const inferenceSummary = buildInferenceSummary(inferenceDestinations);
  const inferenceCountries = collectInferenceCountries(inferenceDestinations);
  const pricingReference = aggregatePricingReference(members);
  const useCaseApprovals = aggregateUseCaseApprovals(members);
  const approvalUseCaseCount = countApprovedUseCases(useCaseApprovals);
  const approvedMemberCount = members.filter((member) => member.approved_for_use).length;

  benchmarkIds.forEach((benchmarkId) => {
    const benchmark = benchmarksById[benchmarkId];
    const bestEntry = members.reduce((best, member) => {
      const score = member.scores?.[benchmarkId];
      if (!score?.value && score?.value !== 0) {
        return best;
      }
      if (!best) {
        return { member, score };
      }
      if (isBetterBenchmarkScore(score, best.score, benchmark)) {
        return { member, score };
      }
      return best;
    }, null);

    scores[benchmarkId] = bestEntry
      ? {
          ...bestEntry.score,
          canonical_variant_id: bestEntry.member.id,
          canonical_variant_name: bestEntry.member.name,
        }
      : null;
  });

  return {
    ...representative,
    ...marketSignals,
    id: canonicalKey,
    name: canonicalName || representative.name,
    catalog_status: mergeFamilyValue(members, "catalog_status", representative.catalog_status),
    openrouter_added_at: mergeFamilyValue(members, "openrouter_added_at", representative.openrouter_added_at),
    family_id: familyId || representative.family_id,
    family_name: familyName || representative.family_name,
    canonical_model_id: canonicalKey,
    canonical_model_name: canonicalName || representative.name,
    approved_for_use: approvalUseCaseCount > 0,
    approval_use_case_count: approvalUseCaseCount,
    use_case_approvals: useCaseApprovals,
    approval_member_count: approvedMemberCount,
    approval_total_count: members.length,
    inference_countries: inferenceCountries,
    inference_destinations: inferenceDestinations,
    inference_summary: inferenceSummary,
    pricing_reference: pricingReference,
    scores,
    canonical: {
      key: canonicalKey,
      member_count: members.length,
      member_ids: members.map((member) => member.id),
      member_names: members.map((member) => member.name).sort((left, right) => left.localeCompare(right)),
      representative_id: representative.id,
    },
  };
}

function buildFamilyModels(models, benchmarksById) {
  const canonicalModels = buildCanonicalModels(models, benchmarksById);
  return buildFamilyModelsFromCanonical(canonicalModels, benchmarksById);
}

function buildFamilyModelsFromCanonical(canonicalModels, benchmarksById) {
  const groups = new Map();

  canonicalModels.forEach((model) => {
    const familyName = model.family_name || extractFamilyName(model.canonical_model_name || model.name);
    const familyKey = model.family_id || `${model.provider}::${slugifyText(familyName)}`;
    const current = groups.get(familyKey) || {
      familyKey,
      familyName,
      provider: model.provider,
      members: [],
    };
    current.members.push(model);
    groups.set(familyKey, current);
  });

  return Array.from(groups.values())
    .map((group) => buildFamilyModel(group, benchmarksById))
    .sort((left, right) => {
      const providerComparison = String(left.provider).localeCompare(String(right.provider));
      if (providerComparison !== 0) {
        return providerComparison;
      }
      return String(left.name).localeCompare(String(right.name));
    });
}

function buildFamilyModel(group, benchmarksById) {
  const { familyKey, familyName, members, provider } = group;
  const representative = chooseRepresentativeModel(members, familyName);
  const benchmarkIds = new Set(members.flatMap((member) => Object.keys(member.scores || {})));
  const scores = {};
  const marketSignals = aggregateOpenRouterSignals(members);
  const inferenceDestinations = mergeInferenceDestinations(members);
  const inferenceSummary = buildInferenceSummary(inferenceDestinations);
  const inferenceCountries = collectInferenceCountries(inferenceDestinations);
  const pricingReference = aggregatePricingReference(members);
  const useCaseApprovals = aggregateUseCaseApprovals(members);
  const approvalUseCaseCount = countApprovedUseCases(useCaseApprovals);
  const approvedMemberCount = members.reduce(
    (sum, member) => sum + Number(member.approval_member_count ?? (member.approved_for_use ? 1 : 0)),
    0,
  );
  const approvalTotalCount = members.reduce(
    (sum, member) => sum + Number(member.approval_total_count ?? 1),
    0,
  );

  benchmarkIds.forEach((benchmarkId) => {
    const benchmark = benchmarksById[benchmarkId];
    const bestEntry = members.reduce((best, member) => {
      const score = member.scores?.[benchmarkId];
      if (!score?.value && score?.value !== 0) {
        return best;
      }
      if (!best) {
        return { member, score };
      }
      if (isBetterBenchmarkScore(score, best.score, benchmark)) {
        return { member, score };
      }
      return best;
    }, null);

    scores[benchmarkId] = bestEntry
      ? {
          ...bestEntry.score,
          family_variant_id: bestEntry.member.id,
          family_variant_name: bestEntry.member.name,
          family_source_variant_id: bestEntry.score?.canonical_variant_id || bestEntry.member.id,
          family_source_variant_name: bestEntry.score?.canonical_variant_name || bestEntry.member.name,
        }
      : null;
  });

  return {
    ...representative,
    ...marketSignals,
    id: `family:${slugifyText(provider)}:${slugifyText(familyName || representative.name)}`,
    name: familyName || representative.name,
    catalog_status: mergeFamilyValue(members, "catalog_status", representative.catalog_status),
    context_window: mergeFamilyValue(members, "context_window", representative.context_window),
    release_date: mergeFamilyValue(members, "release_date", representative.release_date),
    openrouter_added_at: mergeFamilyValue(members, "openrouter_added_at", representative.openrouter_added_at),
    family_id: familyKey,
    family_name: familyName || representative.family_name,
    approved_for_use: approvalUseCaseCount > 0,
    approval_use_case_count: approvalUseCaseCount,
    use_case_approvals: useCaseApprovals,
    approval_member_count: approvedMemberCount,
    approval_total_count: approvalTotalCount,
    inference_countries: inferenceCountries,
    inference_destinations: inferenceDestinations,
    inference_summary: inferenceSummary,
    pricing_reference: pricingReference,
    scores,
    family: {
      key: familyKey,
      member_count: members.length,
      member_ids: members.map((member) => member.id),
      member_names: members.map((member) => member.name).sort((left, right) => left.localeCompare(right)),
      representative_id: representative.id,
    },
  };
}

function buildModelSearchText(model) {
  const parts = [
    model.name,
    model.provider,
    model.provider_country_name,
    model.provider_country_code,
    model.type,
    model.release_date,
    model.context_window,
    model.license_name,
    model.license_id,
    model.training_cutoff,
    model.intended_use_short,
    model.limitations_short,
    model.training_data_summary,
    model.family_name,
    model.canonical_model_name,
    ...(model.base_models || []),
    ...(model.supported_languages || []),
    ...(model.capabilities || []),
    ...(model.inference_countries || []),
  ];
  if (model.family?.member_names?.length) {
    parts.push(...model.family.member_names);
  }
  if (model.canonical?.member_names?.length) {
    parts.push(...model.canonical.member_names);
  }
  if (model.inference_destinations?.length) {
    model.inference_destinations.forEach((destination) => {
      parts.push(
        destination.name,
        destination.hyperscaler,
        destination.availability_scope,
        destination.location_scope,
        destination.pricing_label,
        ...(destination.deployment_modes || []),
        ...(destination.regions || []),
      );
    });
  }
  return parts
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function chooseRepresentativeModel(members, familyName) {
  return [...members].sort((left, right) => {
    const leftScore = representativeSortScore(left, familyName);
    const rightScore = representativeSortScore(right, familyName);
    if (leftScore !== rightScore) {
      return leftScore - rightScore;
    }

    const leftCoverage = countAvailableScores(left);
    const rightCoverage = countAvailableScores(right);
    if (leftCoverage !== rightCoverage) {
      return rightCoverage - leftCoverage;
    }

    return left.name.localeCompare(right.name);
  })[0];
}

function representativeSortScore(model, familyName) {
  let score = 0;
  const baseName = extractFamilyName(model.name);
  if (model.name === familyName) {
    score -= 50;
  }
  if (baseName === familyName) {
    score -= 10;
  }
  if (isSlugLike(model.name)) {
    score += 10;
  }
  if (hasVariantSuffix(model.name)) {
    score += 20;
  }
  score += model.name.length / 100;
  return score;
}

function countAvailableScores(model) {
  return Object.values(model.scores || {}).filter((score) => score?.value != null).length;
}

function mergeFamilyValue(members, key, fallback) {
  const values = Array.from(new Set(members.map((member) => member[key]).filter(Boolean)));
  if (values.length === 1) {
    return values[0];
  }
  if (values.length > 1) {
    return "Mixed";
  }
  return fallback || null;
}

function aggregateOpenRouterSignals(members) {
  const globalRanks = members
    .map((member) => Number(member.openrouter_global_rank))
    .filter((value) => Number.isFinite(value) && value > 0);
  const programmingRanks = members
    .map((member) => Number(member.openrouter_programming_rank))
    .filter((value) => Number.isFinite(value) && value > 0);
  const globalShares = members
    .map((member) => Number(member.openrouter_global_share))
    .filter((value) => Number.isFinite(value) && value > 0);
  const programmingVolumes = members
    .map((member) => Number(member.openrouter_programming_volume))
    .filter((value) => Number.isFinite(value) && value > 0);

  return {
    openrouter_global_rank: globalRanks.length ? Math.min(...globalRanks) : null,
    openrouter_global_total_tokens: sumOpenRouterSignal(members, "openrouter_global_total_tokens"),
    openrouter_global_share: globalShares.length ? Math.min(1, globalShares.reduce((sum, value) => sum + value, 0)) : null,
    openrouter_programming_rank: programmingRanks.length ? Math.min(...programmingRanks) : null,
    openrouter_programming_total_tokens: sumOpenRouterSignal(members, "openrouter_programming_total_tokens"),
    openrouter_programming_volume: programmingVolumes.length ? Math.max(...programmingVolumes) : null,
  };
}

function sumOpenRouterSignal(members, key) {
  const values = members
    .map((member) => Number(member[key]))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (!values.length) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0);
}

function mergeInferenceDestinations(members) {
  const destinationsById = new Map();

  members.forEach((member) => {
    (member.inference_destinations || []).forEach((destination) => {
      const destinationRegions = sortInferenceRegions(destination.regions || []);
      const existing = destinationsById.get(destination.id);
      if (!existing) {
        destinationsById.set(destination.id, {
          ...destination,
          regions: destinationRegions,
          region_count: destinationRegions.length,
          deployment_modes: Array.from(new Set(destination.deployment_modes || [])),
          sources: mergeInferenceSources([], destination.sources || []),
        });
        return;
      }

      existing.regions = sortInferenceRegions([...(existing.regions || []), ...destinationRegions]);
      existing.region_count = existing.regions.length;
      existing.deployment_modes = Array.from(
        new Set([...(existing.deployment_modes || []), ...(destination.deployment_modes || [])]),
      );
      existing.sources = mergeInferenceSources(existing.sources || [], destination.sources || []);
    });
  });

  return Array.from(destinationsById.values()).sort((left, right) => String(left.name).localeCompare(String(right.name)));
}

function mergeInferenceSources(existingSources, nextSources) {
  const sourcesByKey = new Map();
  [...existingSources, ...nextSources].forEach((source) => {
    if (!source?.label || !source?.url) {
      return;
    }
    sourcesByKey.set(`${source.label}:${source.url}`, source);
  });
  return Array.from(sourcesByKey.values());
}

function collectInferenceCountries(destinations) {
  return sortInferenceCountries(
    destinations.flatMap((destination) =>
      (destination.regions || []).map((region) => getInferenceCountryFromRegion(region)),
    ),
  );
}

function getModelInferenceCountries(model) {
  if (Array.isArray(model?.inference_countries) && model.inference_countries.length) {
    return sortInferenceCountries(model.inference_countries);
  }
  return collectInferenceCountries(model?.inference_destinations || []);
}

function getModelInferenceProviders(model) {
  const providersById = new Map();
  (model?.inference_destinations || []).forEach((destination) => {
    const id = String(destination?.id || "").trim();
    if (!id) {
      return;
    }
    providersById.set(id, {
      id,
      label: String(destination?.name || id).trim(),
      hyperscaler: String(destination?.hyperscaler || "").trim(),
    });
  });
  return Array.from(providersById.values()).sort((left, right) => {
    const hyperscalerComparison = String(left.hyperscaler || "").localeCompare(String(right.hyperscaler || ""));
    if (hyperscalerComparison !== 0) {
      return hyperscalerComparison;
    }
    return String(left.label || "").localeCompare(String(right.label || ""));
  });
}

function getModelInferenceProviderIds(model) {
  return getModelInferenceProviders(model).map((provider) => provider.id);
}

function getModelHyperscalers(model) {
  return Array.from(
    new Set(
      (model?.inference_destinations || [])
        .map((destination) => String(destination?.hyperscaler || "").trim())
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right));
}

function sortInferenceRegions(regions) {
  const uniqueRegions = Array.from(new Set((regions || []).map((region) => String(region || "").trim()).filter(Boolean)));
  return uniqueRegions.sort((left, right) => {
    const countryComparison = compareInferenceLocationLabels(
      getInferenceCountryFromRegion(left),
      getInferenceCountryFromRegion(right),
    );
    if (countryComparison !== 0) {
      return countryComparison;
    }
    return left.localeCompare(right);
  });
}

function sortInferenceCountries(countries) {
  const uniqueCountries = Array.from(new Set(countries.map((country) => String(country || "").trim()).filter(Boolean)));
  return uniqueCountries.sort(compareInferenceLocationLabels);
}

function compareInferenceLocationLabels(leftValue, rightValue) {
  const left = String(leftValue || "");
  const right = String(rightValue || "");
  if (left === right) {
    return 0;
  }

  const leftRank = getInferenceLocationRank(left);
  const rightRank = getInferenceLocationRank(right);
  if (leftRank !== rightRank) {
    return leftRank - rightRank;
  }
  return left.localeCompare(right);
}

function getInferenceLocationRank(location) {
  if (!location) {
    return 3;
  }
  if (location === "Australia") {
    return 0;
  }
  if (location === "Global") {
    return 2;
  }
  return 1;
}

function getInferenceCountryFromRegion(region) {
  const normalized = String(region || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  if (Object.prototype.hasOwnProperty.call(REGION_COUNTRY_OVERRIDES, normalized)) {
    return REGION_COUNTRY_OVERRIDES[normalized];
  }

  const keywordMatch = REGION_COUNTRY_KEYWORDS.find(([keyword]) => normalized.includes(keyword));
  if (keywordMatch) {
    return keywordMatch[1];
  }

  if (normalized.startsWith("us-gov") || normalized.startsWith("us-")) {
    return "United States";
  }
  if (normalized.startsWith("ca-")) {
    return "Canada";
  }
  if (normalized.startsWith("australia-")) {
    return "Australia";
  }
  if (normalized.startsWith("northamerica-northeast")) {
    return "Canada";
  }
  if (normalized.startsWith("southamerica-east")) {
    return "Brazil";
  }
  if (normalized.startsWith("southamerica-west")) {
    return "Chile";
  }

  return "";
}

function buildInferenceLocationKey(locationLabel) {
  return String(locationLabel || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function getModelInferenceRouteApprovalRecord(model, useCaseId, destinationId, locationLabel) {
  if (!useCaseId || !destinationId || !locationLabel) {
    return null;
  }
  const approval = getModelApprovalRecord(model, useCaseId);
  const locationKey = buildInferenceLocationKey(locationLabel);
  return (
    (approval?.inference_route_approvals || []).find(
      (entry) => entry?.destination_id === destinationId && entry?.location_key === locationKey,
    ) || null
  );
}

function getModelInferenceRouteApprovalSummary(model, useCaseId, destinationId, locationLabel) {
  if (!useCaseId || !destinationId || !locationLabel) {
    return null;
  }
  const approval = getModelApprovalRecord(model, useCaseId);
  const explicitRouteApproval = getModelInferenceRouteApprovalRecord(model, useCaseId, destinationId, locationLabel);
  const hasRouteOverrides = Boolean(approval?.inference_route_approvals?.length);
  const provider = getModelInferenceProviders(model).find((entry) => entry.id === destinationId);
  const routeLabel = `${provider?.label || destinationId} · ${locationLabel}`;

  if (explicitRouteApproval) {
    return explicitRouteApproval.approved_for_use
      ? {
          className: "tag tag-approval",
          label: `${routeLabel} approved`,
          title: explicitRouteApproval.approval_notes || "Explicitly approved on this route.",
          detail: explicitRouteApproval.approval_notes || "",
        }
      : {
          className: "tag tag-warning",
          label: `${routeLabel} blocked`,
          title: explicitRouteApproval.approval_notes || "Explicitly not approved on this route.",
          detail: explicitRouteApproval.approval_notes || "",
        };
  }

  if (!hasRouteOverrides) {
    if (approval?.approved_for_use) {
      return {
        className: "tag tag-approval-partial",
        label: `${routeLabel} inherits base approval`,
        title: "No route-specific row exists yet, so this route currently inherits the base approval.",
        detail: "No route-specific review exists yet. This route currently inherits the base lens approval.",
      };
    }
    return {
      className: "tag",
      label: `${routeLabel} base not approved`,
      title: "The model is not approved for this lens yet.",
      detail: "The base lens approval is still off, so this route is not approved.",
    };
  }

  return {
    className: "tag",
    label: `${routeLabel} unreviewed`,
    title: "This model already has route-specific approval rows for this lens, but not for the selected provider/location.",
    detail: "This model is already using route-specific approvals for this lens. The selected route has not been reviewed yet.",
  };
}

function buildInferenceSummary(destinations) {
  const deploymentModes = Array.from(
    new Set(destinations.flatMap((destination) => (destination.deployment_modes || []).filter(Boolean))),
  ).sort((left, right) => left.localeCompare(right));
  return {
    destination_count: destinations.length,
    region_count: destinations.reduce((sum, destination) => sum + Number(destination.region_count || 0), 0),
    platform_names: destinations.map((destination) => destination.name),
    deployment_modes: deploymentModes,
  };
}

function aggregatePricingReference(members) {
  return buildPricingReference(
    members.map((member) => member.price_input_per_mtok),
    members.map((member) => member.price_output_per_mtok),
  );
}

function buildPricingReference(inputValues, outputValues) {
  const inputNumbers = normalizePriceValues(inputValues);
  const outputNumbers = normalizePriceValues(outputValues);

  if (!inputNumbers.length && !outputNumbers.length) {
    return null;
  }

  return {
    input_min: inputNumbers.length ? Math.min(...inputNumbers) : null,
    input_max: inputNumbers.length ? Math.max(...inputNumbers) : null,
    output_min: outputNumbers.length ? Math.min(...outputNumbers) : null,
    output_max: outputNumbers.length ? Math.max(...outputNumbers) : null,
  };
}

function normalizePriceValues(values) {
  return (Array.isArray(values) ? values : [])
    .flatMap((value) => {
      if (value == null) {
        return [];
      }
      if (typeof value === "string" && value.trim() === "") {
        return [];
      }
      const numeric = Number(value);
      return Number.isFinite(numeric) && numeric >= 0 ? [numeric] : [];
    });
}

function getModelPricingReference(model) {
  if (model.pricing_reference) {
    return model.pricing_reference;
  }
  return buildPricingReference([model.price_input_per_mtok], [model.price_output_per_mtok]);
}

function getModelPricingSortValue(model) {
  const pricing = getModelPricingReference(model);
  if (!pricing) {
    return Number.POSITIVE_INFINITY;
  }

  const inputValue = Number(pricing.input_min);
  const outputValue = Number(pricing.output_min);
  const hasInput = Number.isFinite(inputValue);
  const hasOutput = Number.isFinite(outputValue);

  if (hasInput && hasOutput) {
    return ((inputValue * 3) + outputValue) / 4;
  }
  if (hasInput) {
    return inputValue;
  }
  if (hasOutput) {
    return outputValue;
  }
  return Number.POSITIVE_INFINITY;
}

function getModelPricingReferenceLabel(model) {
  const pricing = getModelPricingReference(model);
  if (!pricing) {
    return "";
  }

  const parts = [];
  const inputLabel = formatPricingRange(pricing.input_min, pricing.input_max);
  const outputLabel = formatPricingRange(pricing.output_min, pricing.output_max);

  if (inputLabel) {
    parts.push(`Input ${inputLabel}`);
  }
  if (outputLabel) {
    parts.push(`Output ${outputLabel}`);
  }

  return parts.length ? `${parts.join(" / ")} per 1M tokens` : "";
}

function getModelLicenseLabel(model) {
  return String(model?.license_name || model?.license_id || "").trim();
}

function getModelMetadataLinks(model) {
  const links = [
    { label: "Model card", url: model?.model_card_url },
    { label: "Docs", url: model?.documentation_url },
    { label: "Repo", url: model?.repo_url },
    { label: "Paper", url: model?.paper_url },
  ];
  const seen = new Set();
  return links.filter((entry) => {
    const url = String(entry.url || "").trim();
    if (!url || seen.has(url)) {
      return false;
    }
    seen.add(url);
    return true;
  });
}

function formatPricingRange(minimum, maximum) {
  const hasMinimum = Number.isFinite(minimum);
  const hasMaximum = Number.isFinite(maximum);

  if (!hasMinimum && !hasMaximum) {
    return "";
  }
  if (hasMinimum && hasMaximum && minimum === maximum) {
    return `$${formatPricingNumber(minimum)}`;
  }

  const start = hasMinimum ? `$${formatPricingNumber(minimum)}` : "";
  const end = hasMaximum ? `$${formatPricingNumber(maximum)}` : "";
  return start && end ? `${start} to ${end}` : start || end;
}

function formatPricingNumber(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "";
  }
  const maximumFractionDigits = numeric >= 100 ? 0 : numeric >= 10 ? 2 : numeric >= 1 ? 2 : numeric >= 0.1 ? 3 : 4;
  return numeric.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  });
}

function getInferenceSummaryLabel(summary) {
  if (!summary?.destination_count) {
    return "";
  }

  const parts = [`${summary.destination_count} hyperscaler${summary.destination_count === 1 ? "" : "s"}`];
  if (summary.region_count) {
    parts.push(`${summary.region_count} listed locations`);
  }
  if (summary.deployment_modes?.length) {
    parts.push(summary.deployment_modes.slice(0, 2).join(" + "));
  }
  return parts.join(" · ");
}

function isBetterBenchmarkScore(candidate, currentBest, benchmark) {
  const candidateValue = Number(candidate?.value);
  const bestValue = Number(currentBest?.value);
  if (Number.isNaN(candidateValue)) {
    return false;
  }
  if (Number.isNaN(bestValue)) {
    return true;
  }

  const higherIsBetter = benchmark?.higher_is_better !== false;
  if (candidateValue !== bestValue) {
    return higherIsBetter ? candidateValue > bestValue : candidateValue < bestValue;
  }

  return String(candidate?.collected_at || "") > String(currentBest?.collected_at || "");
}

function extractFamilyName(name) {
  if (!name) {
    return "";
  }

  if (isSlugLike(name)) {
    return stripSlugVariantSuffix(name);
  }

  return stripFriendlyVariantSuffix(name);
}

function stripFriendlyVariantSuffix(name) {
  let next = String(name).trim();
  next = next.replace(/\s+20\d{6}$/i, "");
  next = next.replace(/\s*\(([^)]*)\)\s*$/i, "");
  return next.trim();
}

function stripSlugVariantSuffix(name) {
  let next = String(name).trim();
  let previous;

  do {
    previous = next;
    next = next.replace(/-20\d{6}$/i, "");
    next = next.replace(/-(?:\d+k-)?thinking(?:-\d+k)?$/i, "");
    next = next.replace(/-thinking(?:-\d+k)?$/i, "");
    next = next.replace(/-(?:no-thinking|max|adaptive)$/i, "");
    next = next.replace(/-non-reasoning(?:-low-effort)?$/i, "");
  } while (next !== previous);

  return next;
}

function hasVariantSuffix(name) {
  return /\([^)]*\)\s*$/i.test(name) || /-(?:20\d{6}|thinking(?:-\d+k)?|no-thinking|max|adaptive|non-reasoning(?:-low-effort)?)$/i.test(name);
}

function isSlugLike(name) {
  return /^[a-z0-9-]+$/i.test(String(name).trim());
}

function slugifyText(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function normalizeBenchmarkValue(benchmark, value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return 50;
  }

  const rangeMin = Number(benchmark?.range_min);
  const rangeMax = Number(benchmark?.range_max);
  if (Number.isFinite(rangeMin) && Number.isFinite(rangeMax) && rangeMax > rangeMin) {
    let scaled;
    if (usesLogScaledBenchmark(benchmark) && numeric > 0) {
      const safeMin = Math.max(rangeMin, 0.01);
      const safeMax = Math.max(rangeMax, safeMin * 1.01);
      const safeValue = Math.max(numeric, safeMin);
      scaled = ((Math.log(safeValue) - Math.log(safeMin)) / (Math.log(safeMax) - Math.log(safeMin))) * 100;
    } else {
      scaled = ((numeric - rangeMin) / (rangeMax - rangeMin)) * 100;
    }
    const normalized = benchmark?.higher_is_better === false ? 100 - scaled : scaled;
    return Math.max(0, Math.min(100, normalized));
  }

  if (rangeMax === rangeMin && Number.isFinite(rangeMin)) {
    return 75;
  }

  return Math.max(0, Math.min(100, numeric <= 1.5 ? numeric * 100 : numeric));
}

function usesLogScaledBenchmark(benchmark) {
  return String(benchmark?.metric || "").includes("Tokens/sec");
}

function getBenchmarkTone(benchmark, value) {
  const normalized = normalizeBenchmarkValue(benchmark, value);
  if (!Number.isFinite(normalized)) {
    return "muted";
  }
  if (normalized >= 72) {
    return "good";
  }
  if (normalized >= 45) {
    return "warn";
  }
  return "bad";
}

function getBenchmarkScaleDescriptor(benchmark, value) {
  if (!usesLogScaledBenchmark(benchmark)) {
    return "";
  }
  const normalized = normalizeBenchmarkValue(benchmark, value);
  if (!Number.isFinite(normalized)) {
    return "";
  }
  if (normalized >= 80) {
    return "Very fast";
  }
  if (normalized >= 65) {
    return "Fast";
  }
  if (normalized >= 45) {
    return "Mid-pack";
  }
  if (normalized >= 25) {
    return "Slow";
  }
  return "Very slow";
}

function formatScore(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  if (Math.abs(numeric) >= 1000) {
    return numeric.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (Number.isInteger(numeric)) {
    return String(numeric);
  }
  return numeric.toFixed(1).replace(/\.0$/, "");
}

function formatTokenVolume(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return "—";
  }
  if (numeric >= 1_000_000_000_000) {
    return `${(numeric / 1_000_000_000_000).toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1")}T`;
  }
  if (numeric >= 1_000_000_000) {
    return `${(numeric / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}B`;
  }
  if (numeric >= 1_000_000) {
    return `${(numeric / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (numeric >= 1_000) {
    return `${(numeric / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  const percentage = numeric * 100;
  return `${percentage.toFixed(percentage >= 10 ? 1 : 2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1")}%`;
}

function formatSignedPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${formatPercent(numeric)}`;
}

function formatBenchmarkValue(benchmark, value) {
  if (!benchmark) {
    return formatScore(value);
  }

  const metric = String(benchmark.metric || "");
  if (metric.includes("Tokens/sec")) {
    return `${formatScore(value)} t/s`;
  }
  if (metric.includes("$/")) {
    return `$${formatScore(value)}`;
  }
  if (metric.includes("%") || metric.includes("Accuracy") || metric.includes("Grade")) {
    return `${formatScore(value)}%`;
  }
  return formatScore(value);
}

function formatDate(value) {
  if (!value) {
    return "Not updated yet";
  }
  const text = String(value);
  if (text.includes("T")) {
    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    }
  }
  return text;
}

function formatElapsedTime(startedAt, completedAt = "") {
  if (!startedAt) {
    return "—";
  }

  const started = new Date(startedAt);
  const ended = completedAt ? new Date(completedAt) : new Date();
  if (Number.isNaN(started.getTime()) || Number.isNaN(ended.getTime())) {
    return "—";
  }

  const totalSeconds = Math.max(0, Math.round((ended.getTime() - started.getTime()) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function formatSnapshotDateLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "Unknown";
  }
  const normalized = text.includes("T") ? text : text.includes(" ") ? text.replace(" ", "T") : `${text}T00:00:00`;
  const date = new Date(normalized);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }
  return text;
}

function formatSourceHost(url) {
  if (!url) {
    return "";
  }

  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return String(url);
  }
}

function getBenchmarkContext(benchmark) {
  const sourceHost = formatSourceHost(benchmark?.url);
  const fallbackSource = benchmark?.source ? `${benchmark.source}${sourceHost ? ` · ${sourceHost}` : ""}` : sourceHost || "benchmark source";

  const contextByBenchmarkId = {
    internal_view: {
      source: "Internal admin input · manual business/context signal",
      why: "captures internal rollout preference, operator experience, or business fit that external leaderboards do not measure.",
      caveat: "manual internal scores are optional and subjective; missing values do not reduce ranking coverage eligibility.",
    },
    aa_intelligence: {
      source: "Artificial Analysis · independent frontier model leaderboard",
      why: "best single-number snapshot here for broad model capability when you need an overall quality signal.",
    },
    aa_speed: {
      source: "Artificial Analysis · throughput leaderboard",
      why: "strongest quick signal here for real-time UX, concurrency, and queue-processing latency.",
      caveat: "Throughput bars use a log-scaled range in the UI because speed leaderboards are heavily skewed; a model can be genuinely fast without sitting near the absolute maximum.",
    },
    aa_cost: {
      source: "Artificial Analysis · normalized model pricing data",
      why: "best quick read on whether a model is financially viable at production volume.",
    },
    chatbot_arena: {
      source: "Arena.ai / LMSYS lineage · blind human preference votes",
      why: "strong proxy for chat quality, helpfulness, and which answers people actually prefer.",
    },
    gpqa_diamond: {
      source: "Epoch AI · contamination-resistant reasoning benchmark",
      why: "one of the better signals here for hard reasoning beyond memorized benchmark performance.",
    },
    mmmu: {
      source: "MMMU benchmark team · multimodal academic benchmark",
      why: "useful signal here for document, chart, screenshot, and image reasoning.",
      caveat: "the public leaderboard updates slowly and our current ingestion uses the validation split rather than a fresh held-out test feed.",
    },
    swebench_verified: {
      source: "SWE-bench team · official Verified leaderboard",
      why: "strong signal here for repo-level bug fixing and code-change execution.",
      caveat: "our score is derived from the best single-model system submission on the official Verified board, so it is still agent-shaped rather than a pure model-only eval.",
    },
    terminal_bench: {
      source: "tbench.ai · public verified leaderboard for agent submissions",
      why: "strongest signal here for real tool use and terminal workflows, so it matters heavily for enterprise agents.",
      caveat: "scores are agent-derived from verified single-model submissions, not a pure model-only benchmark.",
    },
    ifeval: {
      source: "llm-stats / ZeroEval feed · instruction-following leaderboard",
      why: "useful proxy for instruction obedience, formatting reliability, and workflow discipline in enterprise prompts.",
      caveat: "the live feed is currently dominated by self-reported and unverified results, so we treat it as lower-trust context rather than anchor evidence.",
    },
    ailuminate: {
      source: "MLCommons AILuminate · public named safety results",
      why: "useful signal here for deployment risk, refusal quality, and enterprise guardrails.",
      caveat: "public named results are coarse grade bands and mix bare models with broader AI systems.",
    },
    rag_groundedness: {
      source: "Vectara hallucination leaderboard · factual consistency evaluation",
      why: "useful groundedness signal for whether answers stay faithful to supplied source text.",
      caveat: "this is a grounded summarization faithfulness benchmark, not an end-to-end retrieval relevance eval on your corpus.",
    },
    rag_task_faithfulness: {
      source: "Vectara FaithJudge leaderboard · RAG task hallucination benchmark",
      why: "a directional signal for hallucination across supplied-context RAG-style tasks.",
      caveat: "coverage is narrow and it still measures faithfulness on supplied context, not end-to-end retrieval quality.",
    },
  };

  return contextByBenchmarkId[benchmark?.id] || {
    source: fallbackSource,
    why: benchmark?.description || "useful benchmark evidence for this model decision.",
    caveat: "",
  };
}

const styles = `
  :root {
    color-scheme: light;
    --bg: #f4f7fb;
    --panel: rgba(255, 255, 255, 0.92);
    --panel-strong: #ffffff;
    --line: rgba(148, 163, 184, 0.22);
    --text: #0f172a;
    --muted: #526075;
    --soft: #6b7a90;
    --accent: #0f766e;
    --accent-soft: rgba(15, 118, 110, 0.12);
    --blue: #1d4ed8;
    --blue-soft: rgba(29, 78, 216, 0.12);
    --good: #16a34a;
    --warn: #f59e0b;
    --bad: #ef4444;
    --shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
  }

  * { box-sizing: border-box; }
  html, body, #root { min-height: 100%; }
  body {
    margin: 0;
    font: 500 15px/1.55 Inter, system-ui, sans-serif;
    color: var(--text);
    background:
      radial-gradient(circle at top left, rgba(14, 165, 233, 0.08), transparent 28%),
      radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 26%),
      linear-gradient(180deg, #f8fafc 0%, var(--bg) 46%, #eef3f8 100%);
  }
  button, input, select, textarea { font: inherit; }
  a { color: inherit; text-decoration: none; }
  button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, a:focus-visible {
    outline: 3px solid rgba(79, 70, 229, 0.22);
    outline-offset: 2px;
  }
  .shell {
    min-height: 100vh;
    width: min(1280px, calc(100vw - 32px));
    margin: 0 auto;
    padding: 28px 0 56px;
    display: grid;
    gap: 18px;
  }
  .skip-link {
    position: absolute;
    left: 16px;
    top: -40px;
    z-index: 50;
    padding: 10px 14px;
    border-radius: 12px;
    background: #0f172a;
    color: #fff;
  }
  .skip-link:focus {
    top: 16px;
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
  .topbar {
    position: relative;
    overflow: hidden;
    max-width: none;
    margin: 0;
    padding: 28px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 28px;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(241, 245, 249, 0.94) 100%);
    box-shadow: var(--shadow);
  }
  .topbar::after {
    content: "";
    position: absolute;
    inset: auto -8% -36% auto;
    width: 280px;
    height: 280px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(29, 78, 216, 0.1), rgba(29, 78, 216, 0));
    pointer-events: none;
  }
  .topbar-main {
    display: grid;
    gap: 8px;
    max-width: 860px;
    position: relative;
    z-index: 1;
  }
  h1, h2, h3 {
    margin: 0;
    font-family: "Space Grotesk", Inter, system-ui, sans-serif;
    letter-spacing: -0.04em;
  }
  h1 {
    font-size: clamp(2.1rem, 4vw, 3.35rem);
    line-height: 0.96;
  }
  h2 { font-size: clamp(1.1rem, 1.6vw, 1.3rem); }
  h3 { font-size: 1rem; }
  .eyebrow, .meta, .version, .hint, .submeta, .tip, .small-meta, .panel-copy, .note, .coverage-label, .history-note, .history-errors, .detail-label, .bench-date, .metric, .message {
    color: var(--muted);
  }
  .eyebrow {
    color: var(--accent);
    font-size: 0.78rem;
    font-weight: 800;
    text-transform: none;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
  }
  .meta {
    margin-top: 8px;
    font-size: 0.96rem;
  }
  .topbar-actions {
    display: flex;
    align-items: flex-start;
    justify-content: flex-end;
    gap: 10px;
    flex-wrap: wrap;
    position: relative;
    z-index: 1;
  }
  .hero-state-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
  }
  .topbar-message {
    max-width: 320px;
    text-align: left;
    font-size: .8rem;
  }
  .version {
    border: 1px solid rgba(148, 163, 184, 0.22);
    background: rgba(248, 250, 252, 0.86);
    padding: 8px 12px;
    border-radius: 999px;
    color: var(--muted);
  }
  .btn {
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 999px;
    padding: 10px 14px;
    cursor: pointer;
    background: rgba(248, 250, 252, 0.86);
    color: var(--muted);
    transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease, background-color .15s ease, color .15s ease;
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.05);
  }
  .btn:hover { transform: translateY(-1px); }
  .btn:disabled { cursor: not-allowed; opacity: .7; transform: none; }
  .btn-primary {
    background: #0f172a;
    color: white;
    border-color: #0f172a;
  }
  .btn-secondary {
    background: rgba(255, 255, 255, 0.94);
    color: var(--text);
  }
  .btn-active {
    background: #0f172a;
    color: #fff;
    border-color: #0f172a;
  }
  .btn-ghost {
    background: transparent;
    border-color: transparent;
    box-shadow: none;
    color: var(--blue);
  }
  .btn-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .btn-compact {
    padding: 8px 12px;
    border-radius: 10px;
    box-shadow: none;
  }
  .btn-inline {
    justify-self: start;
  }
  .tabs {
    position: sticky;
    top: 12px;
    z-index: 20;
    background: transparent;
    border: 0;
    overflow: visible;
  }
  .tabs-desktop {
    max-width: none;
    margin: 0;
    padding: 8px;
    display: flex;
    overflow-x: auto;
    gap: 8px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.74);
    backdrop-filter: blur(14px);
    box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
  }
  .tabs-mobile {
    display: none;
    max-width: none;
    margin: 0;
    padding: 8px 0 0;
  }
  .tabs-edge {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 32px;
    pointer-events: none;
    display: none;
  }
  .tabs-edge-left {
    left: 0;
    background: linear-gradient(90deg, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0));
  }
  .tabs-edge-right {
    right: 0;
    background: linear-gradient(270deg, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0));
  }
  .tab {
    border: 0;
    background: transparent;
    padding: 10px 14px;
    border-bottom: 0;
    border-radius: 999px;
    color: var(--muted);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    white-space: nowrap;
    transition: background-color .12s ease, color .12s ease, transform .12s ease;
  }
  .tab:hover { transform: translateY(-1px); }
  .tab-active {
    color: #fff;
    background: #0f172a;
  }
  .tab-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 999px;
    background: rgba(29, 78, 216, .12);
    color: var(--blue);
    font-size: .72rem;
    font-weight: 700;
  }
  .page {
    max-width: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 18px;
  }
  .stack { display: grid; gap: 14px; }
  .stack-tight { display: grid; gap: 8px; }
  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }
  .toggle-group {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px;
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 999px;
    background: rgba(248, 250, 252, 0.84);
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
  }
  .toggle-btn {
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 10px 14px;
    border-radius: 999px;
    font-weight: 700;
    cursor: pointer;
  }
  .toggle-btn-active {
    background: #0f172a;
    color: #fff;
  }
  .pill, .badge, .tag, .compare-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 0.78rem;
    border: 1px solid rgba(148, 163, 184, 0.22);
    background: rgba(248, 250, 252, 0.86);
    color: var(--muted);
  }
  .pill-good {
    color: #166534;
    background: rgba(220, 252, 231, .95);
    border-color: rgba(34, 197, 94, .22);
  }
  .pill-bad {
    color: #991b1b;
    background: rgba(254, 242, 242, .95);
    border-color: rgba(248, 113, 113, .22);
  }
  .pill-muted {
    color: #475569;
    background: rgba(241, 245, 249, .92);
    border-color: rgba(148, 163, 184, .2);
  }
  .badge-slate { background: rgba(148, 163, 184, .14); color: #334155; }
  .badge-indigo, .tag-top {
    background: rgba(29, 78, 216, .12);
    color: var(--blue);
    border-color: rgba(29, 78, 216, .18);
  }
  .tag-ready {
    background: rgba(34, 197, 94, .10);
    color: #166534;
    border-color: rgba(34, 197, 94, .22);
  }
  .tag-preview {
    background: rgba(245, 158, 11, .12);
    color: #92400e;
    border-color: rgba(245, 158, 11, .22);
  }
  .tag-warning {
    background: rgba(251, 146, 60, .12);
    color: #9a3412;
    border-color: rgba(251, 146, 60, .22);
  }
  .tag-not-recommended {
    background: rgba(249, 115, 22, .16);
    color: #9a3412;
    border-color: rgba(249, 115, 22, .32);
    font-weight: 800;
  }
  .tag-legacy {
    background: rgba(120, 113, 108, .12);
    color: #57534e;
    border-color: rgba(120, 113, 108, .24);
    font-weight: 800;
  }
  .tag-detail {
    background: rgba(148, 163, 184, .12);
    color: #334155;
    border-color: rgba(148, 163, 184, .18);
  }
  .tag-provisional {
    background: rgba(245, 158, 11, .1);
    color: #92400e;
    border-color: rgba(245, 158, 11, .24);
  }
  .tag-license {
    background: rgba(245, 158, 11, .1);
    color: #92400e;
    border-color: rgba(245, 158, 11, .24);
  }
  .tag-approval {
    background: rgba(34, 197, 94, .10);
    color: #166534;
    border-color: rgba(34, 197, 94, .22);
  }
  .tag-approval-partial {
    background: rgba(14, 165, 233, .10);
    color: #0f766e;
    border-color: rgba(14, 165, 233, .22);
  }
  .badge-orange { background: rgba(249, 115, 22, .10); color: #9a3412; }
  .badge-green { background: rgba(34, 197, 94, .10); color: #166534; }
  .badge-blue { background: rgba(59, 130, 246, .10); color: #1d4ed8; }
  .badge-violet { background: rgba(139, 92, 246, .10); color: #6d28d9; }
  .badge-pink { background: rgba(236, 72, 153, .10); color: #be185d; }
  .tag-family {
    background: rgba(29, 78, 216, .12);
    color: var(--blue);
    border-color: rgba(29, 78, 216, .18);
  }
  .tag-inference {
    background: rgba(15, 118, 110, .10);
    color: #0f766e;
    border-color: rgba(13, 148, 136, .18);
  }
  .tag-inference-scope {
    background: rgba(226, 232, 240, .82);
    color: #334155;
    border-color: rgba(148, 163, 184, .18);
  }
  .badge-slate, .badge-indigo, .badge-orange, .badge-green, .badge-blue, .badge-violet, .badge-pink {
    font-weight: 600;
  }
  .usecase-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  .usecase-sections, .usecase-section {
    display: grid;
    gap: 14px;
  }
  .usecase-section-head {
    display: grid;
    gap: 4px;
  }
  .usecase-section-copy {
    color: var(--muted);
    font-size: .83rem;
    max-width: 720px;
  }
  @media (min-width: 760px) {
    .usecase-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  }
  .usecase, .card, .panel, .summary, .table, .banner, .empty, .loading-card {
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 16px;
    background: var(--panel);
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
  }
  .usecase {
    text-align: left;
    padding: 16px;
    cursor: pointer;
    transition: transform .15s ease, border-color .15s ease, background .15s ease;
  }
  .usecase:hover, .card-clickable:hover { transform: translateY(-1px); }
  .usecase-active {
    border-color: rgba(79, 70, 229, .4);
    background: rgba(239, 246, 255, .95);
  }
  .usecase-topline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 12px;
  }
  .usecase-icon { font-size: 1.45rem; }
  .usecase-label { font-weight: 700; font-size: .92rem; color: #111827; }
  .usecase-desc { margin-top: 6px; font-size: .77rem; line-height: 1.3; color: var(--muted); }
  .usecase-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 10px;
    font-size: .74rem;
    color: var(--muted);
  }
  .usecase-chip-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }
  .usecase-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 4px 8px;
    font-size: .72rem;
    color: #334155;
    background: rgba(255,255,255,.92);
    border: 1px solid rgba(148, 163, 184, .18);
  }
  .usecase-chip-required {
    background: rgba(239, 246, 255, .95);
    border-color: rgba(59, 130, 246, .16);
  }
  .usecase-status-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .preview-note, .usecase-note-caption {
    font-size: .78rem;
    line-height: 1.45;
    color: var(--muted);
  }
  .preview-note {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(245, 158, 11, .18);
    background: rgba(255, 251, 235, .88);
  }
  .usecase-notes {
    display: grid;
    gap: 8px;
    margin-top: 12px;
  }
  .usecase-note-item {
    display: grid;
    gap: 2px;
    font-size: .78rem;
    line-height: 1.4;
    color: var(--muted);
  }
  .workspace-intro {
    background: linear-gradient(135deg, rgba(255, 255, 255, .98), rgba(241, 245, 249, .94));
  }
  .workspace-intro-copy {
    max-width: 760px;
    font-size: .95rem;
    line-height: 1.6;
    color: #334155;
  }
  .starter-panel {
    gap: 14px;
    background: linear-gradient(135deg, rgba(255, 255, 255, .98), rgba(241, 245, 249, .96));
  }
  .starter-panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    flex-wrap: wrap;
  }
  .starter-lens-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
  .starter-lens-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid rgba(79, 70, 229, .14);
    border-radius: 999px;
    padding: 10px 14px;
    background: rgba(255,255,255,.96);
    color: #334155;
    cursor: pointer;
    font-weight: 600;
  }
  .finder-focus {
    display: grid;
    grid-template-areas:
      "main"
      "actions"
      "quick"
      "details";
    gap: 16px;
    padding: 22px;
    border: 1px solid rgba(148, 163, 184, .18);
    border-radius: 22px;
    background: linear-gradient(145deg, rgba(255, 255, 255, .98), rgba(241, 245, 249, .92));
    box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
  }
  .finder-focus-main {
    grid-area: main;
    display: grid;
    gap: 14px;
  }
  .finder-focus-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 14px;
    flex-wrap: wrap;
  }
  .finder-focus-copy {
    margin: 6px 0 0;
    max-width: 760px;
    color: #475569;
    line-height: 1.5;
  }
  .finder-focus-metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }
  .finder-metric {
    display: grid;
    gap: 4px;
    padding: 14px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .14);
    background: rgba(255, 255, 255, .82);
  }
  .finder-metric strong {
    font-size: 1.2rem;
    font-family: "Space Grotesk", Inter, system-ui, sans-serif;
    letter-spacing: -0.03em;
  }
  .finder-metric span {
    color: var(--muted);
    font-size: .78rem;
  }
  .update-progress-panel {
    display: grid;
    gap: 14px;
  }
  .update-progress-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }
  .update-progress-metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    min-width: min(100%, 360px);
  }
  .update-progress-bar {
    width: 100%;
    height: 10px;
    border-radius: 999px;
    background: rgba(226, 232, 240, .9);
    overflow: hidden;
  }
  .update-progress-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, rgba(37, 99, 235, .92), rgba(14, 165, 233, .88));
    transition: width .24s ease;
  }
  .update-progress-steps {
    display: grid;
    gap: 8px;
  }
  .update-progress-step {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .14);
    background: rgba(255, 255, 255, .86);
  }
  .update-progress-step-running {
    border-color: rgba(37, 99, 235, .22);
    background: rgba(239, 246, 255, .92);
  }
  .update-progress-step-failed {
    border-color: rgba(248, 113, 113, .24);
    background: rgba(254, 242, 242, .92);
  }
  .update-progress-step-completed {
    border-color: rgba(34, 197, 94, .2);
  }
  .update-progress-step-main {
    display: grid;
    gap: 4px;
  }
  .update-progress-step-label {
    font-weight: 600;
    color: #0f172a;
  }
  .update-progress-step-meta {
    font-size: .78rem;
    color: var(--muted);
  }
  .finder-focus-notes {
    display: grid;
    gap: 4px;
  }
  .finder-quick-picks {
    grid-area: quick;
    display: grid;
    gap: 10px;
    grid-template-columns: 1fr;
  }
  .finder-quick-pick {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    padding: 12px 14px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .16);
    background: rgba(255, 255, 255, .92);
  }
  .finder-quick-pick-top {
    border-color: rgba(79, 70, 229, .24);
    background: rgba(238, 242, 255, .9);
  }
  .finder-quick-rank {
    font-weight: 800;
    color: var(--accent);
    font-family: "Space Grotesk", Inter, system-ui, sans-serif;
  }
  .finder-quick-main {
    display: grid;
    gap: 6px;
    min-width: 0;
  }
  .finder-quick-title {
    font-weight: 700;
    color: #0f172a;
  }
  .finder-quick-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: .78rem;
    color: var(--muted);
  }
  .finder-focus-actions {
    grid-area: actions;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: flex-start;
  }
  .finder-details {
    grid-area: details;
    border-top: 1px solid rgba(148, 163, 184, .16);
    padding-top: 14px;
  }
  .finder-details summary {
    cursor: pointer;
    font-weight: 700;
    color: var(--accent);
    list-style: none;
  }
  .finder-details summary::-webkit-details-marker {
    display: none;
  }
  .finder-details-body {
    display: grid;
    gap: 12px;
    margin-top: 12px;
  }
  .finder-details-panel {
    box-shadow: none;
  }
  .finder-results-head {
    align-items: flex-end;
  }
  .finder-results-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
  }
  .tag-enterprise {
    background: rgba(2, 132, 199, .10);
    color: #0f766e;
    border-color: rgba(14, 165, 233, .22);
  }
  .card, .panel, .banner, .summary, .table, .empty { overflow: hidden; }
  .card-with-status-rail {
    display: flex;
    align-items: stretch;
  }
  .card-shell {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .card-status-rail {
    flex: 0 0 ${RECOMMENDATION_RAIL_WIDTH_PX}px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 14px 8px 12px;
    border-right: 1px solid rgba(148, 163, 184, .18);
  }
  .card-status-rail-text {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    white-space: nowrap;
    text-transform: uppercase;
    letter-spacing: ${RECOMMENDATION_RAIL_DESKTOP_LETTER_SPACING_EM}em;
    font-size: ${RECOMMENDATION_RAIL_DESKTOP_FONT_SIZE_REM}rem;
    line-height: 1;
    font-weight: 800;
  }
  .card-status-rail-auto {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 100%;
    padding: 4px 0;
    border-radius: 999px;
    background: rgba(255, 255, 255, .74);
    color: inherit;
    font-size: .58rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: .08em;
  }
  .card-status-rail-recommended {
    background: linear-gradient(180deg, rgba(220, 252, 231, .92), rgba(240, 253, 244, .74));
    color: #166534;
  }
  .card-status-rail-not_recommended {
    background: linear-gradient(180deg, rgba(255, 237, 213, .96), rgba(255, 247, 237, .8));
    color: #9a3412;
  }
  .card-status-rail-discouraged {
    background: linear-gradient(180deg, rgba(254, 226, 226, .96), rgba(255, 241, 242, .82));
    color: #b91c1c;
  }
  .card-status-rail-mixed {
    background: linear-gradient(180deg, rgba(224, 242, 254, .96), rgba(240, 249, 255, .82));
    color: #0f766e;
  }
  .card-status-rail-unrated {
    background: linear-gradient(180deg, rgba(241, 245, 249, .96), rgba(248, 250, 252, .86));
    color: #475569;
  }
  .card-body {
    padding: 16px;
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }
  .card-clickable { cursor: pointer; }
  .rank-pill {
    width: 32px;
    height: 32px;
    border-radius: 999px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    background: rgba(148, 163, 184, .12);
    color: #334155;
    font-weight: 800;
  }
  .card-top .rank-pill {
    background: rgba(79, 70, 229, .92);
    color: white;
  }
  .card-main { flex: 1; min-width: 0; }
  .card-headline {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
  }
  .title { font-weight: 700; color: #0f172a; }
  .submeta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: .78rem;
  }
  .submeta-score {
    color: #0f172a;
    font-weight: 600;
  }
  .legacy-inline-note {
    margin-top: 10px;
    padding: 9px 11px;
    border: 1px solid rgba(120, 113, 108, .18);
    border-left: 4px solid rgba(120, 113, 108, .45);
    border-radius: 12px;
    background: rgba(245, 245, 244, .72);
    color: #57534e;
    font-size: .78rem;
    line-height: 1.45;
  }
  .legacy-inline-note strong {
    color: #44403c;
  }
  .coverage-good { color: #16a34a; }
  .coverage-warn { color: #d97706; }
  .card-actions {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .chev, .link-btn {
    color: var(--accent);
    background: transparent;
    border: 0;
    cursor: pointer;
    font-weight: 700;
  }
  .card-details {
    border-top: 1px solid rgba(148, 163, 184, .16);
    background: rgba(248, 250, 252, .7);
    padding: 14px 16px;
    display: grid;
    gap: 16px;
  }
  .details-head,
  .compare-insights-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .critical-gaps {
    margin-bottom: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(255, 247, 237, .9);
    border: 1px solid rgba(251, 146, 60, .22);
    color: #9a3412;
    font-size: .78rem;
    line-height: 1.45;
  }
  .detail-label { font-size: .76rem; font-weight: 700; margin: 0; }
  .model-detail-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .detail-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(255, 255, 255, .94);
    color: #475569;
    font-size: .74rem;
  }
  .detail-pill strong {
    color: #0f172a;
    font-weight: 700;
  }
  .detail-copy {
    display: grid;
    gap: 4px;
  }
  .detail-caption {
    font-size: .76rem;
    line-height: 1.45;
    color: var(--muted);
  }
  .metadata-link-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .metadata-link {
    display: inline-flex;
    align-items: center;
    padding: 7px 12px;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, .2);
    background: rgba(248, 250, 252, .92);
    color: var(--blue);
    font-size: .82rem;
    font-weight: 700;
  }
  .metadata-link:hover {
    background: rgba(219, 234, 254, .42);
    border-color: rgba(59, 130, 246, .26);
  }
  .metadata-summary-grid {
    display: grid;
    gap: 10px;
  }
  .metadata-summary-item {
    display: grid;
    gap: 4px;
    padding: 12px 14px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(248, 250, 252, .82);
  }
  .metadata-summary-item strong {
    color: var(--muted);
    font-size: .76rem;
    letter-spacing: .02em;
    text-transform: uppercase;
  }
  .metadata-summary-item span {
    color: var(--text);
    line-height: 1.45;
  }
  .detail-list, .bench-grid, .history-list { display: grid; gap: 8px; }
  .member-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .member-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 6px 10px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(255,255,255,.94);
    color: #334155;
    font-size: .76rem;
  }
  .family-variant-grid {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }
  .family-variant-card {
    display: grid;
    gap: 12px;
    padding: 15px 16px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .16);
    background: linear-gradient(180deg, rgba(255, 255, 255, .96), rgba(255, 255, 255, .9));
  }
  .family-variant-head {
    display: grid;
    gap: 6px;
  }
  .family-variant-title-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .family-variant-title {
    font-weight: 700;
    color: #0f172a;
  }
  .family-variant-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
    font-size: .76rem;
    color: var(--muted);
  }
  .family-variant-stat {
    font-size: .78rem;
    line-height: 1.45;
    color: #0f172a;
  }
  .family-variant-subtitle {
    font-size: .74rem;
    font-weight: 700;
    color: #334155;
  }
  .family-variant-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .family-variant-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 5px 10px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(248, 250, 252, .92);
    color: #334155;
    font-size: .74rem;
  }
  .family-variant-chip-muted {
    color: var(--muted);
  }
  .family-variant-muted {
    font-size: .76rem;
    line-height: 1.45;
    color: var(--muted);
  }
  .inference-grid {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  }
  .inference-card {
    display: grid;
    gap: 12px;
    padding: 15px 16px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .16);
    background: linear-gradient(180deg, rgba(255, 255, 255, .96), rgba(255, 255, 255, .88));
  }
  .inference-card-head {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .inference-title-block {
    display: grid;
    gap: 4px;
    min-width: 0;
  }
  .inference-cloud {
    font-size: .68rem;
    text-transform: uppercase;
    letter-spacing: .1em;
    color: var(--muted);
  }
  .inference-title-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .inference-title {
    font-weight: 700;
    color: #0f172a;
  }
  .inference-copy {
    font-size: .78rem;
    line-height: 1.5;
    color: var(--muted);
  }
  .inference-summary-line {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .inference-summary-pill {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 5px 10px;
    background: rgba(248, 250, 252, .95);
    border: 1px solid rgba(226, 232, 240, .95);
    color: #334155;
    font-size: .74rem;
  }
  .inference-price {
    font-size: .82rem;
    line-height: 1.45;
    color: #0f172a;
    font-weight: 700;
  }
  .inference-region-row,
  .inference-links {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .region-chip,
  .inference-link {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 6px 10px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(248, 250, 252, .92);
    color: #334155;
    font-size: .74rem;
  }
  .region-chip-muted {
    color: var(--muted);
  }
  .inference-link {
    color: var(--accent);
    background: rgba(238, 242, 255, .92);
    border-color: rgba(79, 70, 229, .16);
  }
  .inference-foot {
    display: grid;
    gap: 8px;
    font-size: .76rem;
    line-height: 1.5;
    color: var(--muted);
  }
  .inference-empty {
    padding: 12px 14px;
    border-radius: 14px;
    border: 1px dashed rgba(148, 163, 184, .24);
    background: rgba(255, 255, 255, .84);
    color: var(--muted);
    font-size: .8rem;
  }
  .detail-row {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr) auto auto;
    gap: 8px;
    align-items: center;
  }
  .bench-row {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr) auto;
    gap: 8px 12px;
    align-items: center;
    padding: 10px 12px;
    border-radius: 14px;
    background: rgba(255, 255, 255, .88);
    border: 1px solid rgba(226, 232, 240, .85);
  }
  .detail-short, .bench-short {
    font-size: .75rem;
    color: #475569;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .bench-link {
    color: var(--accent);
  }
  .bench-row .bench-short {
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
    line-height: 1.4;
  }
  .bench-score, .score {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .bench-score {
    justify-self: end;
    font-weight: 700;
    white-space: nowrap;
  }
  .bench-score-good { color: #166534; }
  .bench-score-warn { color: #92400e; }
  .bench-score-bad { color: #b91c1c; }
  .bench-score-muted { color: #64748b; }
  .detail-value {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .detail-weight {
    font-size: .72rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .detail-note {
    grid-column: 2 / 5;
    font-size: .76rem;
    color: var(--muted);
    line-height: 1.45;
  }
  .bench-variant, .cell-variant, .bench-provenance {
    color: var(--muted);
    font-size: .76rem;
  }
  .bench-meta {
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 10px;
    align-items: center;
  }
  .bench-meta-item,
  .bench-empty {
    font-size: .75rem;
    color: var(--muted);
  }
  .bench-empty {
    justify-self: end;
    font-weight: 600;
  }
  .cell-note {
    color: var(--muted);
    font-size: .76rem;
    line-height: 1.45;
  }
  .bench-source, .bench-context, .bench-caveat {
    grid-column: 1 / -1;
    font-size: .76rem;
    line-height: 1.45;
  }
  .bench-source {
    color: var(--accent);
  }
  .bench-source-static {
    color: var(--muted);
  }
  .bench-provenance {
    grid-column: 1 / -1;
    line-height: 1.45;
  }
  .bench-context {
    color: var(--muted);
  }
  .bench-caveat {
    color: #92400e;
  }
  .source-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    padding: 2px 6px;
    font-size: .62rem;
    font-weight: 800;
    letter-spacing: .04em;
    border: 1px solid transparent;
  }
  .source-badge-verified {
    color: #166534;
    background: rgba(220, 252, 231, .95);
    border-color: rgba(34, 197, 94, .22);
  }
  .source-badge-secondary {
    color: #92400e;
    background: rgba(254, 243, 199, .95);
    border-color: rgba(245, 158, 11, .22);
  }
  .source-badge-manual {
    color: #334155;
    background: rgba(226, 232, 240, .9);
    border-color: rgba(148, 163, 184, .25);
  }
  .mini-bar, .score-track, .coverage-track {
    width: 100%;
    height: 8px;
    background: rgba(226, 232, 240, 0.95);
    border-radius: 999px;
    overflow: hidden;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .35);
  }
  .score-track { height: 10px; }
  .mini-fill, .score-fill, .coverage-fill {
    height: 100%;
    border-radius: inherit;
    transition: width .24s ease, background-color .24s ease;
  }
  .mini-fill-muted { background: linear-gradient(90deg, #94a3b8, #64748b); }
  .mini-fill-good { background: linear-gradient(90deg, #34d399, #16a34a); }
  .mini-fill-warn { background: linear-gradient(90deg, #fbbf24, #f59e0b); }
  .mini-fill-bad { background: linear-gradient(90deg, #fb7185, #ef4444); }
  .score-row, .coverage-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .score-row { margin-bottom: 8px; }
  .score-value {
    width: 42px;
    text-align: right;
    font-weight: 800;
  }
  .score-good, .coverage-good { background: linear-gradient(90deg, #22c55e, #16a34a); color: #166534; }
  .score-warn, .coverage-warn { background: linear-gradient(90deg, #f59e0b, #d97706); color: #92400e; }
  .score-bad, .coverage-muted { background: linear-gradient(90deg, #f87171, #ef4444); color: #b91c1c; }
  .coverage-label { width: 60px; text-align: right; font-size: .78rem; }
  .small-meta, .tip { margin-top: 10px; font-size: .78rem; }
  .lens-gap-note {
    color: var(--muted);
    font-size: .76rem;
  }
  .lens-gap-note-warning {
    color: #92400e;
  }
  .note {
    padding: 12px 14px;
    border: 1px solid rgba(245, 158, 11, .2);
    border-radius: 14px;
    background: rgba(255, 251, 235, .85);
    font-size: .8rem;
    line-height: 1.45;
  }
  .note-list { display: inline; margin-left: 4px; }
  .panel {
    padding: 16px;
    display: grid;
    gap: 12px;
  }
  .panel-head { font-weight: 700; }
  .admin-subtle {
    font-size: .82rem;
    line-height: 1.5;
    color: var(--muted);
  }
  .admin-savebar {
    position: sticky;
    top: 76px;
    z-index: 15;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 12px 14px;
    border: 1px solid rgba(79, 70, 229, .16);
    border-radius: 16px;
    background: rgba(255, 255, 255, .94);
    box-shadow: 0 14px 30px rgba(15, 23, 42, 0.08);
    backdrop-filter: blur(16px);
  }
  .admin-savebar-copy {
    font-size: .82rem;
    color: #334155;
    line-height: 1.5;
  }
  .admin-savebar-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 10px;
  }
  .admin-focus-group {
    flex-wrap: wrap;
  }
  .admin-toolbar {
    display: grid;
    gap: 10px;
    grid-template-columns: minmax(0, 1.3fr) minmax(220px, 1fr);
    align-items: end;
  }
  .admin-filter-toggle {
    flex-wrap: wrap;
    justify-content: flex-start;
    width: fit-content;
  }
  .admin-chip-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .admin-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(255, 255, 255, .94);
    color: #334155;
    font-size: .78rem;
    cursor: pointer;
  }
  .admin-chip input {
    margin: 0;
  }
  .admin-chip-active {
    background: rgba(79, 70, 229, .10);
    border-color: rgba(79, 70, 229, .22);
    color: var(--accent);
  }
  .admin-checkbox-inline {
    align-self: end;
  }
  .admin-list {
    display: grid;
    gap: 12px;
  }
  .admin-bulk-editor {
    display: grid;
    gap: 10px;
    padding: 14px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .16);
    background: rgba(255, 255, 255, .84);
  }
  .admin-bulk-textarea {
    min-height: 110px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace;
    font-size: .8rem;
  }
  .admin-row {
    display: grid;
    gap: 12px;
    padding: 14px;
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, .16);
    background: rgba(248, 250, 252, .82);
  }
  .admin-row-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    flex-wrap: wrap;
  }
  .admin-row-title {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .admin-grid {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .admin-grid-two {
    grid-template-columns: minmax(0, 220px) minmax(0, 1fr);
  }
  .admin-inline-note {
    font-size: .8rem;
    color: var(--muted);
    line-height: 1.5;
    align-self: end;
  }
  .admin-actions {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }
  .admin-preview-list {
    display: grid;
    gap: 8px;
  }
  .admin-preview-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    font-size: .8rem;
    color: #334155;
    border-bottom: 1px solid rgba(148, 163, 184, .12);
    padding-bottom: 6px;
  }
  .admin-preview-row:last-child {
    border-bottom: 0;
    padding-bottom: 0;
  }
  .admin-actions-start {
    justify-content: flex-start;
  }
  .admin-textarea {
    min-height: 88px;
    resize: vertical;
  }
  .admin-errors {
    display: grid;
    gap: 4px;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(248, 113, 113, .22);
    background: rgba(254, 242, 242, .94);
    color: #b91c1c;
    font-size: .78rem;
    line-height: 1.45;
  }
  .panel-copy { margin: 0; line-height: 1.5; }
  @media (max-width: 980px) {
    .admin-toolbar {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .method-grid, .methodology-usecases, .methodology-benchmarks {
    display: grid;
    gap: 12px;
  }
  .method-card {
    align-content: start;
  }
  .method-card-soft {
    padding: 14px;
    border-radius: 14px;
    border: 1px solid rgba(148, 163, 184, .14);
    background: rgba(248, 250, 252, .8);
  }
  .method-copy, .method-subtle {
    font-size: .82rem;
    line-height: 1.5;
    color: var(--muted);
  }
  .method-list, .method-steps, .weight-list {
    display: grid;
    gap: 8px;
  }
  .method-list > div, .method-step {
    font-size: .8rem;
    line-height: 1.45;
    color: #334155;
  }
  .method-step strong {
    display: inline-block;
    width: 18px;
    color: var(--accent);
  }
  .method-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .method-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border-radius: 999px;
    padding: 8px 10px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(255,255,255,.94);
    font-size: .75rem;
    color: #334155;
  }
  .method-focus-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .method-focus-title {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .weight-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    font-size: .78rem;
    color: #334155;
    border-bottom: 1px solid rgba(148, 163, 184, .12);
    padding-bottom: 6px;
  }
  .weight-row:last-child {
    border-bottom: 0;
    padding-bottom: 0;
  }
  .toolbar {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    margin-bottom: 10px;
  }
  .toolbar-wide {
    margin-bottom: 0;
  }
  .field {
    display: grid;
    gap: 6px;
  }
  .field-label {
    font-size: .76rem;
    font-weight: 700;
    color: var(--muted);
  }
  .browser-toolbar {
    gap: 14px;
  }
  .browser-toolbar-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .checkbox-row {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #334155;
    font-size: .84rem;
  }
  .browser-meta {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .list-footer {
    display: flex;
    justify-content: center;
    padding-top: 4px;
  }
  @media (min-width: 860px) {
    .toolbar { grid-template-columns: minmax(0, 1fr) 220px 220px; }
    .toolbar-wide { grid-template-columns: minmax(0, 1.4fr) 220px 220px 220px; }
    .method-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .methodology-usecases { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .methodology-benchmarks { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .finder-focus {
      grid-template-columns: minmax(0, 1fr) auto;
      grid-template-areas:
        "main actions"
        "quick quick"
        "details details";
      align-items: start;
    }
    .finder-focus-actions { justify-content: flex-end; }
  }
  .input, .select {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 12px 14px;
    background: rgba(255,255,255,.95);
    color: var(--text);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  }
  .stack > .panel, .stack > .card, .stack > .table, .stack > .banner, .stack > .empty {
    margin-top: 2px;
  }
  .table { display: grid; }
  .table-head, .table-row {
    display: grid;
    gap: 0;
  }
  .table-head {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(148, 163, 184, .16);
    background: rgba(248, 250, 252, .9);
    font-size: .75rem;
    font-weight: 800;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: #64748b;
  }
  .table-row {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(241, 245, 249, .85);
    align-items: center;
  }
  .table-row:last-child { border-bottom: 0; }
  .metric { font-size: .76rem; margin-top: 4px; }
  .cell, .cell-winner { padding: 0 8px; }
  .cell-score {
    display: grid;
    gap: 4px;
  }
  .cell-winner { font-weight: 700; }
  .score-winner { color: #166534; }
  .cell-empty { color: #cbd5e1; }
  .compare-summary {
    display: grid;
    gap: 12px;
  }
  .compare-insights {
    padding: 14px 16px;
  }
  .compare-insights-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .summary {
    padding: 16px;
    text-align: center;
  }
  .summary-top { border-color: rgba(79, 70, 229, .3); }
  .summary-title { font-weight: 700; margin-bottom: 8px; }
  .summary-score { margin-top: 14px; }
  .summary-score span { font-size: 2rem; font-weight: 800; color: var(--accent); display: block; line-height: 1; }
  .summary-score small, .summary-foot { color: var(--muted); }
  .summary-foot { margin-top: 6px; font-size: .78rem; }
  .compare-matrix {
    display: grid;
    gap: 10px;
  }
  .compare-row {
    display: grid;
    grid-template-columns: 180px minmax(0, 1fr);
    gap: 12px;
    padding: 14px 16px;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: rgba(255, 255, 255, .92);
    box-shadow: var(--shadow);
  }
  .compare-benchmark {
    display: grid;
    gap: 4px;
    align-content: start;
  }
  .compare-weight {
    font-size: .74rem;
    color: var(--accent);
    font-weight: 700;
  }
  .compare-cells {
    display: grid;
    gap: 10px;
  }
  .compare-cell {
    display: grid;
    gap: 6px;
    padding: 10px 12px;
    border-radius: 14px;
    border: 1px solid rgba(148, 163, 184, .14);
    background: rgba(248, 250, 252, .88);
  }
  .compare-cell-winner {
    border-color: rgba(34, 197, 94, .22);
    background: rgba(240, 253, 244, .9);
  }
  .cell-model {
    display: none;
    font-size: .74rem;
    font-weight: 700;
    color: var(--muted);
  }
  .compare-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
  }
  .compare-pill button {
    border: 0;
    background: transparent;
    color: var(--accent);
    cursor: pointer;
    font-weight: 800;
  }
  .suggestions {
    margin-top: 10px;
    border: 1px solid rgba(226, 232, 240, .9);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: var(--shadow);
  }
  .suggestion {
    width: 100%;
    padding: 12px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border: 0;
    background: #fff;
    border-bottom: 1px solid rgba(241, 245, 249, .9);
    cursor: pointer;
  }
  .suggestion:last-child { border-bottom: 0; }
  .history-list { gap: 12px; }
  .history-item {
    display: flex;
    gap: 14px;
    align-items: flex-start;
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: rgba(255,255,255,.9);
    box-shadow: var(--shadow);
  }
  .history-entry {
    display: grid;
    gap: 12px;
  }
  .history-toggle {
    border: 0;
    background: transparent;
    padding: 0;
    width: 100%;
    display: flex;
    align-items: flex-start;
    gap: 14px;
    text-align: left;
    cursor: pointer;
  }
  .history-main {
    min-width: 0;
    flex: 1 1 auto;
  }
  .history-chevron {
    color: var(--accent);
    font-weight: 800;
  }
  .history-dot {
    width: 10px;
    height: 10px;
    margin-top: 6px;
    border-radius: 999px;
    background: #818cf8;
    flex: 0 0 auto;
  }
  .history-date { font-weight: 700; margin-bottom: 4px; }
  .history-note, .history-errors { font-size: .82rem; line-height: 1.5; }
  .history-errors { color: #b91c1c; margin-top: 4px; }
  .history-sources {
    display: grid;
    gap: 10px;
    border-top: 1px solid rgba(148, 163, 184, .16);
    padding-top: 12px;
  }
  .history-source-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    border: 0;
    background: transparent;
    width: 100%;
    padding: 0;
    text-align: left;
    cursor: pointer;
  }
  .history-source-card {
    display: grid;
    gap: 8px;
    padding: 10px 0;
    border-top: 1px solid rgba(148, 163, 184, .12);
  }
  .history-source-card:first-child { border-top: 0; padding-top: 0; }
  .history-source-name {
    font-weight: 700;
    color: var(--text);
  }
  .history-source-meta, .history-sources-empty {
    font-size: .78rem;
    color: var(--muted);
  }
  .history-source-status {
    display: grid;
    justify-items: end;
    gap: 6px;
  }
  .history-source-chevron {
    color: var(--accent);
    font-size: .8rem;
    font-weight: 800;
  }
  .history-source-error {
    font-size: .76rem;
    color: #b91c1c;
    text-align: right;
    max-width: 280px;
  }
  .history-raw-panel {
    display: grid;
    gap: 8px;
    margin-left: 0;
    padding: 10px 12px;
    border: 1px solid rgba(148, 163, 184, .16);
    border-radius: 12px;
    background: rgba(248, 250, 252, .88);
  }
  .history-raw-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .history-raw-note, .history-raw-empty, .history-raw-meta {
    font-size: .76rem;
    color: var(--muted);
  }
  .history-raw-list {
    display: grid;
    gap: 6px;
  }
  .history-raw-row {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: baseline;
  }
  .history-raw-name {
    font-size: .8rem;
    color: var(--text);
  }
  .market-history-panel {
    display: grid;
    gap: 14px;
  }
  .market-history-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .market-scope-switch,
  .market-date-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .market-scope-btn,
  .market-date-chip {
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(255,255,255,.92);
    color: var(--muted);
    border-radius: 999px;
    padding: 8px 12px;
    font-size: .78rem;
    font-weight: 700;
    cursor: pointer;
  }
  .market-scope-btn-active,
  .market-date-chip-active {
    color: var(--accent);
    border-color: rgba(79, 70, 229, .24);
    background: rgba(238, 242, 255, .96);
  }
  .market-snapshot-metrics {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .market-table-wrap {
    overflow-x: auto;
    border: 1px solid rgba(148, 163, 184, .16);
    border-radius: 14px;
    background: rgba(255,255,255,.9);
  }
  .market-table {
    width: 100%;
    min-width: 760px;
    border-collapse: collapse;
  }
  .market-table th,
  .market-table td {
    padding: 12px 14px;
    border-bottom: 1px solid rgba(241, 245, 249, .9);
    text-align: left;
    font-size: .8rem;
    vertical-align: top;
  }
  .market-table th {
    background: rgba(248, 250, 252, .92);
    color: #64748b;
    font-size: .72rem;
    font-weight: 800;
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .market-table tbody tr:last-child td {
    border-bottom: 0;
  }
  .market-model-cell {
    display: grid;
    gap: 4px;
  }
  .market-model-cell a {
    font-size: .72rem;
    color: var(--accent);
  }
  .banner {
    padding: 14px 16px;
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .banner-error {
    background: rgba(254, 242, 242, .95);
    border-color: rgba(248, 113, 113, .22);
    color: #991b1b;
  }
  .banner-info {
    background: rgba(239, 246, 255, .95);
    border-color: rgba(96, 165, 250, .22);
    color: #1e3a8a;
  }
  .empty {
    padding: 22px;
    text-align: center;
    color: var(--muted);
    background: rgba(255,255,255,.9);
  }
  .loading {
    display: grid;
    gap: 14px;
  }
  .loading-card {
    height: 110px;
    background: linear-gradient(90deg, rgba(226, 232, 240, .6), rgba(241, 245, 249, .95), rgba(226, 232, 240, .6));
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite linear;
  }
  .toast {
    position: fixed;
    right: 18px;
    bottom: 18px;
    max-width: min(420px, calc(100vw - 36px));
    padding: 14px 16px;
    border-radius: 14px;
    background: rgba(15, 23, 42, .94);
    color: white;
    box-shadow: 0 18px 60px rgba(15, 23, 42, .24);
  }
  @keyframes shimmer {
    0% { background-position: 0 0; }
    100% { background-position: -200% 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
    .loading-card {
      animation: none;
      background-position: 0 0;
    }
  }
  @media (max-width: 860px) {
    .tabs-desktop { display: none; }
    .tabs-mobile { display: block; }
    .tabs-edge { display: none; }
    .topbar { flex-direction: column; }
    .section-head { flex-direction: column; align-items: flex-start; }
    .topbar-message { text-align: left; max-width: none; }
    .card-with-status-rail {
      flex-direction: column;
    }
    .card-status-rail {
      flex: 0 0 auto;
      width: 100%;
      flex-direction: row;
      justify-content: space-between;
      padding: 10px 14px;
      border-right: 0;
      border-bottom: 1px solid rgba(148, 163, 184, .14);
    }
    .card-status-rail-text {
      writing-mode: initial;
      transform: none;
      letter-spacing: ${RECOMMENDATION_RAIL_MOBILE_LETTER_SPACING_EM}em;
      font-size: ${RECOMMENDATION_RAIL_MOBILE_FONT_SIZE_REM}rem;
      white-space: nowrap;
    }
    .card-status-rail-auto {
      min-width: auto;
      padding: 4px 8px;
    }
    .card-body { flex-direction: column; }
    .card-actions { width: 100%; justify-content: space-between; }
    .finder-focus-metrics, .compare-insights-grid { grid-template-columns: 1fr; }
    .admin-grid { grid-template-columns: 1fr; }
    .finder-focus-actions { width: 100%; }
    .finder-focus-actions .btn { width: 100%; }
    .finder-quick-pick { grid-template-columns: auto minmax(0, 1fr); }
    .finder-quick-pick .btn { grid-column: 1 / -1; width: 100%; }
    .browser-toolbar-footer { align-items: flex-start; }
    .admin-savebar { top: 68px; flex-direction: column; align-items: stretch; }
    .admin-savebar-actions { width: 100%; justify-content: stretch; }
    .admin-savebar-actions .btn { width: 100%; }
    .compare-summary { grid-template-columns: 1fr !important; }
    .compare-row { grid-template-columns: 1fr; }
    .compare-cells { grid-template-columns: 1fr !important; }
    .cell-model { display: block; }
    .table-head, .table-row { grid-template-columns: 1fr !important; }
    .table-row > div { margin-bottom: 8px; }
    .detail-row { grid-template-columns: 82px minmax(0, 1fr); }
    .bench-row { grid-template-columns: 1fr; }
    .detail-weight { grid-column: 2; }
    .detail-note { grid-column: 2; }
    .bench-score, .bench-empty { justify-self: start; }
    .bench-meta, .bench-provenance, .bench-source, .bench-context, .bench-caveat { grid-column: 1; }
    .market-snapshot-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .update-progress-metrics { grid-template-columns: 1fr; min-width: 0; width: 100%; }
    .update-progress-step { flex-direction: column; }
    .history-source-row { flex-direction: column; }
    .history-source-status { justify-items: start; }
    .history-source-error { max-width: none; text-align: left; }
  }
`;

export default App;
