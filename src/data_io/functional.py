# -*- coding: utf-8 -*-
"""
Data IO Functional Module
------------------------
Official Minivision Silent-Face-Anti-Spoofing data transformation functional tools.
"""

from __future__ import division
import torch
import numpy as np


def _is_tensor_image(img):
    return torch.is_tensor(img) and img.ndimension() == 3


def _is_numpy_image(img):
    return isinstance(img, np.ndarray) and (img.ndim in {2, 3})


def to_tensor(pic):
    """
    Convert a numpy.ndarray (H x W x C) to float Tensor (C x H x W) in range [0.0, 255.0].
    Note: Minivision MiniFASNet models expect un-normalized float tensors in range [0.0, 255.0]!
    """
    if not _is_numpy_image(pic):
        raise TypeError('pic should be ndarray. Got {}'.format(type(pic)))

    if isinstance(pic, np.ndarray):
        if pic.ndim == 2:
            pic = pic.reshape((pic.shape[0], pic.shape[1], 1))

        img = torch.from_numpy(pic.transpose((2, 0, 1)))
        # Note: Minivision model training uses float() without div(255)!
        return img.float()
