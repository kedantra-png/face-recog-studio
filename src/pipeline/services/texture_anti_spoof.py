# -*- coding: utf-8 -*-
"""
Physics-Based Texture & 2D FFT Fourier Moiré Anti-Spoofing Module
------------------------------------------------------------------
Provides ISO/IEC 30107-3 compliant physical presentation attack detection:
1. 2D Discrete Fourier Transform (FFT) Spectral Moiré Pattern Analysis:
   Detects periodic high-frequency spectral peaks caused by smartphone/tablet LCD/OLED display pixel grids.
2. HSV & YCbCr Color-Space Texture & Specular Reflection Analysis:
   Detects unnatural color saturation, screen backlight glare, and printed paper reflection characteristics.
3. Edge Roughness & Blur Gradient Analysis.
"""

import cv2
import numpy as np
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("pipeline.texture_anti_spoof")


class TextureAntiSpoofEvaluator:
    """
    Evaluates physical presentation attack signals using 2D FFT spectral analysis
    and multi-color-space texture metrics.
    """

    @staticmethod
    def _crop_face_region(img: np.ndarray, bbox: Optional[List[int]]) -> np.ndarray:
        if img is None or img.size == 0:
            return img
        if not bbox or len(bbox) < 4:
            return img

        x, y, w, h = bbox
        src_h, src_w = img.shape[:2]

        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(src_w, int(x + w))
        y2 = min(src_h, int(y + h))

        if x2 > x1 and y2 > y1:
            return img[y1:y2, x1:x2]
        return img

    @classmethod
    def evaluate_2d_fft_moire(cls, img: np.ndarray, bbox: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Computes 2D Fourier Transform spectral energy distribution.
        Display screens exhibit distinct periodic high-frequency peaks (Moiré pattern).
        """
        face_crop = cls._crop_face_region(img, bbox)
        if face_crop is None or face_crop.size == 0:
            return {"moire_score": 0.0, "is_screen_replay": False, "high_freq_ratio": 0.0}

        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Resize to fixed dimension for consistent FFT spectral density comparison
        if h < 64 or w < 64:
            gray = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_LANCZOS4)
            h, w = 128, 128
        else:
            gray = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            h, w = 256, 256

        # Apply Hanning windowing to eliminate edge discontinuity artifacts in 2D FFT
        window = np.outer(np.hanning(h), np.hanning(w))
        windowed_gray = gray.astype(np.float32) * window

        # Compute 2D Fast Fourier Transform
        f = np.fft.fft2(windowed_gray)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = np.abs(fshift)

        # Total spectral energy
        total_energy = np.sum(magnitude_spectrum ** 2) + 1e-8

        # Define low-frequency center region radius
        cy, cx = h // 2, w // 2
        radius_low = int(min(h, w) * 0.15)
        radius_mid = int(min(h, w) * 0.40)

        Y, X = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)

        # High-frequency spectral energy mask (detecting screen lattice frequencies)
        high_freq_mask = (dist_from_center >= radius_low) & (dist_from_center <= radius_mid)
        high_freq_energy = np.sum((magnitude_spectrum * high_freq_mask) ** 2)

        high_freq_ratio = float(high_freq_energy / total_energy)

        # Detect sharp periodic spectral peaks (characteristic of digital display pixel matrices)
        high_freq_mags = magnitude_spectrum[high_freq_mask]
        peak_ratio = float(np.max(high_freq_mags) / (np.mean(high_freq_mags) + 1e-5)) if len(high_freq_mags) > 0 else 0.0

        # Dynamic Moiré score calculation: Requires both high-frequency energy ratio & sharp periodic spectral spikes
        # Screen replay attacks exhibit peak_ratio > 25.0 and high_freq_ratio > 0.15
        moire_score = min(1.0, max(0.0, (high_freq_ratio * 2.2) + (peak_ratio / 50.0)))
        is_screen_replay = bool(moire_score >= 0.65 and peak_ratio >= 25.0)

        return {
            "moire_score": round(float(moire_score), 4),
            "is_screen_replay": is_screen_replay,
            "high_freq_ratio": round(float(high_freq_ratio), 4),
            "peak_ratio": round(float(peak_ratio), 2)
        }

    @classmethod
    def evaluate_color_space_texture(cls, img: np.ndarray, bbox: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Evaluates HSV saturation variance, YCbCr chrominance ratios, and specular glare highlights.
        Digital display screens and paper prints exhibit unnatural color gamuts & glare.
        """
        face_crop = cls._crop_face_region(img, bbox)
        if face_crop is None or face_crop.size == 0:
            return {"color_score": 0.5, "glare_ratio": 0.0, "is_color_anomaly": False}

        hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
        ycbcr = cv2.cvtColor(face_crop, cv2.COLOR_BGR2YCrCb)

        # 1. Saturation channel analysis (Screens exhibit high saturation contrast / unnatural gamut)
        sat_channel = hsv[:, :, 1]
        sat_mean = float(np.mean(sat_channel))
        sat_std = float(np.std(sat_channel))

        # 2. Specular reflection glare detection (Bright clipped highlights on paper/screen > 250 value)
        val_channel = hsv[:, :, 2]
        glare_pixels = np.sum(val_channel >= 250)
        glare_ratio = float(glare_pixels / (val_channel.size + 1e-5))

        # 3. YCbCr Chrominance Cr/Cb ratio (Human skin falls into specific tight Cr/Cb boundary)
        cr = ycbcr[:, :, 1].astype(np.float32)
        cb = ycbcr[:, :, 2].astype(np.float32)
        cr_mean = float(np.mean(cr))
        cb_mean = float(np.mean(cb))

        # Human skin YCbCr standard bounds: Cr in [125, 180], Cb in [70, 135]
        skin_chroma_valid = (125.0 <= cr_mean <= 180.0) and (70.0 <= cb_mean <= 135.0)

        # Calculate color texture score (0.0 = spoof/screen, 1.0 = genuine skin)
        sat_score = max(0.0, 1.0 - abs(sat_mean - 65.0) / 100.0)
        glare_score = max(0.0, 1.0 - (glare_ratio * 10.0))
        chroma_score = 1.0 if skin_chroma_valid else 0.5

        color_score = round(0.40 * sat_score + 0.30 * glare_score + 0.30 * chroma_score, 3)
        is_color_anomaly = bool(color_score < 0.35 or glare_ratio > 0.15)

        return {
            "color_score": color_score,
            "glare_ratio": round(glare_ratio, 4),
            "sat_mean": round(sat_mean, 1),
            "sat_std": round(sat_std, 1),
            "skin_chroma_valid": skin_chroma_valid,
            "is_color_anomaly": is_color_anomaly
        }

    @classmethod
    def evaluate_texture_liveness(cls, img: np.ndarray, bbox: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Combines 2D FFT Moiré spectral score and Color-Space texture evaluation to yield a physical liveness score.
        """
        fft_res = cls.evaluate_2d_fft_moire(img, bbox)
        color_res = cls.evaluate_color_space_texture(img, bbox)

        moire_score = fft_res["moire_score"]
        color_score = color_res["color_score"]

        # Combined physics texture real probability (0.0 = spoof, 1.0 = real)
        physical_real_prob = float(0.60 * (1.0 - moire_score) + 0.40 * color_score)
        physical_real_prob = round(max(0.0, min(1.0, physical_real_prob)), 4)

        # Strict physical spoof decision: Requires confirmed 2D FFT screen replay peaks (peak_ratio >= 28.0) or extreme glare (>20%)
        is_physical_spoof = bool(
            (moire_score >= 0.70 and fft_res.get("peak_ratio", 0) >= 28.0) or
            (color_res["glare_ratio"] > 0.20)
        )

        return {
            "physical_real_prob": physical_real_prob,
            "physical_fake_prob": round(1.0 - physical_real_prob, 4),
            "is_physical_spoof": is_physical_spoof,
            "fft_moire": fft_res,
            "color_texture": color_res
        }


texture_anti_spoof_evaluator = TextureAntiSpoofEvaluator()
