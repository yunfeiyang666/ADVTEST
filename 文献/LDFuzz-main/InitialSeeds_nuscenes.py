import os
import copy
import pickle

import numpy as np
from tqdm import tqdm
from easydict import EasyDict as Dict

from torch import no_grad
from torch.cuda import empty_cache

from pcdet.ops.iou3d_nms.iou3d_nms_utils import boxes_iou_bev

from utils import config
from utils import model_utils
from utils.config import get_seed_path
from utils.nuscenes import modify_nuscenes_infos

from _others.fid.lidargen_fid import get_fid
from _lib.func import lidar_mutation_functionV1, build_frd_function

iou_threshold = 0.7
eps = np.finfo(np.float32).eps
mutation_function = lidar_mutation_functionV1(no_seed=True)
frd_function = build_frd_function(model_utils.load_frd_model())


def select_infos(model, loader, batch_size):
    mask = np.zeros(len(loader.dataset.infos), dtype=np.bool8)
    cnt = 0

    empty_cache()
    with no_grad():
        for index, data_batch in enumerate(tqdm(loader)):
            model_utils.load_data_to_gpu(data_batch)
            layer_outputs, _ = model(data_batch)

            for n in range(len(layer_outputs)):
                gt_boxes = data_batch['gt_boxes'][n]
                pred_scores = layer_outputs[n]['pred_scores']
                pred_boxes = layer_outputs[n]['pred_boxes']

                pred_boxes = pred_boxes[pred_scores > 0.3]

                iou = boxes_iou_bev(gt_boxes[:, :7],
                                    pred_boxes[:, :7]).detach().cpu().numpy()

                if iou.shape[1] != 0:
                    iou = iou.max(axis=1).reshape(-1)
                else:
                    iou = np.zeros(len(gt_boxes), dtype=np.float32)

                tp = (iou >= iou_threshold).sum()
                fp = len(pred_boxes) - tp
                fn = len(gt_boxes) - tp

                p = tp / (tp + fp + eps)
                r = tp / (tp + fn + eps)

                if p * r > 0.5:
                    mask[index * batch_size + n] = True
                    cnt += 1
                    print(f'ok {index}, count {cnt}')

            if cnt >= 100:
                break

    loader.dataset.infos = loader.dataset.infos[mask]


def max_frd(batch) -> float:
    l = []
    for _i in range(3):
        test = copy.deepcopy(batch)

        for _j in range(10):
            test = mutation_function(test, config.object_level)[0]

        x = frd_function(batch['points'])
        y = frd_function(test['points'])

        frd = get_fid(x, y)
        l.append(frd)

    return np.max(l)


def createBatch(x_batch, output_path, prefix):
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    batch_num = len(x_batch)
    batches = np.split(x_batch, batch_num, axis=0)
    for i, batch in enumerate(batches):
        # test = np.append(batch, batch, axis=0)
        batch[0]['frd_limit'] = max_frd(batch[0])
        saved_name = f'{prefix}{i:03d}.pickle'
        # np.save(os.path.join(output_path, saved_name), batch)
        with open(os.path.join(output_path, saved_name), 'wb') as f:
            pickle.dump(batch.tolist(), f)


if __name__ == '__main__':

    args = Dict(dataset_model=Dict(nuscenes=['second']))

    for dataset_name, model_name_arr in args.dataset_model.items():
        for model_name in model_name_arr:
            print(dataset_name, model_name)

            num = 50
            batch_size = 4

            model, loader = model_utils.load_model(dataset_name, model_name,
                                                   batch_size)

            loader.dataset.infos = np.random.permutation(loader.dataset.infos)

            select_infos(model, loader, batch_size)

            output_path = get_seed_path(dataset_name, model_name)

            if not os.path.exists(output_path):
                os.makedirs(output_path)

            modify_nuscenes_infos(loader)

            infos_len = len(loader.dataset.infos)
            if infos_len >= num:
                selected = np.random.choice(infos_len, num, replace=False)
            else:
                selected = []
                while num - infos_len > 0:
                    selected.append(np.arange(infos_len, dtype=np.uint32))
                    num -= infos_len
                    if num - infos_len <= 0:
                        break
                selected.append(np.random.choice(infos_len, num,
                                                 replace=False))

                selected = np.concatenate(selected)

            createBatch(loader.dataset.infos[selected], output_path, 'init')
            print('finish')
