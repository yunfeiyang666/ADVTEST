import os
import shutil
import argparse

os.environ['PROJECT_DIR'] = os.path.dirname(__file__)

import copy
from torch.utils.data import DataLoader
from utils import config
from utils.KITTI_LoadModel import load_model, modify_kitti_infos
import numpy as np

from _others.velodyne_mutators import METHOD
from _lib.func import build_fetch_function, get_gt_polygon

from pcdet.datasets.kitti.kitti_object_eval_python import eval as kitti_eval
from pcdet.datasets.kitti.kitti_dataset import KittiDataset

import pickle
import torch

eps = np.finfo(np.float32).eps
rq1_root_path = './__rq1_out'
seeds_path = f'{rq1_root_path}/seeds'
DUMPS = {'scene': {}}

ALL_METHOD = ['none'] + config.scene_level + config.object_level

METHOD_RATE = {
    'none': None,
    'translocate': None,
    'rotation': 80,
    'scale': -0.2,
    'insert': None,
    'rain': None,
    'snow': None,
    'fog': 20
}


def createBatch(x_batch, output_path, prefix):
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    batch_num = len(x_batch)
    batches = np.split(x_batch, batch_num, axis=0)
    for i, batch in enumerate(batches):
        # test = np.append(batch, batch, axis=0)
        saved_name = f'{prefix}{i:03d}.pickle'
        # np.save(os.path.join(output_path, saved_name), batch)
        with open(os.path.join(output_path, saved_name), 'wb') as f:
            pickle.dump(batch.tolist(), f)


def create_seeds(loader: DataLoader):
    # loader.dataset.sample_id_list = np.random.choice(
    #     loader.dataset.sample_id_list, try_num, False).tolist()
    loader.dataset.kitti_infos = loader.dataset.get_infos()

    # modify kitti_infos
    modify_kitti_infos(loader)
    # ----------------------------------------

    loader.dataset.kitti_infos = np.array(loader.dataset.kitti_infos)
    # selected = np.random.choice(len(loader.dataset.kitti_infos),
    #                             num,
    #                             replace=False)

    createBatch(loader.dataset.kitti_infos, seeds_path, 'seed')


def load_data_to_shared_memory(batch):
    for _k in batch:
        try:
            batch[_k] = torch.from_numpy(batch[_k])
        except:
            None


def get_pred_dicts(pred_scores, pred_boxes, pred_labels):
    pred_car_mask = (pred_labels[0] == 1)
    pred_dicts = {}
    pred_dicts['name'] = np.array(['Car'] * np.sum(pred_car_mask))
    pred_dicts['pred_scores'] = torch.from_numpy(pred_scores[0][pred_car_mask])
    pred_dicts['pred_boxes'] = torch.from_numpy(pred_boxes[0][pred_car_mask])
    pred_dicts['pred_labels'] = torch.from_numpy(pred_labels[0][pred_car_mask])

    return [pred_dicts]


if __name__ == '__main__':
    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-m',
        nargs='+',
        help='model list, split by blankspace, e.g. pointpillar pv_rcnn',
        required=True)

    parser.add_argument(
        '--only-seeds',
        action='store_true',
        help='if this arg set, it will only generate test seeds')
    args = parser.parse_args()

    data_name = 'kitti'
    model_list = args.m

    if not os.path.exists(rq1_root_path):
        os.makedirs(rq1_root_path)

    for model_name in model_list:
        model, loader = load_model(model_name, 1)

        if not os.path.exists(seeds_path):
            os.makedirs(seeds_path)
            create_seeds(loader)

        if args.only_seeds:
            continue

        data_path = f'{rq1_root_path}/{data_name}_{model_name}'
        if os.path.exists(data_path):
            shutil.rmtree(data_path)
        os.makedirs(data_path)

        fetch_function = build_fetch_function(model, loader, True)

        mean_ap = {
            **{
                i: 0
                for i in config.object_level + config.scene_level
            }, 'none': 0
        }

        seeds_list = os.listdir(seeds_path)
        for method in ALL_METHOD:
            gt_annos = []
            dt_annos = []
            for seed in seeds_list:
                with open(f'{seeds_path}/{seed}', 'rb') as f:
                    batch = pickle.load(f)

                scene = batch[0]['point_cloud']['lidar_idx']
                batch[0]['scene'] = scene
                batch[0]['criteria'] = config.none

                if scene not in DUMPS['scene']:
                    DUMPS['scene'][scene] = {}
                DUMPS['scene'][scene]['gt_polygon'] = get_gt_polygon(
                    batch[0]['selected_gt_boxes'])

                if method is not config.none:
                    try:
                        batch = METHOD[method](copy.deepcopy(batch)[0],
                                               METHOD_RATE[method], DUMPS)
                    except Exception as e:
                        print(f'Error -- {method} , {e}')

                    if not os.path.exists(f'{data_path}/{method}'):
                        os.makedirs(f'{data_path}/{method}')
                    with open(f'{data_path}/{method}/{seed}.pickle',
                              'wb') as f:
                        pickle.dump(batch, f)

                gt_annos.append(batch[0]['annos'])

                pred_scores, pred_boxes, pred_labels = fetch_function(batch)

                loader.dataset.kitti_infos = batch
                batch = list(loader)[0]
                load_data_to_shared_memory(batch)

                dt_annos += KittiDataset.generate_prediction_dicts(
                    batch, get_pred_dicts(pred_scores, pred_boxes,
                                          pred_labels),
                    ['Car', 'Pedestrian', 'Cyclist'])

            res = kitti_eval.get_official_eval_result(gt_annos, dt_annos,
                                                      ['Car'])

            mean_ap[method] = res[1]['Car_bev/hard_R40']

        with open(f'{rq1_root_path}/{data_name}_{model_name}.pickle',
                  'wb') as f:
            pickle.dump(mean_ap, f)
        print(f'{data_name}_{model_name} : {mean_ap}')

    exit(0)
