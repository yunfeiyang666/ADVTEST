class Seed(object):
    """Class representing a single element of a corpus."""

    def __init__(self, root_seed, parent):
        """Inits the object.

        Args:
          cl: a transformation state to represent whether this seed has been
          coverage: a list to show the coverage
          root_seed: maintain the initial seed from which the current seed is sequentially mutated
          metadata: the prediction result
          ground_truth: the ground truth of the current seed

          l0_ref, linf_ref: if the current seed is mutated from affine transformation, we will record the l0, l_inf
          between initial image and the reference image. i.e., L0(s_0,s_{j-1}) L_inf(s_0,s_{j-1})  in Equation 2 of the paper
        Returns:
          Initialized object.
        """

        self.parent = parent
        self.root_seed = root_seed
        self.queue_time = None
        self.id = None
        self.cal_frd_with = None if parent is None else parent.cal_frd_with
        self.fuzzed_time = 0
