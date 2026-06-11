# _*_coding:utf-8_*_

import time
from abc import abstractmethod
from collections import defaultdict

import numpy as np


class FuzzQueue(object):
    """Class that holds inputs and associated coverage."""

    def __init__(self,
                 outdir,
                 selection_strategy,
                 criteria,
                 check_point,
                 DUMPS,
                 nb_class=10):
        """Init the class.
        """

        self.out_dir = outdir
        self.mutations_processed = 0
        self.queue = {}
        self.frd_score = {}
        self.frd_fname = {}
        self.start_time = time.time()

        self.selection_strategy = selection_strategy
        self.criteria = criteria
        self.check_point = check_point
        self.DUMPS = DUMPS

        self.log_time = time.time()
        # Like AFL, it records the coverage of the seeds in the queue

        self.diverse_num_bins = np.zeros((nb_class, nb_class), dtype="int32")
        self.diverse_iter_bins = np.zeros((nb_class, nb_class), dtype="int32")

        self.uniq_crashes = 0
        self.total_queue = 0

        # Some log information
        self.last_crash_time = self.start_time
        self.last_reg_time = self.start_time
        self.current_id = 0
        self.seed_attacked = set()
        self.seed_bugs = defaultdict(int)
        self.seed_attacked_first_time = dict()

        self.dry_run_cov = None

        # REG_MIN and REG_GAMMA are the p_min and gamma in Equation 3
        self.REG_GAMMA = 5
        self.REG_MIN = 0.3
        self.REG_INIT_PROB = 0.8

    def select_next(self, num=4):
        return self._select(num)

    def _select(self, num):
        ret = []
        for _i in range(num):
            ret.append(self._select_())
        return ret

    def _select_(self):
        scene_list = np.array(list(self.DUMPS['prob'].items()))

        prob = scene_list[:, 1].astype(np.float32)
        scene_list = scene_list[:, 0]

        prob /= np.sum(prob)

        scene = np.random.choice(scene_list, p=prob)

        prob = self.queue[scene][:, 1].astype(np.float32)
        prob /= np.sum(prob)
        return np.random.choice(self.queue[scene][:, 0], p=prob)

    @abstractmethod
    def save_if_interesting(self,
                            seed,
                            data,
                            crash,
                            dry_run=False,
                            suffix=None):
        pass
