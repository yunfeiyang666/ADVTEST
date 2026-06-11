import os
from pathlib import Path

os.environ['PROJECT_DIR'] = Path(os.path.dirname(__file__) +
                                 '/../../').resolve().as_posix()

import copy
import numpy as np
from tqdm import tqdm
from pathlib import Path

from torch.utils.data import DataLoader

from shapely import concave_hull
from shapely.geometry import MultiPoint

from pcdet.datasets.nuscenes.nuscenes_dataset import NuScenesDataset as _NuScenesDataset
from pcdet.utils import box_utils, common_utils
from pcdet.utils.calibration_kitti import Calibration

from mtest.core.pose_estimulation.road_split import load_road_split_labels, split_pc

from utils.coverage_utils import get_scene_graph_type, nuscenes_class


class NuScenesDataset(_NuScenesDataset):

    def __getitem__(self, index):
        if self._merge_all_iters_to_one_epoch:
            index = index % len(self.infos)

        info = copy.deepcopy(self.infos[index])
        if 'points' in info:
            points = copy.deepcopy(info['points'])
            points = np.hstack((points, np.zeros((points.shape[0], 1))))
        else:
            points = self.get_lidar_with_sweeps(
                index, max_sweeps=self.dataset_cfg.MAX_SWEEPS)

        input_dict = {
            'points': points,
            'frame_id': Path(info['lidar_path']).stem,
            'metadata': {
                'token': info['token']
            }
        }

        if 'gt_boxes' in info:
            if self.dataset_cfg.get('FILTER_MIN_POINTS_IN_GT', False):
                mask = (info['num_lidar_pts']
                        > self.dataset_cfg.FILTER_MIN_POINTS_IN_GT - 1)
            else:
                mask = None

            input_dict.update({
                'gt_names':
                info['gt_names'] if mask is None else info['gt_names'][mask],
                'gt_boxes':
                info['gt_boxes'] if mask is None else info['gt_boxes'][mask]
            })
        if self.use_camera:
            input_dict = self.load_camera_info(input_dict, info)

        data_dict = self.prepare_data(data_dict=input_dict)

        if self.dataset_cfg.get('SET_NAN_VELOCITY_TO_ZEROS',
                                False) and 'gt_boxes' in info:
            gt_boxes = data_dict['gt_boxes']
            gt_boxes[np.isnan(gt_boxes)] = 0
            data_dict['gt_boxes'] = gt_boxes

        if not self.dataset_cfg.PRED_VELOCITY and 'gt_boxes' in data_dict:
            data_dict['gt_boxes'] = data_dict[
                'gt_boxes'][:, [0, 1, 2, 3, 4, 5, 6, -1]]

        return data_dict


