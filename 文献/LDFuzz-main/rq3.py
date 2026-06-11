import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from cycler import cycler

plt.rcParams['font.family'] = 'DejaVu Serif'
plt.rcParams['font.weight'] = 'bold'
plt.rcParams['mathtext.fontset'] = 'dejavuserif'

plt.rcParams["axes.prop_cycle"] = cycler(
    'color', ['tab:red', 'tab:blue', 'tab:orange', 'tab:green'])

import numpy as np
import pandas as pd
import pickle

from utils import config

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

format_select = {
    'new': 'Ours Selection Strategy',
    'random': 'Random Selection Strategy'
}


def _gini(a):
    if isinstance(a, list):
        a = np.array(a).reshape(-1)
    a = a.astype(np.float32)
    a /= np.sum(a)
    return 1 - np.sum(a * a)


def _scene_graph(sg_encode, sg_type):
    ret = ' '
    base = 1
    for length in config.scene_graph_length_list:
        for width in config.scene_graph_width_list:
            if sg_type & base:
                if sg_encode & base:
                    ret = '■' + ret
                else:
                    ret = '□' + ret
            else:
                ret = 'x' + ret
            base <<= 1
        ret = ' ' + ret

    if sg_encode & base: ret = ret + 'RN'
    base <<= 1
    if sg_encode & base: ret = ret + 'SW'
    base <<= 1
    if sg_encode & base: ret = ret + 'FG'
    return ret


def get_gini_table(DUMPS: dict, d: dict, **kw):
    select = kw['select']
    _sum = {}
    for s in DUMPS['error_detail']:
        scene = s['scene']

        if scene not in _sum:
            _sum[scene] = 0

        _sum[scene] += s['fn_list'].shape[0]

    d[f'Gini ({select})'] = _gini(np.array(list(_sum.values())))


def get_spc_area(DUMPS: dict, ax: Axes, **kw):
    criteria = kw['criteria']
    spc_area = np.array(DUMPS['coverage1_area_list']) / 1000
    pd.DataFrame(spc_area, columns=[criteria]).plot(ax=ax)
    ax.legend(fontsize=8)


def get_sec_count(DUMPS: dict, ax: Axes, **kw):
    criteria = kw['criteria']
    pd.DataFrame(DUMPS['coverage2_count_list'], columns=[criteria]).plot(ax=ax)
    ax.legend(fontsize=8)


def get_top5(DUMPS: dict, d: dict, **kw):
    fn_arr = {}
    inv_idx = []
    for s in DUMPS['error_detail']:
        sg = s['sg_encode']
        sg_type = s['scene_graph_type']

        if (sg, sg_type) not in fn_arr:
            fn_arr[(sg, sg_type)] = [0, 0]
            inv_idx.append((sg, sg_type))

        # fn_arr[(sg, sg_type)][0] += s['fn_list'].shape[0]
        # fn_arr[(sg, sg_type)][1] += s['gt_boxes'].shape[0]
        if s['fn_list'].shape[0]:
            fn_arr[(sg, sg_type)][0] += 1
        fn_arr[(sg, sg_type)][1] += 1

    for _k in fn_arr:
        fn_arr[_k][1] = round(fn_arr[_k][0] / fn_arr[_k][1], 4)

    npfn_arr = np.array(list(fn_arr.values()))

    # npfn_arr[npfn_arr[:, 0] < 70, 0] = -100
    # npfn_arr[(npfn_arr[:, 1] < 0.4) + (npfn_arr[:, 1] > 0.99), 1] = -100

    # npfn_arr = np.concatenate(
    #     [
    #         npfn_arr,
    #         np.sum(
    #             npfn_arr * [1, 1] / np.max(
    #                 npfn_arr,
    #                 axis=0,
    #             ).reshape(1, -1),
    #             axis=-1,
    #         ).reshape(-1, 1),
    #     ],
    #     axis=-1,
    # )
    inv_idx = np.array(inv_idx)
    idx = npfn_arr[:, 0].argsort()[:-11:-1]

    for _i, _tup in enumerate(inv_idx[idx]):
        _tup = tuple(_tup)
        d[(f'Top {_i+1}', 'Scene Graph')] = _scene_graph(*_tup)
        d[(f'Top {_i+1}', 'SG Err')] = fn_arr[_tup][0]
        d[(f'Top {_i+1}', 'Rate')] = fn_arr[_tup][1]


