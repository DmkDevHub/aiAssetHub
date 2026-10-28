/** Display data supplied by a caller; this type does not load files or invent metadata. */
export interface AssetSummary {
  id: string;
  name: string;
  kind: string;
  analysisText?: string;
  libraryId?: string;
  relativePath?: string;
  path?: string;
  size?: number;
  mtimeNs?: number;
  exists?: boolean;
  scanChange?: string;
}
