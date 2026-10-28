/** Display data supplied by a caller; this type does not load files or invent metadata. */
export interface AssetSummary {
  id: string;
  name: string;
  kind: string;
  analysisText?: string;
}
