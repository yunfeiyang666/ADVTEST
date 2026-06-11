# import pyflann
import time
import numpy as np

# import tensorflow as tf
from _lib.queue.queue import FuzzQueue


class TensorInputCorpus(FuzzQueue):
    """Class that holds inputs and associated coverage."""

    def __init__(self, outdir, israndom, sample_function, threshold, algorithm):
        """Init the class.

        Args:
          seed_corpus: a list of numpy arrays, one for each input tensor in the
            fuzzing process.
          sample_function: a function that looks at the whole current corpus and
            samples the next element to mutate in the fuzzing loop.
        Returns:
          Initialized object.
        """

        FuzzQueue.__init__(self, outdir, israndom, sample_function, 1, 'Near')

        # self.flann = pyflann.FLANN()
        self.flann = None
        self.threshold = threshold
        self.algorithm = algorithm
        self.corpus_buffer = []
        self.lookup_array = []
        self._BUFFER_SIZE = 50

    def is_interesting(self, seed):

        _, approx_distances = self.flann.nn_index(
            seed.coverage, 1, algorithm=self.algorithm
        )
        exact_distances = [
            np.sum(np.square(seed.coverage - buffer_elt))
            for buffer_elt in self.corpus_buffer
        ]
        nearest_distance = min(exact_distances + approx_distances.tolist())

        return nearest_distance > self.threshold or self.random

    def build_index_and_flush_buffer(self):
        """Builds the nearest neighbor index and flushes buffer of examples.
        This method first empties the buffer of examples that have not yet
        been added to the nearest neighbor index.
        Then it rebuilds that index using the contents of the whole corpus.
        Args:
          corpus_object: InputCorpus object.
        """
        tf.logging.info("Total %s Flushing buffer and building index.", len(self.corpus_buffer))
        self.corpus_buffer[:] = []
        self.lookup_array = np.array(
            [element.coverage for element in self.queue]
        )
        self.flann.build_index(self.lookup_array, algorithm=self.algorithm)

    def save_if_interesting(self, seed, data, crash, dry_run=False, suffix=None):

        if len(self.corpus_buffer) >= self._BUFFER_SIZE or len(self.queue) == 1:
            self.build_index_and_flush_buffer()

        self.mutations_processed += 1
        current_time = time.time()
        if dry_run:
            self.dry_run_cov = 0
        if current_time - self.log_time > 2:
            self.log_time = current_time
            self.log()

        if seed.parent is None:
            describe_op = "src:%s" % (suffix)
        else:
            describe_op = "src:%06d:%s" % (seed.parent.id, '' if suffix is None else suffix)

        if crash:
            fn = "%s/crashes/id:%06d_%s.npy" % (self.out_dir, self.uniq_crashes, describe_op)
            self.uniq_crashes += 1
            self.last_crash_time = current_time
        else:
            fn = "%s/queue/id:%06d_%s.npy" % (self.out_dir, self.total_queue, describe_op)
            if dry_run or self.is_interesting(seed):
                self.last_reg_time = current_time
                seed.queue_time = current_time
                seed.id = self.total_queue
                seed.fname = fn
                seed.probability = self.REG_INIT_PROB
                self.queue.append(seed)
                self.corpus_buffer.append(seed.coverage)
                # del seed.coverage
                self.total_queue += 1
            else:
                del seed
                return False
        np.save(fn, data)
        return True
