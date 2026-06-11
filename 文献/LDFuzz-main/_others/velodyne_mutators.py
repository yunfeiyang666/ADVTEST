import os
import copy
import numpy as np
from pathlib import Path

from pylisa.lisa import Lisa

from pygem import FFD

from utils import config
from .fog_simulation import ParameterSet, simulate_fog

from pcdet.utils import box_utils
from pcdet.utils.object3d_kitti import Object3d as _Object3d

from shapely import convex_hull, union, box
from shapely.geometry import Point, MultiPoint, Polygon

from mtest.utils.Utils_o3d import load_normalized_mesh_obj
from mtest.utils.Utils_common import get_geometric_info, get_initial_box3d_in_bg, change_3dbox, get_labels
from mtest.core.pose_estimulation.collision_detection import collision_detection, is_on_road
from mtest.core.pose_estimulation.pose_generator import generate_pose, tranform_mesh_by_pose, get_valid_pints
from mtest.core.sensor_simulation.lidar_simulator import lidar_simulation, complet_pc
from mtest.core.occusion_handing.combine_pc import combine_pcd


def cls_type_to_id(cls_type):
    type_to_id = {'Car': 1, 'Pedestrian': 2, 'Cyclist': 3, 'Van': 4}
    if cls_type not in type_to_id.keys():
        return -1
    return type_to_id[cls_type]


class Object3d(_Object3d):

    def __init__(self, label):
        self.cls_type = label[0]
        self.cls_id = cls_type_to_id(self.cls_type)
        self.truncation = float(label[1])
        self.occlusion = float(
            label[2]
        )  # 0:fully visible 1:partly occluded 2:largely occluded 3:unknown
        self.alpha = float(label[3])
        self.box2d = np.array((float(label[4]), float(label[5]), float(
            label[6]), float(label[7])),
                              dtype=np.float32)
        self.h = float(label[8])
        self.w = float(label[9])
        self.l = float(label[10])
        self.loc = np.array(
            (float(label[11]), float(label[12]), float(label[13])),
            dtype=np.float32)
        self.dis_to_cam = np.linalg.norm(self.loc)
        self.ry = float(label[14])
        self.score = float(label[15]) if label.__len__() == 16 else -1.0
        self.level_str = None
        self.level = self.get_kitti_obj_level()


def core_distortion(points, n_control_points=[2, 2, 2], displacement=None):
    """
        Ref: http://mathlab.github.io/PyGeM/tutorial-1-ffd.html
    """
    # the size of displacement matrix: 3 * control_points.shape
    if displacement is None:
        displacement = np.zeros((3, *n_control_points))

    ffd = FFD(n_control_points=n_control_points)
    ffd.box_length = [2., 2., 2.]
    ffd.box_origin = [-1., -1., -1.]
    ffd.array_mu_x = displacement[0, :, :, :]
    ffd.array_mu_y = displacement[1, :, :, :]
    ffd.array_mu_z = displacement[2, :, :, :]
    new_points = ffd(points)

    return new_points


def distortion(points,
               direction_mask=np.array([1, 1, 1]),
               point_mask=np.ones((5, 5, 5)),
               severity=0.5):

    n_control_points = [5, 5, 5]
    # random
    displacement = np.random.rand(3, *
                                  n_control_points) * 2 * severity - np.ones(
                                      (3, *n_control_points)) * severity
    displacement *= np.transpose(np.tile(direction_mask, (5, 5, 5, 1)),
                                 (3, 0, 1, 2))
    displacement *= np.tile(point_mask, (3, 1, 1, 1))

    points = core_distortion(points,
                             n_control_points=n_control_points,
                             displacement=displacement)

    # points = denomalize(points, scale, offset)
    # set_points(data, points)
    return points


def normalize(points):
    """
    Args:
        points: N x 3+C 
    Returns:
        limit points to max-2 unit square box: N x 3+C
    """
    if points.shape[0] != 0:
        indicator = np.max(np.abs(points[:, :3]))
        if indicator > 1:
            points[:, :3] = points[:, :3] / indicator
    return points


