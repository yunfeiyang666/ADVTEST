import matplotlib.pyplot as plt
from cycler import cycler

import numpy as np
import pickle
from utils import config
import math

from matplotlib.patches import Circle, RegularPolygon
from matplotlib.path import Path
from matplotlib.projections import register_projection
from matplotlib.projections.polar import PolarAxes
from matplotlib.spines import Spine
from matplotlib.transforms import Affine2D

plt.rcParams['font.family'] = 'DejaVu Serif'
plt.rcParams['font.weight'] = 'bold'
plt.rcParams['mathtext.fontset'] = 'dejavuserif'

plt.rcParams["axes.prop_cycle"] = cycler('color', ['tab:green', 'tab:blue'])

rq1_root_path = './__rq1_out'
seeds_path = f'{rq1_root_path}/seeds'

format_model = {
    config.pointpillar: 'PointPillar',
    config.pv_rcnn: 'PV-RCNN',
    config.second: 'SECOND',
    config.pointrcnn: 'PointRCNN'
}

format_method = {
    'rain': 'RN',
    'snow': 'SW',
    'fog': 'FG',
    'translocate': 'TL',
    'rotation': 'RT',
    'insert': 'IS',
    'scale': 'SC'
}

format_legend = [
    'Results on Original Testing Dataset $T_O$',
    'Results on 7 Transformed Testing Dataset $T_A$'
]


def radar_factory(num_vars, frame='circle'):
    """
    Create a radar chart with `num_vars` Axes.

    This function creates a RadarAxes projection and registers it.

    Parameters
    ----------
    num_vars : int
        Number of variables for radar chart.
    frame : {'circle', 'polygon'}
        Shape of frame surrounding Axes.

    """
    # calculate evenly-spaced axis angles
    theta = np.linspace(0, 2 * np.pi, num_vars, endpoint=False)

    class RadarTransform(PolarAxes.PolarTransform):

        def transform_path_non_affine(self, path):
            # Paths with non-unit interpolation steps correspond to gridlines,
            # in which case we force interpolation (to defeat PolarTransform's
            # autoconversion to circular arcs).
            if path._interpolation_steps > 1:
                path = path.interpolated(num_vars)
            return Path(self.transform(path.vertices), path.codes)

    class RadarAxes(PolarAxes):

        name = 'radar'
        PolarTransform = RadarTransform

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # rotate plot such that the first axis is at the top
            self.set_theta_zero_location('N')

        def fill(self, *args, closed=True, **kwargs):
            """Override fill so that line is closed by default"""
            return super().fill(closed=closed, *args, **kwargs)

        def plot(self, *args, **kwargs):
            """Override plot so that line is closed by default"""
            lines = super().plot(*args, **kwargs)
            for line in lines:
                self._close_line(line)

        def _close_line(self, line):
            x, y = line.get_data()
            # FIXME: markers at x[0], y[0] get doubled-up
            if x[0] != x[-1]:
                x = np.append(x, x[0])
                y = np.append(y, y[0])
                line.set_data(x, y)

        def set_varlabels(self, labels):
            self.set_thetagrids(np.degrees(theta), labels)

        def _gen_axes_patch(self):
            # The Axes patch must be centered at (0.5, 0.5) and of radius 0.5
            # in axes coordinates.
            if frame == 'circle':
                return Circle((0.5, 0.5), 0.5)
            elif frame == 'polygon':
                return RegularPolygon((0.5, 0.5),
                                      num_vars,
                                      radius=.5,
                                      edgecolor="k")
            else:
                raise ValueError("Unknown value for 'frame': %s" % frame)

        def _gen_axes_spines(self):
            if frame == 'circle':
                return super()._gen_axes_spines()
            elif frame == 'polygon':
                # spine_type must be 'left'/'right'/'top'/'bottom'/'circle'.
                spine = Spine(axes=self,
                              spine_type='circle',
                              path=Path.unit_regular_polygon(num_vars))
                # unit_regular_polygon gives a polygon of radius 1 centered at
                # (0, 0) but we want a polygon of radius 0.5 centered at (0.5,
                # 0.5) in axes coordinates.
                spine.set_transform(Affine2D().scale(.5).translate(.5, .5) +
                                    self.transAxes)
                return {'polar': spine}
            else:
                raise ValueError("Unknown value for 'frame': %s" % frame)

    register_projection(RadarAxes)
    return theta


def example_data(data_name, model_name):
    with open(f'{rq1_root_path}/{data_name}_{model_name}.pickle', 'rb') as f:
        res = pickle.load(f)

    for _i in res:
        if math.isnan(res[_i]):
            res[_i] = 0
    ret = [[res['none']] * len(config.scene_level + config.object_level),
           [res[_i] for _i in config.scene_level + config.object_level]]
    return ret


if __name__ == '__main__':

    print([format_method[i] for i in config.scene_level + config.object_level])

    model_data = {
        config.kitti:
        [config.pointpillar, config.pv_rcnn, config.second, config.pointrcnn]
    }

    N = 7
    theta = radar_factory(N)

    fig, axs = plt.subplots(2,
                            4,
                            subplot_kw=dict(projection='radar'),
                            gridspec_kw=dict(height_ratios=[5, 1]),
                            constrained_layout=True,
                            figsize=(8, 2.4))
    iter_axs = iter(axs.reshape(-1))
    for data_name, model_name_arr in model_data.items():
        for model_name in model_name_arr:
            print(format_model[model_name])
            ax = next(iter_axs)
            ax.set_title(format_model[model_name],
                         y=-0.2,
                         pad=0,
                         fontweight='bold')
            ax.set_rgrids([45, 60, 75])

            data = example_data(data_name, model_name)
            ax.set_rlim([45, data[0][0]])

            for i, d in enumerate(data):
                if i == 0:
                    ax.plot(theta, d, label=format_legend[i])
                    ax.fill_between(theta.tolist() + [theta[0]],
                                    data[0] + [data[0][0]],
                                    data[1] + [data[1][0]],
                                    interpolate=True,
                                    alpha=0.25)
                    print('before : ', d)
                    before_d = np.array(d)
                if i == 1:
                    ax.plot(theta, d, label=format_legend[i])
                    ax.fill(theta, d, alpha=0.25)
                    print('after : ', d)
                    after_d = np.array(d)

            print('percent : ', ((before_d - after_d) / before_d).tolist())

            ax.set_varlabels([
                format_method[i]
                for i in config.scene_level + config.object_level
            ])
            ax.tick_params('x', pad=0)

    for ax in iter_axs:
        ax.set_visible(False)

    fig.legend(handles=list(axs[0, 0].lines), loc='lower left', ncol=2)
    fig.savefig('rq1.pdf', format='pdf')
