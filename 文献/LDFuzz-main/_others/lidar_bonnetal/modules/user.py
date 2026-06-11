#!/usr/bin/env python3
# This file is covered by the LICENSE file in the root of this project.

import torch
import torch.backends.cudnn as cudnn
import numpy as np

from .segmentator import *
from ..postproc.KNN import KNN

from ..dataset.kitti.parser import Parser


class User():

    def __init__(self, ARCH, DATA, modeldir):
        # parameters
        self.ARCH = ARCH
        self.DATA = DATA
        self.modeldir = modeldir

        self.parser = Parser(color_map=self.DATA["color_map"],
                             learning_map=self.DATA["learning_map"],
                             learning_map_inv=self.DATA["learning_map_inv"],
                             sensor=self.ARCH["dataset"]["sensor"],
                             max_points=self.ARCH["dataset"]["max_points"],
                             batch_size=1,
                             workers=self.ARCH["train"]["workers"])

        # concatenate the encoder and the head
        with torch.no_grad():
            self.model = Segmentator(self.ARCH, self.parser.get_n_classes(),
                                     self.modeldir)

        # use knn post processing?
        self.post = None
        if self.ARCH["post"]["KNN"]["use"]:
            self.post = KNN(self.ARCH["post"]["KNN"]["params"],
                            self.parser.get_n_classes())

        # GPU?
        self.gpu = False
        self.model_single = self.model
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")
        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            cudnn.benchmark = True
            cudnn.fastest = True
            self.gpu = True
            self.model.cuda()

    def infer(self, from_point_cloud):
        return self.infer_subset(
            loader=self.parser.get_test_set(from_point_cloud),
            to_orig_fn=self.parser.to_original)

    def infer_subset(self, loader, to_orig_fn):
        # switch to evaluate mode
        self.model.eval()

        # empty the cache to infer in high res
        if self.gpu:
            torch.cuda.empty_cache()

        with torch.no_grad():

            for i, (proj_in, proj_mask, _, _, p_x, p_y, proj_range,
                    unproj_range, _, _, _, _, npoints) in enumerate(loader):
                # first cut to rela size (batch size one allows it)
                p_x = p_x[0, :npoints]
                p_y = p_y[0, :npoints]
                proj_range = proj_range[0, :npoints]
                unproj_range = unproj_range[0, :npoints]

                if self.gpu:
                    proj_in = proj_in.cuda()
                    proj_mask = proj_mask.cuda()
                    p_x = p_x.cuda()
                    p_y = p_y.cuda()
                    if self.post:
                        proj_range = proj_range.cuda()
                        unproj_range = unproj_range.cuda()

                # compute output
                proj_output, x_numpy = self.model(proj_in, proj_mask)
                return x_numpy
