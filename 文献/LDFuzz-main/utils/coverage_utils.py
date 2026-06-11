from typing import Union

import numpy as np

import shapely
from shapely.geometry import MultiPoint, Polygon, MultiPolygon

from pcdet.utils import box_utils

from .config import scene_level, scene_graph_length_list, scene_graph_width_list, kitti, nuscenes

nuscenes_class = [
    'car', 'truck', 'construction_vehicle', 'bus', 'trailer', 'motorcycle',
    'bicycle', 'pedestrian'
]
kitti_class = ['Car']


def cls2bit(dataset_name, cls: str):

    if dataset_name == kitti:
        x = kitti_class.index(cls)
    elif dataset_name == nuscenes:
        x = nuscenes_class.index(cls)

    return 1 << x


def get_coverage1_area(DUMPS, error=False) -> float:
    ret = 0
    for scene in DUMPS['scene']:
        if error:
            ret += DUMPS['scene'][scene]['error_polygon'].area
        else:
            ret += DUMPS['scene'][scene]['gt_polygon'].area

    return ret


def get_coverage2_count(DUMPS, error=False) -> int:
    ret = 0
    for sg_type in DUMPS['cluster']:
        if error:
            ret += len(DUMPS['cluster'][sg_type]['error_cluster'])
        else:
            ret += len(DUMPS['cluster'][sg_type]['cluster'])

    return ret


def get_fp_coverage1_area(DUMPS) -> float:
    ret = 0
    for scene in DUMPS['scene']:
        ret += DUMPS['scene'][scene]['fp_polygon'].area
    return ret


def get_fp_coverage2_count(DUMPS) -> int:
    ret = 0
    for sg_type in DUMPS['cluster']:
        ret += len(DUMPS['cluster'][sg_type]['fp_cluster'])
    return ret


def get_coverage1_DUMPSver(DUMPS, error=False) -> float:
    a, b = 0, 0
    for scene in DUMPS['scene']:
        hull = DUMPS['scene'][scene]['road_hull']
        if error:
            polygon = DUMPS['scene'][scene]['error_polygon']
        else:
            polygon = DUMPS['scene'][scene]['gt_polygon']

        a += polygon.area
        b += hull.area

    return a / b


def get_coverage2_DUMPSver(DUMPS, error=False) -> float:
    sg, tot_sg = 0, 0
    for sg_type in DUMPS['cluster']:
        if error:
            sg += len(DUMPS['cluster'][sg_type]['error_cluster'])
        else:
            sg += len(DUMPS['cluster'][sg_type]['cluster'])
        tot_sg += (2**bin(sg_type).count('1')) * (len(scene_level) + 1)

    return sg / tot_sg


def get_scene_graph_type(hull: Polygon) -> int:
    ret = 0
    base = 1
    for length in scene_graph_length_list:
        for width in scene_graph_width_list:
            area = shapely.box(length[0], width[0], length[1], width[1])
            # area = shapely.box(width[0], length[0], width[1], length[1])
            if hull.intersects(area):
                ret |= base
            base <<= 1
    return ret


def get_gt_polygon(
        selected_gt_boxes: np.ndarray) -> Union[Polygon, MultiPolygon]:
    ret = None
    for k in selected_gt_boxes:
        cor = box_utils.boxes_to_corners_3d(np.array([k]))[0, :4, :2]
        if ret is None: ret = shapely.convex_hull(MultiPoint(cor))
        else: ret = shapely.union(ret, shapely.convex_hull(MultiPoint(cor)))
    return ret


def get_scene_graph_encode(dataset_name, selected_gt_boxes: np.ndarray,
                           selected_name: np.ndarray, weather_type: str,
                           sg_type: int) -> int:
    ret = [0, 0, 0, 0, 0, 0, 0]  # (..., weather)
    for k in range(selected_gt_boxes.shape[0]):
        index = 0
        base = 1
        x = selected_gt_boxes[k][0]
        y = selected_gt_boxes[k][1]
        name = selected_name[k]
        for length in scene_graph_length_list:
            for width in scene_graph_width_list:
                if sg_type & base:
                    if length[0] <= x and x < length[1] and width[
                            0] <= y and y < width[1]:
                        # if length[0] <= y and y < length[1] and width[
                        #         0] <= x and x < width[1]:
                        ret[index] |= cls2bit(dataset_name, name)
                index += 1
                base <<= 1

    # sunny : 0
    # rain : 1
    # snow : 2
    # fog : 3
    if weather_type == 'rain': ret[6] = 1
    if weather_type == 'snow': ret[6] = 2
    if weather_type == 'fog': ret[6] = 3

    return tuple(ret)


def cal_single_c1(polygon: Union[Polygon, MultiPolygon],
                  hull: Polygon) -> float:
    return shapely.intersection(polygon, hull).area / hull.area


def cal_single_c2(sg_encode_set: set, sg_type: int) -> float:
    sg = len(sg_encode_set)
    return sg
