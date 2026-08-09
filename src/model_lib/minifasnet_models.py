# -*- coding: utf-8 -*-
"""
MiniFASNet Model Definitions (Silent-Face-Anti-Spoofing)
---------------------------------------------------------
Official PyTorch implementation of MiniFASNetV1SE and MiniFASNetV2 lightweight anti-spoofing networks:
- MiniFASNetV1SE: Squeeze-and-Excitation enhanced depthwise separable CNN (scale 4.0 crop).
- MiniFASNetV2: Deep residual depthwise separable CNN (scale 2.7 crop).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, List


class L2Norm(nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(x, p=2, dim=1)


class Flatten(nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x.view(x.size(0), -1)


class Conv_block(nn.Module):
    def __init__(self, in_c: int, out_c: int, kernel: Tuple[int, int] = (1, 1), stride: Tuple[int, int] = (1, 1), padding: Tuple[int, int] = (0, 0), groups: int = 1):
        super(Conv_block, self).__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel_size=kernel, groups=groups, stride=stride, padding=padding, bias=False)
        self.bn = nn.BatchNorm2d(out_c)
        self.prelu = nn.PReLU(out_c)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.prelu(self.bn(self.conv(x)))


class Linear_block(nn.Module):
    def __init__(self, in_c: int, out_c: int, kernel: Tuple[int, int] = (1, 1), stride: Tuple[int, int] = (1, 1), padding: Tuple[int, int] = (0, 0), groups: int = 1):
        super(Linear_block, self).__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel_size=kernel, groups=groups, stride=stride, padding=padding, bias=False)
        self.bn = nn.BatchNorm2d(out_c)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.bn(self.conv(x))


class Depth_Wise(nn.Module):
    def __init__(self, c1: Tuple[int, int], c2: Tuple[int, int], c3: Tuple[int, int], residual: bool = False, kernel: Tuple[int, int] = (3, 3), stride: Tuple[int, int] = (2, 2), padding: Tuple[int, int] = (1, 1), groups: int = 1):
        super(Depth_Wise, self).__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = Conv_block(c1_in, out_c=c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = Linear_block(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        short_cut = x if self.residual else None
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)
        if self.residual and short_cut is not None:
            output = short_cut + x
        else:
            output = x
        return output


class Multi_Depth_Wise(nn.Module):
    def __init__(self, num_block: int, keep: list, residual: bool = True, kernel: Tuple[int, int] = (3, 3), stride: Tuple[int, int] = (1, 1), padding: Tuple[int, int] = (1, 1), groups: int = 1):
        super(Multi_Depth_Wise, self).__init__()
        modules = []
        for i in range(num_block):
            c1 = (keep[i * 3], keep[i * 3 + 1])
            c2 = (keep[i * 3 + 1], keep[i * 3 + 2])
            c3 = (keep[i * 3 + 2], keep[i * 3 + 3])
            modules.append(Depth_Wise(c1, c2, c3, residual=residual, kernel=kernel, stride=stride, padding=padding, groups=groups))
        self.model = nn.Sequential(*modules)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


class ResidualSE(nn.Module):
    def __init__(self, c1: Tuple[int, int], c2: Tuple[int, int], c3: Tuple[int, int], num_squeeze: int = 4, residual: bool = False, kernel: Tuple[int, int] = (3, 3), stride: Tuple[int, int] = (2, 2), padding: Tuple[int, int] = (1, 1), groups: int = 1):
        super(ResidualSE, self).__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = Conv_block(c1_in, out_c=c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = Linear_block(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))

        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.se_fc1 = nn.Conv2d(c3_out, c3_out // num_squeeze, kernel_size=(1, 1), bias=False)
        self.se_bn1 = nn.BatchNorm2d(c3_out // num_squeeze)
        self.se_fc2 = nn.Conv2d(c3_out // num_squeeze, c3_out, kernel_size=(1, 1), bias=False)
        self.se_bn2 = nn.BatchNorm2d(c3_out)
        self.residual = residual

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        short_cut = x if self.residual else None
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)

        y = self.avg_pool(x)
        y = F.relu(self.se_bn1(self.se_fc1(y)))
        y = torch.sigmoid(self.se_bn2(self.se_fc2(y)))
        x = x * y

        if self.residual and short_cut is not None:
            output = short_cut + x
        else:
            output = x
        return output


class Multi_ResidualSE(nn.Module):
    def __init__(self, num_block: int, keep: list, num_squeeze: int = 4, residual: bool = True, kernel: Tuple[int, int] = (3, 3), stride: Tuple[int, int] = (1, 1), padding: Tuple[int, int] = (1, 1), groups: int = 1):
        super(Multi_ResidualSE, self).__init__()
        modules = []
        for i in range(num_block):
            c1 = (keep[i * 3], keep[i * 3 + 1])
            c2 = (keep[i * 3 + 1], keep[i * 3 + 2])
            c3 = (keep[i * 3 + 2], keep[i * 3 + 3])
            modules.append(ResidualSE(c1, c2, c3, num_squeeze=num_squeeze, residual=residual, kernel=kernel, stride=stride, padding=padding, groups=groups))
        self.model = nn.Sequential(*modules)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


keep_dict = {
    '1.8M': [
        32, 32, 103, 103, 64,
        13, 13, 64, 26, 26, 64, 13, 13, 64, 52, 52, 64,
        231, 231, 128,
        154, 154, 128, 52, 52, 128, 26, 26, 128, 52, 52, 128, 26, 26, 128, 26, 26, 128,
        308, 308, 128,
        26, 26, 128, 26, 26, 128,
        512, 512
    ],
    '1.8M_': [
        32, 32, 103, 103, 64,
        13, 13, 64, 13, 13, 64, 13, 13, 64, 13, 13, 64,
        231, 231, 128,
        231, 231, 128, 52, 52, 128, 26, 26, 128, 77, 77, 128, 26, 26, 128, 26, 26, 128,
        308, 308, 128,
        26, 26, 128, 26, 26, 128,
        512, 512
    ]
}


class MiniFASNet(nn.Module):
    """MiniFASNetV2 base model."""
    def __init__(self, keep: list, embedding_size: int = 128, conv6_kernel: Tuple[int, int] = (5, 5), drop_p: float = 0.2, num_classes: int = 3, img_channel: int = 3):
        super(MiniFASNet, self).__init__()
        self.embedding_size = embedding_size

        self.conv1 = Conv_block(img_channel, keep[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1))
        self.conv2_dw = Conv_block(keep[0], keep[1], kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[0])

        self.conv_23 = Depth_Wise((keep[1], keep[2]), (keep[2], keep[3]), (keep[3], keep[4]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[3])
        self.conv_3 = Multi_Depth_Wise(4, keep[4:17], residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[6])
        self.conv_34 = Depth_Wise((keep[16], keep[17]), (keep[17], keep[18]), (keep[18], keep[19]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[18])
        self.conv_4 = Multi_Depth_Wise(6, keep[19:38], residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[21])

        self.conv_45 = Depth_Wise((keep[37], keep[38]), (keep[38], keep[39]), (keep[39], keep[40]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[39])
        self.conv_5 = Multi_Depth_Wise(2, keep[40:47], residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[42])
        self.conv_6_sep = Conv_block(keep[46], keep[47], kernel=(1, 1), stride=(1, 1), padding=(0, 0))
        self.conv_6_dw = Linear_block(keep[47], keep[47], kernel=conv6_kernel, stride=(1, 1), padding=(0, 0), groups=keep[47])
        self.conv_6_flatten = Flatten()

        self.linear = nn.Linear(keep[47], embedding_size, bias=False)
        self.bn = nn.BatchNorm1d(embedding_size)
        self.drop = nn.Dropout(p=drop_p)
        self.prob = nn.Linear(embedding_size, num_classes, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)
        x = self.conv2_dw(x)
        x = self.conv_23(x)
        x = self.conv_3(x)
        x = self.conv_34(x)
        x = self.conv_4(x)
        x = self.conv_45(x)
        x = self.conv_5(x)
        x = self.conv_6_sep(x)
        x = self.conv_6_dw(x)
        x = self.conv_6_flatten(x)

        x = self.linear(x)
        x = self.bn(x)
        x = self.drop(x)
        x = self.prob(x)
        return x


class MiniFASNetSE(nn.Module):
    """MiniFASNetV1SE model with Squeeze-and-Excitation modules."""
    def __init__(self, keep: list, embedding_size: int = 128, conv6_kernel: Tuple[int, int] = (5, 5), drop_p: float = 0.75, num_classes: int = 3, img_channel: int = 3):
        super(MiniFASNetSE, self).__init__()
        self.embedding_size = embedding_size

        self.conv1 = Conv_block(img_channel, keep[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1))
        self.conv2_dw = Conv_block(keep[0], keep[1], kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[0])

        self.conv_23 = Depth_Wise((keep[1], keep[2]), (keep[2], keep[3]), (keep[3], keep[4]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[3])
        self.conv_3 = Multi_ResidualSE(4, keep[4:17], num_squeeze=4, residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[6])
        self.conv_34 = Depth_Wise((keep[16], keep[17]), (keep[17], keep[18]), (keep[18], keep[19]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[18])
        self.conv_4 = Multi_ResidualSE(6, keep[19:38], num_squeeze=4, residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[21])

        self.conv_45 = Depth_Wise((keep[37], keep[38]), (keep[38], keep[39]), (keep[39], keep[40]), kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[39])
        self.conv_5 = Multi_ResidualSE(2, keep[40:47], num_squeeze=4, residual=True, kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[42])
        self.conv_6_sep = Conv_block(keep[46], keep[47], kernel=(1, 1), stride=(1, 1), padding=(0, 0))
        self.conv_6_flatten = Flatten()

        self.linear = nn.Linear(keep[47], embedding_size, bias=False)
        self.bn = nn.BatchNorm1d(embedding_size)
        self.drop = nn.Dropout(p=drop_p)
        self.prob = nn.Linear(embedding_size, num_classes, bias=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x)
        x = self.conv2_dw(x)
        x = self.conv_23(x)
        x = self.conv_3(x)
        x = self.conv_34(x)
        x = self.conv_4(x)
        x = self.conv_45(x)
        x = self.conv_5(x)
        x = self.conv_6_sep(x)
        x = F.adaptive_avg_pool2d(x, (1, 1))
        x = self.conv_6_flatten(x)

        x = self.linear(x)
        x = self.bn(x)
        x = self.drop(x)
        x = self.prob(x)
        return x


def MiniFASNetV1SE(embedding_size: int = 128, conv6_kernel: Tuple[int, int] = (5, 5), drop_p: float = 0.75, num_classes: int = 3, img_channel: int = 3) -> MiniFASNetSE:
    return MiniFASNetSE(keep_dict['1.8M'], embedding_size, conv6_kernel, drop_p, num_classes, img_channel)


def MiniFASNetV2(embedding_size: int = 128, conv6_kernel: Tuple[int, int] = (5, 5), drop_p: float = 0.2, num_classes: int = 3, img_channel: int = 3) -> MiniFASNet:
    return MiniFASNet(keep_dict['1.8M_'], embedding_size, conv6_kernel, drop_p, num_classes, img_channel)
