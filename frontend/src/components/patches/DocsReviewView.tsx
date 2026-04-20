import { useEffect, useState } from "react";
import { X, FileText, ExternalLink, Check } from "lucide-react";
import { toast } from "sonner";
import { dk } from "../../lib/constants";
import { openDocxInWord } from "../../lib/api";
import type { PatchSummary } from "../../lib/types";

interface DocsReviewViewProps {
  patch: PatchSummary;
  productName: string;
  onContinue: () => void;
  onClose: () => void;
}

export default function DocsReviewView({
  patch,
  productName,
  onContinue,
  onClose,
}: DocsReviewViewProps) {
  const [openingInWord, setOpeningInWord] = useState(false);
  // Per-mount cache-bust: forces Chrome to treat each open as a fresh URL so a
  // previously-cached Content-Disposition: attachment header can't stick.
  const [cacheBust] = useState(() => Date.now());

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const sourceUrl = `/api/patches/${patch.product_id}/${patch.patch_id}/release-notes/source.pdf?v=${cacheBust}`;
  const previewUrl = `/api/patches/${patch.product_id}/${patch.patch_id}/release-notes/preview.pdf?v=${cacheBust}`;

  const handleOpenInWord = async () => {
    setOpeningInWord(true);
    try {
      await openDocxInWord(patch.product_id, patch.patch_id);
      toast.success(`Opening DOCX in Word — edits persist to disk.`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to open in Word";
      toast.error(`Open in Word failed: ${msg}`);
    } finally {
      setOpeningInWord(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-2"
      style={{ backgroundColor: "rgba(0,0,0,0.75)" }}
      onClick={onClose}
    >
      <div
        className="flex flex-col w-full h-full rounded-xl overflow-hidden"
        style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-3 flex-shrink-0"
          style={{ borderBottom: `1px solid ${dk.border}` }}
        >
          <div className="flex items-center gap-3">
            <FileText size={18} style={{ color: dk.purple }} />
            <div>
              <div className="text-sm font-semibold" style={{ color: dk.text }}>
                Review release notes — {patch.patch_id}
              </div>
              <div className="text-xs" style={{ color: dk.textDim }}>
                {productName} · version {patch.version}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleOpenInWord}
              disabled={openingInWord}
              className="px-3 py-1.5 text-xs font-semibold rounded-md inline-flex items-center gap-1.5"
              style={
                openingInWord
                  ? {
                      backgroundColor: dk.surface,
                      border: `1px solid ${dk.border}`,
                      color: dk.textDim,
                      cursor: "not-allowed",
                      opacity: 0.6,
                    }
                  : {
                      backgroundColor: dk.surface,
                      border: `1px solid ${dk.border}`,
                      color: dk.text,
                    }
              }
              title="Opens the canonical DOCX in Word. Edits you save persist to disk; reload this view to re-render the preview."
            >
              <ExternalLink size={12} />
              {openingInWord ? "Opening…" : "Open in Word"}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md hover:bg-white/5"
              style={{ color: dk.textDim }}
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Two panels */}
        <div className="flex flex-row flex-1 min-h-0">
          <div className="flex-1 flex flex-col min-w-0">
            <div
              className="px-4 py-2 text-xs font-semibold uppercase tracking-wider flex-shrink-0"
              style={{
                color: dk.textMute,
                backgroundColor: dk.surface,
                borderBottom: `1px solid ${dk.border}`,
              }}
            >
              Source PDF (Zendesk)
            </div>
            <iframe
              src={sourceUrl}
              title="Source release notes PDF"
              className="flex-1 w-full"
              style={{ border: "none", backgroundColor: "#fff" }}
            />
          </div>

          <div
            className="flex-shrink-0"
            style={{ width: 1, backgroundColor: dk.border }}
          />

          <div className="flex-1 flex flex-col min-w-0">
            <div
              className="px-4 py-2 text-xs font-semibold uppercase tracking-wider flex-shrink-0"
              style={{
                color: dk.textMute,
                backgroundColor: dk.surface,
                borderBottom: `1px solid ${dk.border}`,
              }}
            >
              Rendered DOCX preview
            </div>
            <iframe
              src={previewUrl}
              title="Rendered DOCX preview"
              className="flex-1 w-full"
              style={{ border: "none", backgroundColor: "#fff" }}
            />
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-end gap-2 px-5 py-3 flex-shrink-0"
          style={{ borderTop: `1px solid ${dk.border}` }}
        >
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs font-semibold rounded-md"
            style={{
              backgroundColor: dk.surface,
              border: `1px solid ${dk.border}`,
              color: dk.textDim,
            }}
          >
            Cancel
          </button>
          <button
            onClick={onContinue}
            className="px-3 py-1.5 text-xs font-semibold rounded-md inline-flex items-center gap-1.5"
            style={{
              background: "linear-gradient(135deg,#7c3aed,#6d28d9)",
              color: "#fff",
            }}
          >
            <Check size={12} />
            Looks good, continue
          </button>
        </div>
      </div>
    </div>
  );
}
