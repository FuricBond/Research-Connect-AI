import React from "react";
import { Award, CheckCircle2, ShieldCheck } from "lucide-react";

interface QualityBadgeProps {
  indexing?: string[] | null;
  status?: string | null;
  qualityScore?: number | null;
  showScore?: boolean;
}

const TIER_1_BODIES = new Set([
  "SCOPUS", "SCI", "SCIE", "SSCI", "AHCI", "WEB OF SCIENCE", "WOS",
  "IEEE", "IEEE XPLORE", "ACM", "ACM DIGITAL LIBRARY", "MEDLINE", "PUBMED",
]);

const TIER_2_BODIES = new Set([
  "DBLP", "EI COMPENDEX", "DOAJ", "SPRINGER", "ELSEVIER", "INSPEC", "EMBASE", "CORE A", "CORE A*"
]);

export const QualityBadge: React.FC<QualityBadgeProps> = ({
  indexing,
  status,
  qualityScore,
  showScore = false,
}) => {
  const indexList = Array.isArray(indexing) ? indexing : [];
  
  // Determine highest tier
  let isTier1 = false;
  let isTier2 = false;
  let topIndexer = "";

  for (const item of indexList) {
    if (typeof item === "string") {
      const upper = item.trim().toUpperCase();
      if (TIER_1_BODIES.has(upper)) {
        isTier1 = true;
        topIndexer = item;
        break;
      }
      if (TIER_2_BODIES.has(upper) && !isTier2) {
        isTier2 = true;
        topIndexer = item;
      }
    }
  }

  if (isTier1) {
    return (
      <span className="quality-badge quality-tier-1" title={`Indexed in Tier 1 database: ${topIndexer}`}>
        <ShieldCheck size={13} />
        <span>{topIndexer || "Top Indexed"}</span>
        {showScore && qualityScore !== undefined && qualityScore !== null && (
          <span className="quality-score-pill">{(qualityScore * 100).toFixed(0)}%</span>
        )}
      </span>
    );
  }

  if (isTier2) {
    return (
      <span className="quality-badge quality-tier-2" title={`Indexed in recognized database: ${topIndexer}`}>
        <Award size={13} />
        <span>{topIndexer || "Indexed"}</span>
        {showScore && qualityScore !== undefined && qualityScore !== null && (
          <span className="quality-score-pill">{(qualityScore * 100).toFixed(0)}%</span>
        )}
      </span>
    );
  }

  if (status === "ACTIVE" || status === "VERIFIED") {
    return (
      <span className="quality-badge quality-verified" title="Verified active academic venue">
        <CheckCircle2 size={13} />
        <span>Verified Venue</span>
        {showScore && qualityScore !== undefined && qualityScore !== null && (
          <span className="quality-score-pill">{(qualityScore * 100).toFixed(0)}%</span>
        )}
      </span>
    );
  }

  return (
    <span className="quality-badge quality-neutral" title="Standard academic listing">
      <span>Standard Listing</span>
    </span>
  );
};