def modify_nuscenes_infos(loader: DataLoader):

    point_cloud_range = [-51.2, 0, -5.0, 51.2, 51.2, 3.0]
    dataset_cfg = loader.dataset.dataset_cfg
    dataset_version = dataset_cfg.VERSION

    infos_mask = np.ones(len(loader.dataset.infos), dtype=np.bool8)

    for index in range(len(loader.dataset.infos)):
        info = loader.dataset.infos[index]
        token = info['token']

        # Point cloud
        points = loader.dataset.get_lidar_with_sweeps(
            index, max_sweeps=dataset_cfg.MAX_SWEEPS)
        points = points[:, :4]

        if points.shape[0] == 0:
            print(f'pop {index} -- low point cloud')
            infos_mask[index] = False
            continue

        # Insert method : road point cloud
        road_pc = np.fromfile(
            f'data/nuscenes/{dataset_version}/road_label/{token}.bin',
            dtype=np.float32).reshape(-1, 3)

        ######## Filter
        selected = common_utils.mask_points_by_range(road_pc,
                                                     point_cloud_range)

        road_pc = road_pc[selected]

        if road_pc.shape[0] < 10:
            print(f'pop {index} -- low insert point cloud')
            infos_mask[index] = False
            continue

        # Insert method : point cloud without sweep
        points_without_sweep = loader.dataset.get_lidar_with_sweeps(index)

        ######## Filter
        selected = common_utils.mask_points_by_range(points_without_sweep,
                                                     point_cloud_range)

        points_without_sweep = points_without_sweep[selected]

        road_labels = load_road_split_labels(
            f'data/nuscenes/{dataset_version}/road_label/{token}.label')

        road_labels = road_labels[selected]

        inx_road_arr, inx_other_road_arr, inx_other_ground_arr, inx_no_road_arr = split_pc(
            road_labels)

        non_road_pc = points_without_sweep[inx_other_road_arr +
                                           inx_other_ground_arr +
                                           inx_no_road_arr][:, :3]

        if 'gt_names' not in info:
            print(f'pop {index} -- already selected')
            infos_mask[index] = False
            continue

        ######## Filter ground truth boxes
        # 1. Selected classes
        selected = common_utils.keep_arrays_by_name(info['gt_names'],
                                                    nuscenes_class)

        info['gt_names'] = info['gt_names'][selected]
        info['gt_boxes'] = info['gt_boxes'][selected][:, :7]
        info['num_lidar_pts'] = info['num_lidar_pts'][selected]

        # 2. Filter min points in ground truth
        selected = (info['num_lidar_pts'] >= 5)

        info['gt_names'] = info['gt_names'][selected]
        info['gt_boxes'] = info['gt_boxes'][selected]
        info['num_lidar_pts'] = info['num_lidar_pts'][selected]

        # 3. Filter boxes outside range
        selected = box_utils.mask_boxes_outside_range_numpy(
            info['gt_boxes'], point_cloud_range)

        info['gt_names'] = info['gt_names'][selected]
        info['gt_boxes'] = info['gt_boxes'][selected]
        info['num_lidar_pts'] = info['num_lidar_pts'][selected]
        ######## Filter end

        if len(info['gt_boxes']) == 0 or (info['gt_names'] == 'car').sum() < 3:
            print(f'pop {index} -- low ground truth boxes')
            infos_mask[index] = False
            continue

        # Point cloud mask
        gt_corners = box_utils.boxes_to_corners_3d(info['gt_boxes'])
        pc_mask = np.zeros((1, points.shape[0]), dtype=np.bool8)
        for corner in gt_corners:
            pc_mask = np.vstack(
                (pc_mask, box_utils.in_hull(
                    points[:, :3],
                    corner,
                )))
        pc_mask = pc_mask[1:]

        assert pc_mask.shape[0] == gt_corners.shape[0]

        # Scene graph
        s_rl = road_labels.reshape(-1)
        # 40: road
        # 44: parking
        # 48: sidewalk
        s_rl = (s_rl == 44) + (s_rl == 40)
        s_rl_pts = points_without_sweep[s_rl][:, :2]

        road_hull = concave_hull(MultiPoint(s_rl_pts), 0.3)

        if road_hull.area < 10:
            print(f'pop {index} -- low road hull')
            infos_mask[index] = False
            continue

        info['selected_name'] = info['gt_names']
        info['selected_gt_boxes'] = info['gt_boxes']

        # Delete GT
        info.pop('gt_boxes')
        info.pop('gt_boxes_velocity')
        info.pop('gt_names')
        info.pop('gt_boxes_token')
        info.pop('num_lidar_pts')
        info.pop('num_radar_pts')

        info['selected_pc_mask'] = pc_mask
        info['points'] = points
        info['is_fn'] = np.array([False] * gt_corners.shape[0])
        info['is_fn2'] = np.array([False] * gt_corners.shape[0])
        info['weather_type'] = 'sunny'
        info['road_hull'] = road_hull
        info['scene_graph_type'] = get_scene_graph_type(road_hull)
        info['road_pc'] = road_pc
        info['road_labels'] = road_labels
        info['non_road_pc'] = non_road_pc
        info['mtest_calib'] = Calibration({
            'P2':
            np.zeros((3, 4), dtype=np.float32),
            'P3':
            np.zeros((3, 4), dtype=np.float32),
            'R0':
            np.eye(3, 3, dtype=np.float32),
            'Tr_velo2cam':
            np.eye(3, 4, dtype=np.float32),
        })

    loader.dataset.infos = loader.dataset.infos[infos_mask]
