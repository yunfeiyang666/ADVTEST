import yaml
from easydict import EasyDict as Dict

import torch
from torch import from_numpy

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.set_float32_matmul_precision("high")

from pcdet.models import build_network
from pcdet.config import cfg, merge_new_config
from pcdet.utils import common_utils

from _others.lidar_bonnetal.modules.user import User

from .dataloader import create_dataloader
from .config import kitti, nuscenes


def load_data_to_gpu(batch_dict):
    keys = ['points', 'voxels', 'voxel_num_points', 'voxel_coords', 'gt_boxes']
    for k, v in batch_dict.items():
        if k in keys:
            batch_dict[k] = from_numpy(v).type(torch.float32).cuda()


def load_model(dataset_type: str, model_type: str, batch_size=1, loader=None):

    model_cfg = merge_new_config(
        cfg,
        Dict(
            yaml.safe_load(
                open(f'__profile/{dataset_type}/cfg/{model_type}.yaml'))),
    )

    if loader is None:
        loader = create_dataloader(model_cfg.DATA_CONFIG, batch_size, False)

    model = build_network(model_cfg=model_cfg.MODEL,
                          num_class=len(model_cfg.CLASS_NAMES),
                          dataset=loader.dataset)

    model.cuda()
    model.eval()

    model.load_params_from_file(
        f'__profile/{dataset_type}/models/{model_type}.pth',
        common_utils.create_logger(f'{dataset_type}_{model_type}_log.log'))

    return model, loader


def load_frd_model(dataset_name):
    ARCH = yaml.safe_load(
        open('_others/lidar_bonnetal/model/arch_cfg.yaml', 'r'))
    DATA = yaml.safe_load(
        open('_others/lidar_bonnetal/model/data_cfg.yaml', 'r'))

    if dataset_name == kitti:
        ARCH['dataset']['max_points'] = 150000
    elif dataset_name == nuscenes:
        ARCH['dataset']['max_points'] = 300000

    return User(ARCH, DATA, '_others/lidar_bonnetal/model')
