import yaml
from pathlib import Path
from functools import partial
from easydict import EasyDict as Dict
from torch.utils.data import DataLoader

from pcdet.utils import common_utils

from pcdet.datasets import DatasetTemplate

from utils.kitti import KittiDataset
from utils.nuscenes import NuScenesDataset

__all__ = {
    'DatasetTemplate': DatasetTemplate,
    'KittiDataset': KittiDataset,
    'NuScenesDataset': NuScenesDataset,
}


def create_dataloader(dataset_cfg, batch_size=1, training=True):

    if isinstance(dataset_cfg, str):
        dataset_cfg = Dict(yaml.safe_load(open(dataset_cfg)))
    elif not isinstance(dataset_cfg, Dict):
        raise Exception

    return _build_dataloader(
        dataset_cfg=dataset_cfg,
        class_names=dataset_cfg.CLASS_NAMES,
        batch_size=batch_size,
        dist=False,
        root_path=Path(dataset_cfg.DATA_PATH),
        logger=common_utils.create_logger(f'{dataset_cfg.DATASET}_log.log'),
        training=training,
    )


def _build_dataloader(dataset_cfg,
                      class_names,
                      batch_size,
                      dist,
                      root_path=None,
                      workers=4,
                      seed=None,
                      logger=None,
                      training=True,
                      merge_all_iters_to_one_epoch=False,
                      total_epochs=0):

    dataset = __all__[dataset_cfg.DATASET](
        dataset_cfg=dataset_cfg,
        class_names=class_names,
        root_path=root_path,
        training=training,
        logger=logger,
    )

    if merge_all_iters_to_one_epoch:
        assert hasattr(dataset, 'merge_all_iters_to_one_epoch')
        dataset.merge_all_iters_to_one_epoch(merge=True, epochs=total_epochs)

    dataloader = DataLoader(dataset,
                            batch_size=batch_size,
                            pin_memory=True,
                            num_workers=workers,
                            shuffle=False,
                            collate_fn=dataset.collate_batch,
                            drop_last=False,
                            sampler=None,
                            timeout=0,
                            worker_init_fn=partial(common_utils.worker_init_fn,
                                                   seed=seed))

    return dataloader
