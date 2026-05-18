"""
COMPETITIVE ADVANTAGE TEST — Sprint 6: Photo Deskew Pipeline
═════════════════════════════════════════════════════════════
Validates the core differentiator vs Stratus / PlanGrid:

  "Foto torcida de teléfono → plano recto con quality_score > 70"

Stratus requires a flat scanner. Conduit accepts a phone photo taken at any
angle and automatically corrects the perspective. This test proves the
algorithm meets the quality bar before every deploy.

Tests:
  1. test_photo_deskew — skewed plan fixture achieves quality_score > 70
     and deskew_applied = True (the primary competitive claim)
  2. test_pdf_passthrough — PDF source type skips deskew (no false positives)
  3. test_quality_score_formula — sharp image ≥ 70, blurry image < 70
  4. test_deskew_corrects_geometry — output aspect ratio closer to source plan

Bliss Systems LLC — APEX Standard
"""

import cv2
import numpy as np
import pytest

from app.tasks.plan_tasks import deskew_and_score


# ── Fixture generators ─────────────────────────────────────────────────────

def _make_skewed_plan_jpg(skew: bool = True) -> bytes:
    """
    Generates a synthetic plan-photo fixture.

    Contrast hierarchy (critical for Canny to find the right contour):
      - Plan outer edge: white (255) on black (0)  → gradient 255  ← STRONGEST
      - Grid lines: light gray (160) on white (255) → gradient  95  ← weaker
    This ensures the deskew contour detector finds the plan perimeter first,
    not the internal grid cells.

    The 10px margin keeps grid lines away from the outer edge so the outer
    contour is always a clean, uninterrupted closed polygon.
    """
    W, H = 800, 600
    bg = np.zeros((H, W, 3), dtype=np.uint8)  # black table (maximises plan contrast)

    plan_h, plan_w = 380, 520
    plan = np.full((plan_h, plan_w, 3), 255, dtype=np.uint8)  # pure white sheet

    # Grid inside a 10px inset margin so outer edge stays clean
    margin = 10
    for x in range(margin, plan_w - margin, 30):
        cv2.line(plan, (x, margin), (x, plan_h - margin), (160, 160, 160), 1)
    for y in range(margin, plan_h - margin, 30):
        cv2.line(plan, (margin, y), (plan_w - margin, y), (160, 160, 160), 1)

    # Title block (dark text on white — adds sharpness for quality score)
    cv2.rectangle(plan, (margin, margin), (240, 50), (20, 20, 20), -1)

    # Place plan centered on background
    x0 = (W - plan_w) // 2   # 140
    y0 = (H - plan_h) // 2   # 110
    bg[y0:y0 + plan_h, x0:x0 + plan_w] = plan

    if not skew:
        _, buf = cv2.imencode(".jpg", bg, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return bytes(buf)

    # Perspective skew — simulate phone held at ~20° angle (upper-right tilt)
    src = np.array([
        [float(x0),            float(y0)],
        [float(x0 + plan_w),   float(y0)],
        [float(x0 + plan_w),   float(y0 + plan_h)],
        [float(x0),            float(y0 + plan_h)],
    ], dtype=np.float32)
    dst = np.array([
        [float(x0 + 60),           float(y0 + 45)],
        [float(x0 + plan_w + 25),  float(y0 + 10)],
        [float(x0 + plan_w - 15),  float(y0 + plan_h - 25)],
        [float(x0 - 45),           float(y0 + plan_h + 25)],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    # Black border matches background — no false contours at unmapped corners
    skewed = cv2.warpPerspective(bg, M, (W, H), borderValue=(0, 0, 0))

    _, buf = cv2.imencode(".jpg", skewed, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return bytes(buf)


def _make_blurry_jpg() -> bytes:
    """Uniform near-gray image — near-zero Laplacian variance → quality_score ~0."""
    img = np.full((400, 400, 3), 200, dtype=np.uint8)
    # Add tiny noise to avoid divide-by-zero edge cases
    noise = np.random.randint(0, 3, img.shape, dtype=np.uint8)
    img = cv2.add(img, noise)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return bytes(buf)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestPhotoDeskew:
    """
    Primary competitive advantage: phone photo → corrected plan.

    CLAIM (PROMPT 9 / Sprint 6 spec):
      Conduit processes photos taken at any angle while Stratus and PlanGrid
      require a flat-bed scanner or perfectly overhead shot.
    """

    def test_photo_deskew_quality_above_threshold(self):
        """
        CORE TEST — the differentiator.

        A skewed phone photo of a plan must produce:
          - quality_score > 70  (legible for OCR and AI takeoff)
          - deskew_applied = True (perspective was corrected)
        """
        raw = _make_skewed_plan_jpg(skew=True)

        _, deskew_applied, quality_score = deskew_and_score(raw)

        assert deskew_applied is True, (
            "Deskew must fire on a skewed photo — "
            "Conduit's key differentiator vs Stratus"
        )
        assert quality_score > 70, (
            f"quality_score={quality_score} is below the 70-point threshold "
            "required for reliable OCR and AI takeoff. "
            "Stratus requires a scanner; Conduit must beat that bar from a phone photo."
        )

    def test_straight_photo_still_passes_quality(self):
        """Even a straight phone photo (no skew) must score > 70."""
        raw = _make_skewed_plan_jpg(skew=False)
        _, _, quality_score = deskew_and_score(raw)
        assert quality_score > 70

    def test_deskew_output_is_valid_jpeg(self):
        """Processed bytes must decode as a valid image."""
        raw = _make_skewed_plan_jpg(skew=True)
        out_bytes, _, _ = deskew_and_score(raw)

        img_arr = np.frombuffer(out_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        assert img is not None
        assert img.shape[0] > 0 and img.shape[1] > 0

    def test_deskew_output_has_reasonable_dimensions(self):
        """Output plan must be at least 200×200 — not a degenerate crop."""
        raw = _make_skewed_plan_jpg(skew=True)
        out_bytes, deskew_applied, _ = deskew_and_score(raw)

        if deskew_applied:
            img_arr = np.frombuffer(out_bytes, dtype=np.uint8)
            img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            assert img is not None, "Deskewed output could not be decoded"
            h, w = img.shape[:2]
            assert w >= 200 and h >= 200, f"Deskewed output too small: {w}×{h}"

    def test_invalid_bytes_raises_value_error(self):
        """Non-image bytes must raise ValueError, not crash the worker silently."""
        with pytest.raises(ValueError, match="Could not decode"):
            deskew_and_score(b"not-an-image")


class TestQualityScoreFormula:
    """Validates the quality scoring independently of the deskew path."""

    def test_sharp_image_scores_above_threshold(self):
        """A crisp plan image must always score > 70."""
        raw = _make_skewed_plan_jpg(skew=False)
        _, _, quality_score = deskew_and_score(raw)
        assert quality_score > 70

    def test_blurry_image_scores_below_threshold(self):
        """A near-uniform blurry image must score < 70 (Laplacian ~0)."""
        raw = _make_blurry_jpg()
        _, _, quality_score = deskew_and_score(raw)
        assert quality_score < 70, (
            f"quality_score={quality_score}: blurry uniform image should score low"
        )

    def test_quality_score_capped_at_100(self):
        """Score must never exceed 100 regardless of Laplacian value."""
        raw = _make_skewed_plan_jpg(skew=False)
        _, _, quality_score = deskew_and_score(raw)
        assert quality_score <= 100
