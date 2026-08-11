# -*- coding: utf-8 -*-
"""
Test User Guidance Messages & Lightweight Quality Filters
--------------------------------------------------------
Verifies lightweight O(1) user guidance messages:
  - Low Light -> "Please move to a brighter area."
  - Too Far -> "Please move closer to the camera."
  - Off-Center -> "Please center your face in the frame."
"""

import os
import sys
import cv2
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.pipeline.services.anti_spoof_service import anti_spoof_service
from src.pipeline.config import settings


def main():
    print("=" * 80)
    print("LIGHTWEIGHT USER GUIDANCE MESSAGES & QUALITY FILTER TEST")
    print("=" * 80)

    # Test 1: Dark Image (Low Light)
    dark_img = np.zeros((480, 640, 3), dtype=np.uint8) + 15
    msg1 = anti_spoof_service._evaluate_lightweight_guidance(dark_img, bbox=[200, 200, 100, 100])
    print(f"Test 1 - Dark Frame Guidance:     '{msg1}'")
    assert msg1 == settings.MSG_LOW_LIGHT, f"Expected '{settings.MSG_LOW_LIGHT}', got '{msg1}'"
    print("  -> TEST 1 (Low Light Message) = PASS")

    # Test 2: Small Face (Too Far)
    normal_img = np.zeros((480, 640, 3), dtype=np.uint8) + 120
    small_bbox = [300, 200, 30, 30]  # Very small face bbox
    msg2 = anti_spoof_service._evaluate_lightweight_guidance(normal_img, bbox=small_bbox)
    print(f"Test 2 - Small Face Guidance:    '{msg2}'")
    assert msg2 == settings.MSG_TOO_FAR, f"Expected '{settings.MSG_TOO_FAR}', got '{msg2}'"
    print("  -> TEST 2 (Too Far Message) = PASS")

    # Test 3: Off-Center Face
    off_center_bbox = [10, 10, 150, 150]  # Far corner bbox
    msg3 = anti_spoof_service._evaluate_lightweight_guidance(normal_img, bbox=off_center_bbox)
    print(f"Test 3 - Off-Center Guidance:   '{msg3}'")
    assert msg3 == settings.MSG_OFF_CENTER, f"Expected '{settings.MSG_OFF_CENTER}', got '{msg3}'"
    print("  -> TEST 3 (Off-Center Message) = PASS")

    # Test 4: Optimal Frame (No Guidance Message Needed)
    centered_bbox = [240, 180, 160, 160]  # Well centered
    msg4 = anti_spoof_service._evaluate_lightweight_guidance(normal_img, bbox=centered_bbox)
    print(f"Test 4 - Optimal Frame Guidance: '{msg4}'")
    assert msg4 is None, f"Expected None, got '{msg4}'"
    print("  -> TEST 4 (Optimal Frame) = PASS")

    print("\n>>> ALL 4 USER GUIDANCE TESTS PASSED SUCCESSFULLY! <<<\n")


if __name__ == "__main__":
    main()
