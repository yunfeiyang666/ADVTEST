import os

os.environ['PROJECT_DIR'] = os.path.dirname(__file__)

import pickle
import numpy as np

from utils import config
from utils.coverage_utils import get_gt_polygon, get_scene_graph_encode, cal_single_c1, cal_single_c2

from pcdet.ops.iou3d_nms import iou3d_nms_utils

import mlab_visual

import matplotlib.pyplot as plt
from cycler import cycler

plt.rcParams['font.family'] = 'DejaVu Serif'
plt.rcParams['font.weight'] = 'bold'
plt.rcParams['mathtext.fontset'] = 'dejavuserif'

plt.rcParams["axes.prop_cycle"] = cycler(
    'color', ['tab:red', 'tab:blue', 'tab:orange', 'tab:green'])

from matplotlib.axes import Axes

from shapely.geometry import Point, MultiPolygon

import rustworkx as rx
from rustworkx.visualization import graphviz_draw

import pandas as pd

global global_fn

format_model = {
    config.pointpillar: 'PointPillar',
    config.pv_rcnn: 'PV-RCNN',
    config.second: 'SECOND',
    config.pointrcnn: 'PointRCNN'
}

format_criteria = {
    config.spc: 'SPC',
    config.sec: 'SEC',
    config.ldfuzz: 'LDFuzz',
    config.none: 'No Guidance'
}


def draw_3dscene(seed):
    if isinstance(seed, str):
        with open(seed, 'rb') as f:
            seed = pickle.load(f)

    while isinstance(seed, list):
        seed = seed[0]

    iou = None
    if 'pred_boxes' in seed and 'selected_gt_boxes' in seed:
        iou = iou3d_nms_utils.boxes_bev_iou_cpu(seed['pred_boxes'],
                                                seed['selected_gt_boxes'])
        if iou.shape[1] != 0:
            iou = np.max(iou, axis=1).reshape(-1)
        else:
            iou = np.array([0] * iou.shape[0])

    mlab_visual.draw_scenes(
        None,
        seed['points'],
        seed['selected_gt_boxes'] if 'selected_gt_boxes' in seed else None,
        seed['pred_boxes'] if 'pred_boxes' in seed else None,
        ref_scores=iou)


def draw_road(ax: Axes, seed):
    if isinstance(seed, str):
        with open(seed, 'rb') as f:
            seed = pickle.load(f)

    while isinstance(seed, list):
        seed = seed[0]

    hull = seed['road_hull']
    ax.plot(
        hull.exterior.xy[0],
        hull.exterior.xy[1],
        color='red',
        linewidth=4,
        label='TotalArea',
    )

    points = seed['points'][:, :2]
    pts_mask = np.array([hull.intersects(Point(_p)) for _p in points])
    points = points[pts_mask]
    ax.scatter(points.T[0], points.T[1], s=1, color='grey')

    gt_poly = get_gt_polygon(seed['selected_gt_boxes'])
    gt_poly = hull.intersection(gt_poly)
    if isinstance(gt_poly, MultiPolygon):
        for geom in gt_poly.geoms:
            ax.fill(
                geom.exterior.xy[0],
                geom.exterior.xy[1],
                color='blue',
                alpha=0.25,
                label='LPA',
            )
    else:
        ax.fill(
            gt_poly.exterior.xy[0],
            gt_poly.exterior.xy[1],
            color='blue',
            alpha=0.25,
            label='LPA',
        )


def draw_result(ax: Axes, res, scene):
    if isinstance(res, str):
        with open(res, 'rb') as f:
            res = pickle.load(f)

    while isinstance(res, list):
        res = res[0]

    res = res['scene'][scene]
    kitti_idx = res['kitti_idx']
    sg_type = res['scene_graph_type']
    hull = res['road_hull']

    ax.plot(hull.exterior.xy[0], hull.exterior.xy[1], color='red')

    gt_poly = res['gt_polygon']
    if isinstance(gt_poly, MultiPolygon):
        for geom in gt_poly.geoms:
            ax.plot(geom.exterior.xy[0], geom.exterior.xy[1], color='blue')
    else:
        ax.plot(gt_poly.exterior.xy[0], gt_poly.exterior.xy[1], color='blue')

    ax.grid(True)
    ax.set_title(f'Kitti Index : {kitti_idx} Scene Graph Type : {sg_type}')


def draw_fp(ax: Axes, res, **kw):
    if isinstance(res, str):
        with open(res, 'rb') as f:
            res = pickle.load(f)

    while isinstance(res, list):
        res = res[0]

    fp = res['fp']

    size = len(fp) // 8

    x = list(range(len(fp)))

    if 'criteria' in kw:
        criteria = kw['criteria'].replace('_', ' ').title()
        criteria += ' '
    else:
        criteria = ''

    if 'model' in kw:
        model = kw['model'].replace('_', ' ').title()
    else:
        model = ''

    if 'select' in kw:
        select = kw['select'].replace('_', ' ').title()
    else:
        select = ''

    ax.plot(x, fp, marker='^', markevery=size, label=f'{criteria} {select} FP')

    ax.grid(True)
    ax.set_title(model)
    ax.legend(loc='upper left')