def rotate_pts_along_z(points, angle):
    """
    Args:
        points: (N x 3 + C) narray
        angle: angle along z-axis, angle increases x ==> y
    Returns:

    """
    cosa = np.cos(angle)
    sina = np.sin(angle)
    rot_matrix = np.array([cosa, sina, 0.0, -sina, cosa, 0.0, 0.0, 0.0,
                           1.0]).reshape(3, 3)
    points_rot = np.matmul(points[:, 0:3], rot_matrix)
    points_rot = np.hstack((points_rot, points[:, 3:].reshape(-1, 1)))

    return points_rot


def Lidar_to_Max2(points, gt_boxes_lidar):
    """
    Args:
        points: N x 3+C
        gt_boxes_lidar: 7 
    Returns:
        points normalized to max-2 unit square box: N x 3+C
    """
    # shift
    points[:, :3] = points[:, :3] - gt_boxes_lidar[:3]
    # normalize to 2 units
    points[:, :3] = points[:, :3] / np.max(gt_boxes_lidar[3:6]) * 2
    # reversely rotate
    points = rotate_pts_along_z(points, -gt_boxes_lidar[6])

    return points.astype(np.float32)


def Max2_to_Lidar(points, gt_boxes_lidar):
    """
    Args:
        points: N x 3+C
        gt_boxes_lidar: 7 
    Returns:
        points denormalized to lidar coordinates
    """

    # rotate
    points = rotate_pts_along_z(points, gt_boxes_lidar[6])
    # denormalize to lidar
    points[:, :3] = points[:, :3] * np.max(gt_boxes_lidar[3:6]) / 2
    # shift
    points[:, :3] = points[:, :3] + gt_boxes_lidar[:3]

    return points.astype(np.float32)


