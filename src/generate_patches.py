# -*- coding: utf-8 -*-
"""
MiniFASNet Multi-Scale Patch Generator Module
---------------------------------------------
Generates scaled image crops for Silent-Face-Anti-Spoofing MiniFASNet models.
"""

import cv2
import numpy as np
from typing import List


class CropImage:
    """
    Minivision Silent-Face-Anti-Spoofing patch crop generator.
    """
    @staticmethod
    def _get_new_box(src_w: int, src_h: int, bbox: List[int], scale: float):
        x = bbox[0]
        y = bbox[1]
        box_w = bbox[2]
        box_h = bbox[3]

        scale = min((src_h - 1) / max(1.0, float(box_h)), min((src_w - 1) / max(1.0, float(box_w)), float(scale)))

        new_width = box_w * scale
        new_height = box_h * scale
        center_x, center_y = box_w / 2.0 + x, box_h / 2.0 + y

        left_top_x = center_x - new_width / 2.0
        left_top_y = center_y - new_height / 2.0
        right_bottom_x = center_x + new_width / 2.0
        right_bottom_y = center_y + new_height / 2.0

        if left_top_x < 0:
            right_bottom_x -= left_top_x
            left_top_x = 0
        if left_top_y < 0:
            right_bottom_y -= left_top_y
            left_top_y = 0
        if right_bottom_x >= src_w:
            left_top_x -= (right_bottom_x - src_w + 1)
            right_bottom_x = src_w - 1
        if right_bottom_y >= src_h:
            left_top_y -= (right_bottom_y - src_h + 1)
            right_bottom_y = src_h - 1

        return int(left_top_x), int(left_top_y), int(right_bottom_x), int(right_bottom_y)

    @staticmethod
    def crop(img: np.ndarray, bbox: List[int], scale: float, out_w: int = 80, out_h: int = 80) -> np.ndarray:
        if img is None or img.size == 0 or not bbox or len(bbox) < 4:
            return cv2.resize(img, (out_w, out_h)) if (img is not None and img.size > 0) else np.zeros((out_h, out_w, 3), dtype=np.uint8)

        src_h, src_w, _ = img.shape
        x1, y1, x2, y2 = CropImage._get_new_box(src_w, src_h, bbox, scale)
        crop_img = img[y1:y2, x1:x2]

        if crop_img.size == 0:
            return cv2.resize(img, (out_w, out_h))

        return cv2.resize(crop_img, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