def draw_fn(DUMPS: dict, d: dict, ax: Axes, **kw):
    criteria = format_criteria[kw['criteria']]
    fn = None
    for _me in DUMPS[global_fn]:
        if fn is None:
            fn = np.array(DUMPS[global_fn][_me])
        else:
            fn += np.array(DUMPS[global_fn][_me])

    size = fn.shape[0] // 8
    if size == 0: size = 1

    fn = fn / 1000
    pd.DataFrame(fn, columns=[criteria]).plot(ax=ax,
                                              marker='s',
                                              markersize=3,
                                              markevery=size)
    ax.legend(fontsize=8)
    # ax.annotate(f'{int(fn[-1]*1000)}', (1005, fn[-1]))
    # ax.set_xlim(right=1200)

    total_fn = 0
    total_gt = 0

    for s in DUMPS['error_detail']:
        boxes = s['gt_boxes']
        fn_list = s['fn_list']

        total_fn += fn_list.shape[0]
        total_gt += boxes.shape[0]

    d[(criteria, 'FN')] = total_fn
    d[(criteria, 'FN/GT')] = round(total_fn / total_gt, 4)

    return


def draw_crash(ax: Axes, res, **kw):
    if isinstance(res, str):
        with open(res, 'rb') as f:
            res = pickle.load(f)

    while isinstance(res, list):
        res = res[0]

    crash = res['crash']

    size = len(crash) // 8

    x = list(range(len(crash)))

    if 'criteria' in kw:
        criteria = kw['criteria'].replace('_', ' ').title()
        criteria += ' '
    else:
        criteria = ''

    if 'model' in kw:
        model = kw['model'].replace('_', ' ').title()
    else:
        model = ''

    if 'select' in kw:
        select = kw['select'].replace('_', ' ').title()
    else:
        select = ''

    ax.plot(x,
            crash,
            marker='x',
            markevery=size,
            label=f'{criteria} {select} Crash')

    ax.grid(True)
    ax.set_title(model)
    ax.legend(loc='upper left')


def draw_scene_graph(ax: Axes, seed):
    if isinstance(seed, str):
        with open(seed, 'rb') as f:
            seed = pickle.load(f)

    while isinstance(seed, list):
        seed = seed[0]

    s_gt_boxes = seed['selected_gt_boxes']
    s_name = seed['selected_name']
    w_type = seed['weather_type']
    sg_type = seed['scene_graph_type']

    sg_encode = get_scene_graph_encode(s_gt_boxes, s_name, w_type, sg_type)

    graph = rx.PyDiGraph()

    w_type = w_type if w_type is not None else 'Sunny'
    ego = graph.add_node('ego')
    graph.add_parent(ego, f'{w_type}', 'weather')

    area = []
    base = 1
    for ix, x in enumerate(config.scene_graph_length_list):
        sub_area = []

        for iy, y in enumerate(config.scene_graph_width_list):
            if sg_type & base:
                if 2 * iy < len(config.scene_graph_width_list):
                    node = graph.add_node(f'Right Range{ix+1}\nx:{x} y:{y}')
                else:
                    node = graph.add_node(f'Left Range{ix+1}\nx:{x} y:{y}')
                if sg_encode & base:
                    graph.add_parent(node, 'Car', 'exist in')
                sub_area.append(node)
            else:
                sub_area.append(None)
            base <<= 1

        if len(area):
            prev = area[-1]
            for k in range(len(sub_area)):
                if prev[k] is not None and sub_area[k] is not None:
                    graph.add_edge(prev[k], sub_area[k], 'connect to')
        else:
            for k in range(len(sub_area)):
                if 2 * k < len(sub_area):
                    graph.add_edge(ego, sub_area[k], 'toRight')
                else:
                    graph.add_edge(ego, sub_area[k], 'toLeft')
        area.append(sub_area)

    image = graphviz_draw(graph,
                          node_attr_fn=lambda node: {'label': node},
                          edge_attr_fn=lambda edge: {"label": edge},
                          graph_attr={'rankdir': 'BT'})

    ax.axis('off')
    ax.imshow(image)