def get_zd(DUMPS: dict, d: dict, **kw):

    # tup_zd = [(3, 3), (6, 7), (9, 11), (12, 15), (24, 31), (36, 47)]
    tup_zd = [(6, 7), (9, 11), (12, 15), (24, 31), (36, 47)]

    tfn = 0
    tgt = 0
    zdfn = 0
    zdgt = 0

    for s in DUMPS['error_detail']:
        sg = s['sg_encode']
        sg_type = s['scene_graph_type']

        ju = 0
        for ssg, m_ssg in tup_zd:
            if (sg ^ ssg) & m_ssg == 0 and (sg & (~m_ssg)) != 0:
                zdfn += s['fn_list'].shape[0]
                zdgt += s['gt_boxes'].shape[0]
                ju += 1

        if ju > 1:
            raise Exception('NMB')

        tfn += s['fn_list'].shape[0]
        tgt += s['gt_boxes'].shape[0]

    return zdfn, zdgt, zdfn / zdgt, tfn - zdfn, tgt - zdgt, (tfn - zdfn) / (
        tgt - zdgt)


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

    fig_area, axs_area = plt.subplots(1,
                                      4,
                                      constrained_layout=True,
                                      figsize=(12, 3))
    iter_axs_area = iter(axs_area)

    fig_count, axs_count = plt.subplots(1,
                                        4,
                                        constrained_layout=True,
                                        figsize=(12, 3))
    iter_axs_count = iter(axs_count)

    for data_name, model_name_arr in model_data.items():
        for model_name in model_name_arr:
            ax_area = next(iter_axs_area)
            ax_count = next(iter_axs_count)

            ax_area.set_title(format_model[model_name], fontweight='bold')
            ax_area.set_xlabel('Iterations', fontweight='bold')
            ax_area.set_ylabel('Area Projected to BEV ($\\times 10^3$)',
                               fontweight='bold')

            ax_count.set_title(format_model[model_name], fontweight='bold')
            ax_count.set_xlabel('Iterations', fontweight='bold')
            ax_count.set_ylabel('Equivalence Class Num. (ASGs)',
                                fontweight='bold')

            for out in out_ls:
                for c in criteria:
                    for s in select:
                        try:
                            res = f'{out}/{data_name}_{model_name}/{s}/{c}/0/result/result_{cp}.pickle'

                            with open(res, 'rb') as f:
                                DUMPS = pickle.load(f)
                            while isinstance(DUMPS, list):
                                DUMPS = DUMPS[0]

                            get_spc_area(DUMPS,
                                         ax_area,
                                         criteria=format_criteria[c])
                            get_sec_count(DUMPS,
                                          ax_count,
                                          criteria=format_criteria[c])

                        except Exception as e:
                            None

    criteria = [config.ldfuzz]

    select = ['new', 'random']

    d_gini = {}

    for data_name, model_name_arr in model_data.items():
        for model_name in model_name_arr:
            d_gini[format_model[model_name]] = {}

            for out in out_ls:
                for c in criteria:
                    for s in select:
                        try:
                            res = f'{out}/{data_name}_{model_name}/{s}/{c}/0/result/result_{cp}.pickle'

                            with open(res, 'rb') as f:
                                DUMPS = pickle.load(f)
                            while isinstance(DUMPS, list):
                                DUMPS = DUMPS[0]

                            get_gini_table(DUMPS,
                                           d_gini[format_model[model_name]],
                                           select=format_select[s])

                        except Exception as e:
                            None

    criteria = [config.ldfuzz]

    select = ['new']

    d_top5 = {}

    for data_name, model_name_arr in model_data.items():
        for model_name in model_name_arr:
            d_top5[format_model[model_name]] = {}

            for out in out_ls:
                for c in criteria:
                    for s in select:
                        try:
                            res = f'{out}/{data_name}_{model_name}/{s}/{c}/0/result/result_{cp}.pickle'

                            with open(res, 'rb') as f:
                                DUMPS = pickle.load(f)
                            while isinstance(DUMPS, list):
                                DUMPS = DUMPS[0]

                            get_top5(DUMPS, d_top5[format_model[model_name]])

                            # print(get_zd(DUMPS, {}))

                        except Exception as e:
                            None

    print(pd.DataFrame(d_top5))

    # pd.DataFrame(d_gini).T.to_excel('rq3_gini.xlsx')
    fig_area.savefig('rq3_area.pdf', format='pdf')
    fig_count.savefig('rq3_count.pdf', format='pdf')
