import os
import sys
import json
import argparse
import numpy as np

try:
    from nuscenes.nuscenes import NuScenes
    from pyquaternion import Quaternion
except Exception:
    here = os.path.dirname(os.path.abspath(__file__))
    sdk_fallback = os.path.normpath(os.path.join(here, '..', 'nuscenes-devkit', 'nuscenes-devkit-master', 'python-sdk'))
    if os.path.isdir(sdk_fallback) and sdk_fallback not in sys.path:
        sys.path.insert(0, sdk_fallback)
    from nuscenes.nuscenes import NuScenes
    from pyquaternion import Quaternion


CAM_CHANNELS = [
    'CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT',
    'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT'
]


def T_from_qt(q, t):
    R = Quaternion(q).rotation_matrix
    t = np.asarray(t, dtype=float)
    return R, t


def ego_to_sensor(p_e, R_es, t_es):
    return R_es.T @ (p_e - t_es)


def project(K, p_s):
    x, y, z = p_s
    if z <= 0:
        return None
    u = K[0, 0] * (x / z) + K[0, 2]
    v = K[1, 1] * (y / z) + K[1, 2]
    return float(u), float(v), float(z)


def process_frame(nusc: NuScenes, frame: dict, channels, min_corner_vis: int = 2):
    sample = nusc.get('sample', frame['sample_token'])

    # prepare per-channel calibration cache
    calibs = {}
    for ch in channels:
        if ch not in sample['data']:
            continue
        sd = nusc.get('sample_data', sample['data'][ch])
        cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
        R_es, t_es = T_from_qt(cs['rotation'], cs['translation'])
        K = np.array(cs['camera_intrinsic'], dtype=float)
        calibs[ch] = {
            'R_es': R_es,
            't_es': np.asarray(t_es, dtype=float),
            'K': K,
            'w': sd.get('width', None),
            'h': sd.get('height', None)
        }

    # annotate nodes
    for n in frame['nodes']:
        if n['id'] == 'ego':
            n.setdefault('visibility', {})
            for ch in channels:
                n['visibility'][ch] = {'visible': True, 'bbox2d': None, 'center_uv': None, 'depth': None}
            continue
        corners_e = np.array(n.get('corners_ego', []), dtype=float)  # 8x3
        center_e = np.array(n['pose']['ego']['center'], dtype=float)
        n.setdefault('visibility', {})
        for ch in channels:
            calib = calibs.get(ch)
            if not calib:
                continue
            R_es, t_es, K = calib['R_es'], calib['t_es'], calib['K']
            W, H = calib['w'], calib['h']
            # project center
            pc = ego_to_sensor(center_e, R_es, t_es)
            cp = project(K, pc)
            center_uv = None
            depth = None
            if cp is not None:
                u, v, z = cp
                center_uv = [u, v]
                depth = z
            # project corners
            pts = []
            inside = 0
            xs, ys = [], []
            for p in corners_e:
                ps = ego_to_sensor(p, R_es, t_es)
                uvz = project(K, ps)
                if uvz is None:
                    continue
                u, v, z = uvz
                pts.append((u, v, z))
                xs.append(u)
                ys.append(v)
                if W is not None and H is not None:
                    if 0 <= u < W and 0 <= v < H:
                        inside += 1
            if pts:
                xmin = float(min(xs)); xmax = float(max(xs))
                ymin = float(min(ys)); ymax = float(max(ys))
                bbox2d = [xmin, ymin, xmax, ymax]
            else:
                bbox2d = None
            visible = inside >= min_corner_vis
            n['visibility'][ch] = {
                'visible': bool(visible),
                'bbox2d': bbox2d,
                'center_uv': center_uv,
                'depth': depth
            }

    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataroot', type=str, required=True)
    ap.add_argument('--version', type=str, default='v1.0-mini')
    ap.add_argument('--jsonl_in', type=str, required=True)
    ap.add_argument('--jsonl_out', type=str, required=True)
    ap.add_argument('--channels', type=str, nargs='*', default=CAM_CHANNELS)
    ap.add_argument('--min_corner_vis', type=int, default=2)
    ap.add_argument('--max_frames', type=int, default=None)
    args = ap.parse_args()

    nusc = NuScenes(version=args.version, dataroot=args.dataroot, verbose=False)

    cnt = 0
    kept = 0
    with open(args.jsonl_out, 'w', encoding='utf-8') as fw:
        with open(args.jsonl_in, 'r', encoding='utf-8') as fr:
            for line in fr:
                if args.max_frames is not None and cnt >= args.max_frames:
                    break
                frame = json.loads(line)
                frame = process_frame(nusc, frame, args.channels, args.min_corner_vis)
                fw.write(json.dumps(frame) + '\n')
                cnt += 1
                kept += 1
    print(f"Wrote {kept} frames with visibility to {args.jsonl_out}")


if __name__ == '__main__':
    main()