class Mutator():

    def __init__(self, dataset_name, criteria=None):
        self.dataset_name = dataset_name
        self.criteria = criteria

    def generate_method_list(self):
        method_list = {}

        for method in config.scene_level:
            method_list[method] = getattr(self, method)

        for method in config.object_level:
            method_list[method] = getattr(self, method)

        return method_list

    def generate_area_list(self, hull):
        area_list = []

        for length in config.scene_graph_length_list:
            for width in config.scene_graph_width_list:

                if self.dataset_name == config.kitti:
                    area_list.append(
                        hull.intersection(
                            box(length[0], width[0], length[1], width[1])))

                elif self.dataset_name == config.nuscenes:
                    area_list.append(
                        hull.intersection(
                            box(width[0], length[0], width[1], length[1])))

                if area_list[-1].is_empty:
                    area_list.pop()

        return area_list

    def generate_location_cheaply(self, hull, polygon):

        area_list = []
        if self.criteria in [
                config.spc, config.error_spc, config.sec, config.error_sec
        ]:
            area_list = self.generate_area_list(hull)
        elif self.criteria in [config.ldfuzz, config.error_mixed]:
            hull = hull.difference(polygon)
            area_list = self.generate_area_list(hull)
        elif self.criteria == config.none:
            area_list.append(hull)

        if len(area_list):
            selected_area = np.random.choice(area_list)
            return np.array(selected_area.point_on_surface().xy).reshape(-1)

        return None

    def rain(self, ret, rate=None, DUMPS=None):
        c = np.random.uniform(0.1, 10) if rate is None else rate

        if self.dataset_name == config.nuscenes:
            # normalization : 0-255 --> 0-1
            ret['points'][:, 3] /= 255

        ret['points'] = Lisa(atm_model='rain').augment(
            ret['points'], c)[:, :-1].astype(dtype=np.float32)

        if self.dataset_name == config.nuscenes:
            # 0-1 --> 0-255
            ret['points'][:, 3] *= 255

        ret['points'] = ret['points'][np.where(
            np.sum(ret['points'] != [0.0, 0.0, 0.0, 0.0], axis=1))]

        corners_lidar = box_utils.boxes_to_corners_3d(ret['selected_gt_boxes'])
        selected_mask = None
        for k in range(corners_lidar.shape[0]):
            selected_mask = \
                np.append(
                    selected_mask,
                    box_utils.in_hull(
                        ret['points'][:, 0:3],
                        corners_lidar[k]
                    ).reshape(1, -1),
                    axis=0
                ) if selected_mask is not None else\
                box_utils.in_hull(
                    ret['points'][:, 0:3],
                    corners_lidar[k]
                ).reshape(1, -1)

        ret['selected_pc_mask'] = selected_mask
        ret['weather_type'] = 'rain'

        return [ret]

    def snow(self, ret, rate=None, DUMPS=None):
        c = np.random.uniform(0.1, 2.4) if rate is None else rate

        if self.dataset_name == config.nuscenes:
            # normalization : 0-255 --> 0-1
            ret['points'][:, 3] /= 255

        ret['points'] = Lisa(atm_model='snow').augment(
            ret['points'], c)[:, :-1].astype(dtype=np.float32)

        if self.dataset_name == config.nuscenes:
            # 0-1 --> 0-255
            ret['points'][:, 3] *= 255

        ret['points'] = ret['points'][np.where(
            np.sum(ret['points'] != [0.0, 0.0, 0.0, 0.0], axis=1))]

        corners_lidar = box_utils.boxes_to_corners_3d(ret['selected_gt_boxes'])
        selected_mask = None
        for k in range(corners_lidar.shape[0]):
            selected_mask = \
                np.append(
                    selected_mask,
                    box_utils.in_hull(
                        ret['points'][:, 0:3],
                        corners_lidar[k]
                    ).reshape(1, -1),
                    axis=0
                ) if selected_mask is not None else\
                box_utils.in_hull(
                    ret['points'][:, 0:3],
                    corners_lidar[k]
                ).reshape(1, -1)

        ret['selected_pc_mask'] = selected_mask
        ret['weather_type'] = 'snow'

        return [ret]

    def fog(self, ret, rate=None, DUMPS=None):
        c = np.random.uniform(200, 1000) if rate is None else rate
        c = 2.996 / c

        points = ret['points']

        if self.dataset_name == config.kitti:
            # 0-1 --> 0-255
            points[:, 3] *= 255

        points, _, _ = simulate_fog(ParameterSet(alpha=c), points, noise=0)

        if self.dataset_name == config.kitti:
            # 0-255 --> 0-1
            points[:, 3] /= 255

        ret['points'] = points.astype(np.float32)
        ret['weather_type'] = 'fog'

        return [ret]

    def translocate(self, ret, rate=None, DUMPS=None):
        s = np.random.choice(ret['selected_pc_mask'].shape[0])

        diff = Polygon()
        for __i__ in range(ret['selected_gt_boxes'].shape[0]):
            if __i__ == s: continue
            cor = box_utils.boxes_to_corners_3d(
                np.array([ret['selected_gt_boxes'][__i__]]))[0, :4, :2]
            diff = union(diff, convex_hull(MultiPoint(cor)))

        hull = ret['road_hull'].difference(diff)

        xmax, xmin = np.max(hull.convex_hull.exterior.xy[0]), np.min(
            hull.convex_hull.exterior.xy[0])
        ymax, ymin = np.max(hull.convex_hull.exterior.xy[1]), np.min(
            hull.convex_hull.exterior.xy[1])

        box = copy.deepcopy(ret['selected_gt_boxes'][s])
        ref_center = copy.deepcopy(box[0:2])

        if DUMPS is not None:
            center = self.generate_location_cheaply(
                hull, DUMPS['scene'][ret['scene']]['gt_polygon'])
        else:
            center = None

        try_num = 30
        while try_num:
            if center is None:
                center = np.array([
                    np.random.uniform(xmin, xmax),
                    np.random.uniform(ymin, ymax)
                ])

            if hull.disjoint(Point(center)):
                center = None
                try_num -= 1
                continue

            box[0:2] = center

            cor = box_utils.boxes_to_corners_3d(np.array([box]))[0, :4, :2]
            poly = convex_hull(MultiPoint(cor))

            if diff.intersects(poly):
                center = None
                try_num -= 1
                continue

            points = ret['points'][ret['selected_pc_mask'][s]]
            points[:, 0:2] += center - ref_center
            ret['points'][ret['selected_pc_mask'][s]] = points

            ret['selected_gt_boxes'][s] = box
            ret['is_fn'][s] = False
            ret['is_fn2'][s] = False
            break

        if try_num <= 0:
            raise ValueError(f'Expected try_num > 0, found {try_num}.')

        return [ret]

    def rotation(self, ret, rate=None, DUMPS=None):
        hull = ret['road_hull']

        try_num = 30
        while try_num:
            s = np.random.choice(ret['selected_pc_mask'].shape[0])
            center = ret['selected_gt_boxes'][s, :2]

            if hull.disjoint(Point(center)):
                try_num -= 1
                continue

            c = np.random.uniform(5, 30) if rate is None else rate

            points = ret['points'][ret['selected_pc_mask'][s]]

            points = Lidar_to_Max2(points, ret['selected_gt_boxes'][s])

            beta = np.random.uniform(c - 1, c + 1) * np.random.choice(
                [-1, 1]) * np.pi / 180.
            matrix_roration_z = np.array([[np.cos(beta),
                                           np.sin(beta), 0],
                                          [-np.sin(beta),
                                           np.cos(beta), 0], [0, 0, 1]])

            points[:, :3] = np.matmul(points[:, :3], matrix_roration_z)

            ret['points'][ret['selected_pc_mask'][s]] = Max2_to_Lidar(
                points, ret['selected_gt_boxes'][s])

            angle_modified = ret['selected_gt_boxes'][s, 6] + beta
            if abs(angle_modified) > np.pi:
                angle_modified = angle_modified - angle_modified / abs(
                    angle_modified) * 2 * np.pi

            ret['selected_gt_boxes'][s][6] = angle_modified
            ret['is_fn'][s] = False
            ret['is_fn2'][s] = False
            break

        if try_num <= 0:
            raise ValueError(f'Expected try_num > 0, found {try_num}.')

        return [ret]

    def scale(self, ret, rate=None, DUMPS=None):
        hull = ret['road_hull']

        try_num = 30
        while try_num:
            s = np.random.choice(ret['selected_pc_mask'].shape[0])
            center = ret['selected_gt_boxes'][s, :2]

            if hull.disjoint(Point(center)):
                try_num -= 1
                continue

            low, high = -0.2, 0.2

            points = ret['points'][ret['selected_pc_mask'][s]]

            points = Lidar_to_Max2(points, ret['selected_gt_boxes'][s])

            xs, ys, zs = np.ones(3) + (np.random.uniform(low, high, 3) if rate
                                       is None else np.array([rate] * 3))

            matrix = np.array([[xs, 0, 0, 0], [0, ys, 0, 0], [0, 0, zs, 0],
                               [0, 0, 0, 1]])

            points = np.matmul(points, matrix)
            points[:, 2] += (zs - 1) * ret['selected_gt_boxes'][s][5] / np.max(
                ret['selected_gt_boxes'][s][3:6])

            ret['points'][ret['selected_pc_mask'][s]] = Max2_to_Lidar(
                points, ret['selected_gt_boxes'][s])

            ret['selected_gt_boxes'][s][3:6] = np.matmul(
                ret['selected_gt_boxes'][s][3:6],
                np.array([[xs, 0, 0], [0, ys, 0], [0, 0, zs]]))
            ret['is_fn'][s] = False
            ret['is_fn2'][s] = False
            break

        if try_num <= 0:
            raise ValueError(f'Expected try_num > 0, found {try_num}.')

        return [ret]

    def insert(self, ret, rate=None, DUMPS=None):

        obj_car_dirs = os.listdir('_assets/shapenet')
        obj_num = len(obj_car_dirs)

        objs_index = np.random.randint(1, obj_num)

        obj_mesh_path = Path('_assets/shapenet') / obj_car_dirs[
            objs_index] / 'models' / 'model_normalized.gltf'

        road_pc_valid = get_valid_pints(ret['mtest_calib'], ret['road_pc'])
        mesh_obj_initial = load_normalized_mesh_obj(obj_mesh_path.as_posix())

        corners_lidar = box_utils.boxes_to_corners_3d(ret['selected_gt_boxes'])

        initial_boxes, _objs_half_diagonal, _objs_center = get_initial_box3d_in_bg(
            corners_lidar)

        objs_half_diagonal = _objs_half_diagonal.copy()
        objs_center = _objs_center.copy()

        try_num = 30
        while try_num > 0:
            half_diagonal, _, _ = get_geometric_info(mesh_obj_initial)
            position, rz_degree = generate_pose(mesh_obj_initial,
                                                road_pc_valid,
                                                ret['road_labels'])
            mesh_obj = tranform_mesh_by_pose(mesh_obj_initial, position,
                                             rz_degree)
            onroad_flag = is_on_road(mesh_obj, ret['road_pc'],
                                     ret['non_road_pc'])
            if not onroad_flag:
                try_num -= 1
                continue

            barycenter_xy = mesh_obj.get_center()[:2]
            success_flag = collision_detection(barycenter_xy, half_diagonal,
                                               objs_half_diagonal, objs_center,
                                               len(initial_boxes))

            if not success_flag:
                try_num -= 1
                continue

            box_inserted_o3d = mesh_obj.get_minimal_oriented_bounding_box()

            break

        if try_num <= 0:
            raise ValueError(f'Expected try_num > 0, found {try_num}.')

        box, angle = change_3dbox(box_inserted_o3d)

        pcd_obj = lidar_simulation(mesh_obj)
        label_ins = get_labels(rz_degree, box, ret['mtest_calib'], None, None)

        combine_pc, labels_insert = combine_pcd(ret['points'][:, :-1],
                                                [pcd_obj], [mesh_obj],
                                                [label_ins])
        mixed_pc = complet_pc(combine_pc).astype(np.float32)

        if self.dataset_name == config.kitti:
            mixed_pc[:, -1] = 0.1
        elif self.dataset_name == config.nuscenes:
            mixed_pc[:, -1] = 25
        else:
            raise NotImplementedError

        gt_boxes_ins = np.concatenate([
            box.center.reshape(1, -1),\
            box.extent.reshape(1, -1),\
            [[-(np.pi / 2 + float(label_ins[-1]))]]
        ], axis=1)
        ret['selected_gt_boxes'] = np.append(ret['selected_gt_boxes'],
                                             gt_boxes_ins,
                                             axis=0).astype(np.float32)

        corners_lidar = box_utils.boxes_to_corners_3d(ret['selected_gt_boxes'])
        selected_mask = None
        for k in range(corners_lidar.shape[0]):
            selected_mask = \
                np.append(
                    selected_mask,
                    box_utils.in_hull(
                        mixed_pc[:, 0:3],
                        corners_lidar[k]
                    ).reshape(1, -1),
                    axis=0
                ) if selected_mask is not None else\
                box_utils.in_hull(
                    mixed_pc[:, 0:3],
                    corners_lidar[k]
                ).reshape(1, -1)

        ret['selected_pc_mask'] = selected_mask
        ret['points'] = mixed_pc

        if self.dataset_name == config.kitti:
            ret['selected_name'] = np.concatenate(
                [ret['selected_name'], ['Car']])
        elif self.dataset_name == config.nuscenes:
            ret['selected_name'] = np.concatenate(
                [ret['selected_name'], ['car']])
        else:
            raise NotImplementedError

        ret['is_fn'] = np.concatenate([ret['is_fn'], [False]])
        ret['is_fn2'] = np.concatenate([ret['is_fn2'], [False]])

        return [ret]
