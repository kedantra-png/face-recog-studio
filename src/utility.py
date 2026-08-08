# -*- coding: utf-8 -*-
"""
MiniFASNet Utility Helper Functions
-----------------------------------
Utility functions for parsing model names and conv6 kernel sizes.
"""

import os
from typing import Tuple, List, Dict, Any


def parse_model_name(model_name: str) -> Dict[str, Any]:
    """
    Parses model name parameters such as scale, height, width, model_type.
    e.g. 4_0_0_80x80_MiniFASNetV1SE.pth -> scale=4.0, h=80, w=80, name=MiniFASNetV1SE
    """
    basename = os.path.basename(model_name)
    parts = basename.split('_')
    info = {
        'scale': 2.7,
        'height': 80,
        'width': 80,
        'model_type': 'MiniFASNetV2'
    }

    try:
        if len(parts) >= 4:
            if '80x80' in basename:
                info['height'] = 80
                info['width'] = 80

            if 'MiniFASNetV1SE' in basename:
                info['model_type'] = 'MiniFASNetV1SE'
                info['scale'] = 4.0
            elif 'MiniFASNetV2' in basename:
                info['model_type'] = 'MiniFASNetV2'
                info['scale'] = 2.7
    except Exception:
        pass

    return info


def get_kernel(height: int, width: int) -> Tuple[int, int]:
    """Returns Conv6 kernel dimensions based on crop size (5x5 for 80x80 crop)."""
    return (int(height / 16), int(width / 16))
