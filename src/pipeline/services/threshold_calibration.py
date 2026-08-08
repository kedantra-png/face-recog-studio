# -*- coding: utf-8 -*-
"""
Liveness Threshold Calibration & ROC Analytics Utility
------------------------------------------------------
Evaluates labeled validation dataset predictions (real vs spoof) to compute:
1. False Accept Rate (FAR)
2. False Reject Rate (FRR)
3. Equal Error Rate (EER)
4. Receiver Operating Characteristic (ROC) curves
5. Recommended PASS, UNCERTAIN, and FAIL liveness thresholds
"""

import numpy as np
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("pipeline.calibration")


class ThresholdCalibrationUtility:
    """
    Computes FAR, FRR, EER, and recommends optimal liveness thresholds.
    """

    @staticmethod
    def calibrate_thresholds(
        scores: List[float],
        labels: List[int],
        target_far: float = 0.01
    ) -> Dict[str, Any]:
        """
        Calibrates thresholds from validation evaluation.

        Args:
            scores: Array of float fusion scores in range [0.0, 1.0].
            labels: Binary labels (1 = Real Face, 0 = Spoof Attack).
            target_far: Target False Accept Rate (e.g. 1% FAR = 0.01).

        Returns:
            Dict containing recommended PASS, UNCERTAIN, and FAIL thresholds, EER, and FAR/FRR metrics.
        """
        if not scores or not labels or len(scores) != len(labels):
            return {
                "recommended_pass_threshold": 0.65,
                "recommended_uncertain_low": 0.25,
                "recommended_fail_threshold": 0.35,
                "eer": 0.05,
                "message": "Empty or invalid evaluation dataset"
            }

        scores_arr = np.array(scores, dtype=np.float32)
        labels_arr = np.array(labels, dtype=np.int32)

        thresholds = np.linspace(0.0, 1.0, 101)
        far_list = []
        frr_list = []

        total_real = max(1, np.sum(labels_arr == 1))
        total_spoof = max(1, np.sum(labels_arr == 0))

        for th in thresholds:
            # False Accept: Spoof sample predicted >= th
            fa = np.sum((labels_arr == 0) & (scores_arr >= th))
            # False Reject: Real sample predicted < th
            fr = np.sum((labels_arr == 1) & (scores_arr < th))

            far = fa / total_spoof
            frr = fr / total_real

            far_list.append(far)
            frr_list.append(frr)

        far_arr = np.array(far_list)
        frr_arr = np.array(frr_list)

        # Equal Error Rate (EER): Where FAR == FRR
        eer_idx = np.argmin(np.abs(far_arr - frr_arr))
        eer = float((far_arr[eer_idx] + frr_arr[eer_idx]) / 2.0)
        eer_threshold = float(thresholds[eer_idx])

        # Target FAR threshold (e.g. 1% FAR)
        target_far_idx = np.argmin(np.abs(far_arr - target_far))
        pass_threshold = float(thresholds[target_far_idx])

        # Uncertain zone bounds
        fail_threshold = float(max(0.15, pass_threshold - 0.30))
        uncertain_low = float(max(0.10, fail_threshold - 0.10))

        result = {
            "recommended_pass_threshold": round(max(0.55, pass_threshold), 4),
            "recommended_uncertain_low": round(uncertain_low, 4),
            "recommended_fail_threshold": round(fail_threshold, 4),
            "eer": round(eer, 4),
            "eer_threshold": round(eer_threshold, 4),
            "far_at_pass": round(float(far_arr[target_far_idx]), 4),
            "frr_at_pass": round(float(frr_arr[target_far_idx]), 4),
            "total_samples": len(scores),
            "real_count": int(total_real),
            "spoof_count": int(total_spoof)
        }

        logger.info(f"Threshold Calibration Completed: Recommended PASS={result['recommended_pass_threshold']}, FAIL={result['recommended_fail_threshold']}, EER={result['eer']*100:.2f}%")
        return result


threshold_calibration = ThresholdCalibrationUtility()