def draw_chain(ax: Axes, dir, scene, **kw):

    def load_and_get_c1c2(fn):
        with open(fn, 'rb') as f:
            res = pickle.load(f)
        while isinstance(res, list):
            res = res[0]
        c1, c2 = cal_single_c1(res['gt_polygon'],
                               res['road_hull']), cal_single_c2(
                                   res['cluster'], res['scene_graph_type'])
        return c1, c2, res['level']

    graph = rx.PyDiGraph()
    dict_node = {}

    fn_list = os.listdir(f'{dir}/0/queue/{scene}')

    for fn in fn_list:
        c1, c2, le = load_and_get_c1c2(f'{dir}/0/queue/{scene}/{fn}')

        id = fn.split('_')[1]
        parent = fn.split('_')[3].rstrip('.pickle')

        if id not in dict_node:
            node_id = graph.add_node(
                {'label': f'{id}\n{c1:.02%}\n{c2:.02%}\n{le}'})
            dict_node[id] = node_id
        else:
            node_id = dict_node[id]

        if parent not in dict_node:
            flag = False
            for p in fn_list:
                if p.startswith(f'id_{parent}'):
                    flag = True
                    c1, c2, le = load_and_get_c1c2(
                        f'{dir}/0/queue/{scene}/{p}')

            if flag:
                node_parent = graph.add_node(
                    {'label': f'{parent}\n{c1:.02%}\n{c2:.02%}\n{le}'})
            else:
                node_parent = graph.add_node({'label': 'INIT'})
            dict_node[parent] = node_parent
        else:
            node_parent = dict_node[parent]

        graph.add_edge(node_parent, node_id, None)

    try:
        fn_list = os.listdir(f'{dir}/0/crashes/{scene}')
    except:
        fn_list = []

    for fn in fn_list:
        c1, c2, le = load_and_get_c1c2(f'{dir}/0/crashes/{scene}/{fn}')

        id = fn.split('_')[1]
        parent = fn.split('_')[3].rstrip('.pickle')

        node_id = graph.add_node({
            'label': f'{id}\n{c1:.02%}\n{c2:.02%}\n{le}',
            'color': 'red'
        })
        node_parent = dict_node[parent]

        graph.add_edge(node_parent, node_id, None)

    image = graphviz_draw(graph, node_attr_fn=lambda node: node)

    ax.axis('off')
    ax.set_title(f'{kw}')
    ax.imshow(image)


if __name__ == '__main__':

    model_data = {
        config.kitti:
        [config.pointpillar, config.pv_rcnn, config.second, config.pointrcnn]
    }

    criteria = [
        config.ldfuzz,
        config.spc,
        config.sec,
        config.none,
    ]

    select = ['new']

    out_ls = ['2024-11-23_00-20-35_754431__out']
    cp = 1000

    global_fn = 'fn'

    dict_fig = {}
    content = {}
    index = []
    method_times = {
        **{
            i: []
            for i in config.object_level + config.scene_level
        }, 'sum': []
    }
    inqueue_method_times = {
        **{
            i: []
            for i in config.object_level + config.scene_level
        }, 'sum': []
    }
    method_founderror_times = {
        **{
            i: []
            for i in config.object_level + config.scene_level
        }, 'sum': []
    }
    cov1_list = []
    cov2_list = []
    err_cov1_list = []
    err_cov2_list = []
    area_list = []
    err_area_list = []
    count_list = []
    err_count_list = []
    tot_times = {}
    seed_times = {}

    d = {}

    fig, axs = plt.subplots(1, 4, constrained_layout=True, figsize=(12, 3))
    iter_axs = iter(axs.reshape(-1))

    for data_name, model_name_arr in model_data.items():
        for model_name in model_name_arr:
            ax = next(iter_axs)
            ax.set_title(format_model[model_name], fontweight='bold')
            ax.set_xlabel('Iterations', fontweight='bold')
            ax.set_ylabel('Missed Detection Num. ($\\times 10^3$)',
                          fontweight='bold')
            d[format_model[model_name]] = {}

            ldfuzz_fn = 0
            none_fn = 0
            spc_fn = 0
            sec_fn = 0
            for out in out_ls:
                for c in criteria:
                    for s in select:
                        try:
                            res = f'{out}/{data_name}_{model_name}/{s}/{c}/0/result/result_{cp}.pickle'

                            with open(res, 'rb') as f:
                                DUMPS = pickle.load(f)
                            while isinstance(DUMPS, list):
                                DUMPS = DUMPS[0]

                            if c == 'none':
                                for nmb in DUMPS['fn']:
                                    none_fn += DUMPS['fn'][nmb][-1]
                            if c == 'ldfuzz':
                                for nmb in DUMPS['fn']:
                                    ldfuzz_fn += DUMPS['fn'][nmb][-1]
                            if c == 'spc':
                                for nmb in DUMPS['fn']:
                                    spc_fn += DUMPS['fn'][nmb][-1]
                            if c == 'sec':
                                for nmb in DUMPS['fn']:
                                    sec_fn += DUMPS['fn'][nmb][-1]

                            draw_fn(DUMPS,
                                    d[format_model[model_name]],
                                    ax,
                                    criteria=c)
                        except Exception as e:
                            None
                print(
                    f'{format_model[model_name]} : {ldfuzz_fn / np.max([none_fn, spc_fn, sec_fn]) - 1}'
                )

    for ax in iter_axs:
        ax.set_visible(False)

    pd.DataFrame(d).T.to_excel('rq2_table.xlsx')
    fig.savefig('rq2.pdf', format='pdf')
