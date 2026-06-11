import os
from pathlib import Path

os.environ['PROJECT_DIR'] = Path(os.path.dirname(__file__) +
                                 '/../../').resolve().as_posix()

import copy
import numpy as np
from tqdm import tqdm

from torch.utils.data import DataLoader

from shapely import concave_hull
from shapely.geometry import MultiPoint

from pcdet.datasets.kitti.kitti_dataset import KittiDataset as _KittiDataset
from pcdet.utils import box_utils, common_utils

from mtest.core.pose_estimulation.road_split import load_road_split_labels, split_pc

from utils.coverage_utils import get_scene_graph_type, kitti_class


class KittiDataset(_KittiDataset):

    def __getitem__(self, index):
        if self._merge_all_iters_to_one_epoch:
            index = index % len(self.kitti_infos)

        info = copy.deepcopy(self.kitti_infos[index])

        sample_idx = info['point_cloud']['lidar_idx']
        img_shape = info['image']['image_shape']
        calib = self.get_calib(sample_idx)
        get_item_list = self.dataset_cfg.get('GET_ITEM_LIST', ['points'])

        input_dict = {
            'frame_id': sample_idx,
            'calib': calib,
        }

        if 'annos' in info:
            annos = info['annos']
            annos = common_utils.drop_info_with_name(annos, name='DontCare')
            loc, dims, rots = annos['location'], annos['dimensions'], annos[
                'rotation_y']
            gt_names = annos['name']
            gt_boxes_camera = np.concatenate(
                [loc, dims, rots[..., np.newaxis]], axis=1).astype(np.float32)
            gt_boxes_lidar = box_utils.boxes3d_kitti_camera_to_lidar(
                gt_boxes_camera, calib)

            input_dict.update({
                'gt_names': gt_names,
                'gt_boxes': gt_boxes_lidar
            })

        if "points" in get_item_list:
            if 'points' in info:
                input_dict['points'] = info['points']
            else:
                points = self.get_lidar(sample_idx)
                if self.dataset_cfg.FOV_POINTS_ONLY:
                    pts_rect = calib.lidar_to_rect(points[:, 0:3])
                    fov_flag = self.get_fov_flag(pts_rect, img_shape, calib)
                    points = points[fov_flag]
                input_dict['points'] = points

        input_dict['calib'] = calib
        data_dict = self.prepare_data(data_dict=input_dict)

        data_dict['image_shape'] = img_shape
        return data_dict


def modify_kitti_infos(loader: DataLoader):

    infos_mask = np.ones(len(loader.dataset.kitti_infos), dtype=np.bool8)

    for index in tqdm(range(len(loader.dataset.kitti_infos))):
        info = loader.dataset.kitti_infos[index]

        sample_idx = info['point_cloud']['lidar_idx']
        img_shape = info['image']['image_shape']
        calib = loader.dataset.get_calib(sample_idx)
        point_cloud_range = loader.dataset.point_cloud_range

        # Point cloud and road labels
        points = loader.dataset.get_lidar(sample_idx)
        road_labels = load_road_split_labels(
            f'data/kitti/training/road_label/{sample_idx}.label')

        ######## Filter
        selected = common_utils.mask_points_by_range(points, point_cloud_range)

        points = points[selected]
        road_labels = road_labels[selected]

        if loader.dataset.dataset_cfg.FOV_POINTS_ONLY:
            pts_rect = calib.lidar_to_rect(points[:, 0:3])
            fov_flag = loader.dataset.get_fov_flag(pts_rect, img_shape, calib)

            points = points[fov_flag]
            road_labels = road_labels[fov_flag]

        inx_road_arr, inx_other_road_arr, inx_other_ground_arr, inx_no_road_arr = split_pc(
            road_labels)

        non_road_pc = points[inx_other_road_arr + inx_other_ground_arr +
                             inx_no_road_arr][:, :3]

        if points.shape[0] == 0:
            print(f'pop {index} -- low point cloud')
            infos_mask[index] = False
            continue

        # Insert method
        road_pc = np.fromfile(
            f'data/kitti/training/road_label/{sample_idx}.bin',
            dtype=np.float32).reshape(-1, 3)

        ######## Filter
        selected = common_utils.mask_points_by_range(road_pc,
                                                     point_cloud_range)

        road_pc = road_pc[selected]

        if road_pc.shape[0] < 10:
            print(f'pop {index} -- low insert point cloud')
            infos_mask[index] = False
            continue

        # Ground truth boxes
        if 'annos' not in info:
            raise NotImplementedError

        annos = info['annos']
        annos = common_utils.drop_info_with_name(annos, name='DontCare')
        loc, dims, rots = annos['location'], annos['dimensions'], annos[
            'rotation_y']
        gt_names = annos['name']
        gt_boxes_camera = np.concatenate([loc, dims, rots[..., np.newaxis]],
                                         axis=1).astype(np.float32)
        gt_boxes_lidar = box_utils.boxes3d_kitti_camera_to_lidar(
            gt_boxes_camera, calib)

        ######## Filter ground truth boxes
        # 1. Selected classes
        selected = common_utils.keep_arrays_by_name(gt_names, kitti_class)

        gt_names = gt_names[selected]
        gt_boxes_lidar = gt_boxes_lidar[selected]

        # 2. Filter boxes outside range
        selected = box_utils.mask_boxes_outside_range_numpy(
            gt_boxes_lidar, point_cloud_range)

        gt_names = gt_names[selected]
        gt_boxes_lidar = gt_boxes_lidar[selected]
        ######## Filter end

        if len(gt_boxes_lidar) == 0 or (gt_names == 'Car').sum() < 3:
            print(f'pop {index} -- low ground truth boxes')
            infos_mask[index] = False
            continue

        # Point cloud mask
        gt_corners = box_utils.boxes_to_corners_3d(gt_boxes_lidar)
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
        s_rl_pts = points[s_rl][:, :2]

        road_hull = concave_hull(MultiPoint(s_rl_pts), 0.3)

        if road_hull.area < 10:
            print(f'pop {index} -- low road hull')
            infos_mask[index] = False
            continue

        info['selected_name'] = gt_names
        info['selected_gt_boxes'] = gt_boxes_lidar

        # Delete GT
        info.pop('annos')

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
        info['mtest_calib'] = calib

    loader.dataset.kitti_infos = loader.dataset.kitti_infos[infos_mask]
