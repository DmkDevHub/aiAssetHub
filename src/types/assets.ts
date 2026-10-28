/** Display data supplied by a caller; this type does not load files or invent metadata. */
export interface AssetSummary {
  activeResultId?: string | null;
  lastAnalysisJobId?: string | null;
  analysisStale?: boolean;
  lastAnalysisError?: string | null;
  hasActiveResult?: boolean;
  lastAttemptState?: string | null;
  lastAnalysisAt?: string | null;
  userTags?: readonly string[];
  id: string;
  name: string;
  kind: string;
  analysisText?: string;
  libraryId?: string;
  relativePath?: string;
  path?: string;
  size?: number;
  mtimeNs?: number | string;
  exists?: boolean;
  scanChange?: string;
}
