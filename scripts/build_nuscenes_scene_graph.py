import os
import sys
import json
import math
import argparse
import numpy as np

try:
    from nuscenes.nuscenes import NuScenes
    from nuscenes.utils.data_classes import Box
    from nuscenes.map_expansion.map_api import NuScenesMap
    from pyquaternion import Quaternion
except Exception:
    here = os.path.dirname(os.path.abspath(__file__))
    sdk_fallback = os.path.normpath(os.path.join(here, '..', 'nuscenes-devkit', 'nuscenes-devkit-master', 'python-sdk'))
    if os.path.isdir(sdk_fallback) and sdk_fallback not in sys.path:
        sys.path.insert(0, sdk_fallback)
    from nuscenes.nuscenes import NuScenes
    from nuscenes.utils.data_classes import Box
    from nuscenes.map_expansion.map_api import NuScenesMap
    from pyquaternion import Quaternion


def T_from_qt(q, t):
    R = Quaternion(q).rotation_matrix
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(t, dtype=float)
    return T, R, np.asarray(t, dtype=float)


def world_to_ego(p_w, R_ge, t_ge):
    return R_ge.T @ (p_w - t_ge)


def central_diff(pos_prev, t_prev, pos_next, t_next):
    dt = max(1e-6, (t_next - t_prev))
    return (pos_next - pos_prev) / dt


def yaw_from_q(q):
    return Quaternion(q).yaw_pitch_roll[0]


def angle_diff(a2, a1):
    d = a2 - a1
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


def get_sample_ego_T(nusc, sample_token):
    s = nusc.get('sample', sample_token)
    sd_lidar = nusc.get('sample_data', s['data']['LIDAR_TOP'])
    ep = nusc.get('ego_pose', sd_lidar['ego_pose_token'])
    T_ge, R_ge, t_ge = T_from_qt(ep['rotation'], ep['translation'])
    return T_ge, R_ge, t_ge, sd_lidar['timestamp']


def get_scene_and_location(nusc, sample_token):
    s = nusc.get('sample', sample_token)
    scene = nusc.get('scene', s['scene_token'])
    log = nusc.get('log', scene['log_token'])
    return scene, log['location']


def classify_sector8(bearing_rad):
    # sectors: front, front-left, left, back-left, back, back-right, right, front-right
    ang = ((bearing_rad + math.pi) % (2 * math.pi)) - math.pi
    boundaries = [-7*math.pi/8, -5*math.pi/8, -3*math.pi/8, -math.pi/8, math.pi/8, 3*math.pi/8, 5*math.pi/8, 7*math.pi/8]
    names = ['back-right', 'right', 'front-right', 'front', 'front-left', 'left', 'back-left', 'back']
    for b, name in zip(boundaries, names):
        if ang <= b:
            return name
    return 'back'


def classify_s3c_angular(bearing_rad):
    """S3C风格的4象限角度分类 (Direct Front/Side Front/Direct Rear/Side Rear)"""
    angle_deg = math.degrees(bearing_rad)
    angle_deg = (angle_deg + 360) % 360  # 标准化到[0,360)
    
    if 315 <= angle_deg or angle_deg < 45: return "direct_front"
    elif 45 <= angle_deg < 135: return "side_front" 
    elif 135 <= angle_deg < 225: return "direct_rear"
    else: return "side_rear"


def distance_bin(d):
    if d < 2.0:
        return 'very_close'
    if d < 10.0:
        return 'close'
    if d < 30.0:
        return 'medium'
    return 'far'


def s3c_distance_bin(d):
    """S3C风格的距离分档 (更细粒度，基于安全性考虑)"""
    if d < 2.0: return "safe_hazard"    # 安全隐患 - 极危险距离
    elif d < 4.0: return "near_coll"   # 近碰撞 - 紧急制动距离
    elif d < 7.0: return "super_near"  # 超近 - 需要密切关注
    elif d < 10.0: return "very_near"  # 很近 - 影响决策
    elif d < 16.0: return "near"       # 近 - 可感知影响
    elif d < 25.0: return "visible"    # 可见 - 视野范围内
    elif d < 50.0: return "far"        # 远 - 边缘感知
    else: return None  # 超出感知范围，不包含在场景图中


def parse_attributes(nusc, ann):
    result = {
        'moving': None,
        'standing': None,
        'stopped': None,
        'parked': None,
        'with_rider': None,
        'without_rider': None,
    }
    for atok in ann.get('attribute_tokens', []) or []:
        try:
            name = nusc.get('attribute', atok)['name']
        except Exception:
            continue
        if 'moving' in name:
            result['moving'] = True
        if 'standing' in name:
            result['standing'] = True
        if 'stopped' in name:
            result['stopped'] = True
        if 'parked' in name:
            result['parked'] = True
        if 'with_rider' in name:
            result['with_rider'] = True
        if 'without_rider' in name:
            result['without_rider'] = True
    return result


def est_inst_state(nusc, ann):
    def center_time(a):
        p = np.asarray(a['translation'], dtype=float)
        st = nusc.get('sample', a['sample_token'])
        sd = nusc.get('sample_data', st['data']['LIDAR_TOP'])
        return p, sd['timestamp'] / 1e6

    p_c, t_c = center_time(ann)
    v_w = np.zeros(3, dtype=float)
    a_w = np.zeros(3, dtype=float)

    if ann['prev'] and ann['next']:
        ap = nusc.get('sample_annotation', ann['prev'])
        an = nusc.get('sample_annotation', ann['next'])
        p_p, t_p = center_time(ap)
        p_n, t_n = center_time(an)
        v_w = central_diff(p_p, t_p, p_n, t_n)
        dt = (t_n - t_p) / 2.0
        a_w = (p_n - 2 * p_c + p_p) / max(1e-6, dt * dt)
    return p_c, t_c, v_w, a_w


def build_scene_graph_for_sample(nusc, sample_token, nusc_map=None, compute_bins=True, graph_radius=60.0, min_ttc_dist=1.0, min_closing_speed=0.1, map_cache=None):
    T_ge, R_ge, t_ge, ts = get_sample_ego_T(nusc, sample_token)

    s = nusc.get('sample', sample_token)
    s_prev = nusc.get('sample', s['prev']) if s['prev'] else None
    s_next = nusc.get('sample', s['next']) if s['next'] else None

    def ego_state(sample):
        sd = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
        ep = nusc.get('ego_pose', sd['ego_pose_token'])
        p = np.asarray(ep['translation'], dtype=float)
        yaw = yaw_from_q(ep['rotation'])
        t = sd['timestamp'] / 1e6
        return p, yaw, t

    p0, yaw0, t0 = ego_state(s)
    if s_prev and s_next:
        p1, yaw1, t1 = ego_state(s_prev)
        p2, yaw2, t2 = ego_state(s_next)
        v_ego_w = central_diff(p1, t1, p2, t2)
        yaw_rate = angle_diff(yaw2, yaw1) / max(1e-6, (t2 - t1))
    else:
        v_ego_w = np.zeros(3, dtype=float)
        yaw_rate = 0.0

    w_ego_w = np.array([0.0, 0.0, yaw_rate], dtype=float)
    w_ego_e = R_ge.T @ w_ego_w

    nodes = []
    edges = []

    nodes.append({
        'id': 'ego',
        'instance_token': None,
        'category_name': 'vehicle.ego',
        'pose': {
            'ego': {'center': [0.0, 0.0, 0.0], 'yaw': 0.0},
            'global': {'center': t_ge.tolist()}
        },
        'velocity': {'ego': [0.0, 0.0, 0.0], 'global': v_ego_w.tolist()},
        'size': None,
        'corners_ego': None
    })

    for ann_token in s['anns']:
        ann = nusc.get('sample_annotation', ann_token)
        p_w, t_c, v_w, a_w = est_inst_state(nusc, ann)

        p_e = world_to_ego(p_w, R_ge, t_ge)
        q_w = Quaternion(ann['rotation'])
        yaw_e = yaw_from_q((Quaternion(matrix=R_ge.T) * q_w).elements)

        size_wlh = ann['size']
        box = Box(center=p_w, size=size_wlh, orientation=q_w)
        corners_w = box.corners().T
        corners_e = (R_ge.T @ (corners_w - t_ge).T).T

        v_rel_e = R_ge.T @ (v_w - v_ego_w) - np.cross(w_ego_e, p_e)

        # map attachment (地图挂接) - 优化版本
        on_layer = None
        on_lane_id = None
        in_intersection = None
        if nusc_map is not None:
            try:
                # 使用缓存提高性能
                cache_key = f"{p_w[0]:.1f},{p_w[1]:.1f}"  # 0.1m精度缓存
                if map_cache and cache_key in map_cache:
                    cached_result = map_cache[cache_key]
                    on_layer = cached_result['layer']
                    on_lane_id = cached_result['lane_id']
                    in_intersection = cached_result['in_intersection']
                else:
                    # 先查询车道
                    lane_tok = nusc_map.record_on_point(float(p_w[0]), float(p_w[1]), 'lane')
                    if lane_tok:
                        on_layer = 'lane'
                        on_lane_id = lane_tok
                        in_intersection = False
                    else:
                        # 尝试查询路口连接段
                        try:
                            layers = nusc_map.layers_on_point(float(p_w[0]), float(p_w[1]))
                            if 'lane_connector' in layers:
                                lane_conn_records = nusc_map.get_records_in_radius(float(p_w[0]), float(p_w[1]), 2.0, ['lane_connector'])
                                if lane_conn_records['lane_connector']:
                                    on_layer = 'lane_connector'
                                    on_lane_id = lane_conn_records['lane_connector'][0]
                                    in_intersection = True
                        except:
                            pass
                        
                        # 最近车道回退
                        if on_lane_id is None:
                            lane_closest = nusc_map.get_closest_lane(float(p_w[0]), float(p_w[1]), radius=10.0)
                            if lane_closest:
                                on_layer = 'lane'
                                on_lane_id = lane_closest
                                in_intersection = False
                    
                    # 缓存结果
                    if map_cache is not None:
                        map_cache[cache_key] = {
                            'layer': on_layer,
                            'lane_id': on_lane_id, 
                            'in_intersection': in_intersection
                        }
            except Exception as e:
                pass

        # attributes
        attrs = parse_attributes(nusc, ann)

        # bins relative to ego
        dist = float(np.linalg.norm(p_e[:2]))
        bearing = math.atan2(p_e[1], p_e[0])
        
        # 原始8扇区分类
        sector8 = classify_sector8(bearing) if compute_bins else None
        dist_bin = distance_bin(dist) if compute_bins else None
        
        # S3C风格分类 (借鉴S3C的处理策略)
        s3c_angular = classify_s3c_angular(bearing) if compute_bins else None
        s3c_distance = s3c_distance_bin(dist) if compute_bins else None
        
        # S3C策略：超过50m的对象不包含在场景图中
        if dist > 50.0:
            continue  # 跳过距离过远的对象

        nodes.append({
            'id': ann['token'],
            'instance_token': ann['instance_token'],
            'category_name': ann['category_name'],
            'pose': {
                'ego': {'center': p_e.tolist(), 'yaw': float(yaw_e)},
                'global': {'center': p_w.tolist()}
            },
            'velocity': {'ego': v_rel_e.tolist(), 'global': v_w.tolist()},
            'size': {'wlh': size_wlh},
            'corners_ego': corners_e.tolist(),
            'map': {'on_layer': on_layer, 'on_lane_id': on_lane_id, 'in_intersection': in_intersection},
            'attributes': attrs,
            'bins': {
                'sector8': sector8, 
                'distance': dist_bin,
                's3c_angular': s3c_angular,    # S3C风格角度分类
                's3c_distance': s3c_distance   # S3C风格距离分档
            }
        })

    id_to_node = {n['id']: n for n in nodes}
    ids = [n['id'] for n in nodes]

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            ni = id_to_node[ids[i]]
            nj = id_to_node[ids[j]]
            pi = np.asarray(ni['pose']['ego']['center'], dtype=float) if ni['pose']['ego']['center'] is not None else np.zeros(3)
            pj = np.asarray(nj['pose']['ego']['center'], dtype=float) if nj['pose']['ego']['center'] is not None else np.zeros(3)
            vi = np.asarray(ni['velocity']['ego'], dtype=float) if ni['velocity']['ego'] is not None else np.zeros(3)
            vj = np.asarray(nj['velocity']['ego'], dtype=float) if nj['velocity']['ego'] is not None else np.zeros(3)

            delta = pj - pi
            # Skip if distance is too far (S3C风格: 50m以外不包含在场景图中)
            if np.linalg.norm(delta) > min(graph_radius, 50.0):  # 借鉴S3C的50m阈值
                continue
            bearing = math.atan2(delta[1], delta[0])
            rel = vj - vi
            ttc = None
            if np.linalg.norm(delta) > min_ttc_dist:
                u = delta / np.linalg.norm(delta)
                closing = -float(np.dot(rel, u))
                if closing > min_closing_speed:
                    ttc = dist / closing

            # relation type relative to ego heading
            phi = abs(bearing)
            if (ni.get('map') and ni['map'].get('in_intersection')) or (nj.get('map') and nj['map'].get('in_intersection')):
                relation_type = 'intersecting'
            else:
                relation_type = 'longitudinal' if (phi <= math.pi/4 or phi >= 3*math.pi/4) else 'lateral'

            # same/adjacent lane heuristics
            same_lane = False
            adjacent_lane = None
            oni = ni.get('map', {}).get('on_lane_id')
            onj = nj.get('map', {}).get('on_lane_id')
            layer_i = ni.get('map', {}).get('on_layer')
            layer_j = nj.get('map', {}).get('on_layer')
            if oni and onj and layer_i == 'lane' and layer_j == 'lane':
                same_lane = (oni == onj)
                if not same_lane and relation_type == 'lateral':
                    # heuristic: lanes side-by-side within lateral 5m & longitudinal overlap
                    if abs(delta[1]) < 5.0 and abs(delta[0]) < 20.0:
                        adjacent_lane = True
                    else:
                        adjacent_lane = False

            edges.append({
                'from': ni['id'],
                'to': nj['id'],
                'distance': dist,
                'bearing_ego': bearing,
                'front_of': bool(delta[0] > tau_x),
                'left_of': bool(delta[1] > tau_y),
                'ttc': ttc,
                'relation_type': relation_type,
                'same_lane': same_lane,
                'adjacent_lane': adjacent_lane
            })

    graph = {
        'sample_token': sample_token,
        'timestamp': int(ts),
        'prev_sample_token': s['prev'],
        'next_sample_token': s['next'],
        'nodes': nodes,
        'edges': edges
    }
    return graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataroot', type=str, required=True)
    parser.add_argument('--version', type=str, default='v1.0-mini')
    parser.add_argument('--out_path', type=str, default='scene_graph.jsonl')
    parser.add_argument('--graph_radius', type=float, default=60.0)
    parser.add_argument('--tau_x', type=float, default=0.5)
    parser.add_argument('--tau_y', type=float, default=0.5)
    parser.add_argument('--min_closing_speed', type=float, default=0.5)
    parser.add_argument('--min_ttc_dist', type=float, default=0.5)
    parser.add_argument('--first_n_scenes', type=int, default=None)
    parser.add_argument('--disable_map', action='store_true', help='Disable map attachment and map-based fields')
    parser.add_argument('--disable_bins', action='store_true', help='Disable sector8 and distance bins')
    args = parser.parse_args()

    nusc = NuScenes(version=args.version, dataroot=args.dataroot, verbose=True)
    
    # 初始化地图和缓存
    nusc_map = None
    map_cache = {}
    if not args.disable_map:
        try:
            # 默认使用singapore-onenorth，实际应该根据场景动态选择
            nusc_map = NuScenesMap(dataroot=args.dataroot, map_name='singapore-onenorth')
            print(f"地图加载成功: singapore-onenorth")
        except Exception as e:
            print(f"地图加载失败: {e}")
    
    count_scenes = 0
    total_samples = 0
    processed_samples = 0
    
    # 统计总数
    for scene in nusc.scene:
        if args.first_n_scenes is not None and count_scenes >= args.first_n_scenes:
            break
        total_samples += scene['nbr_samples']
        count_scenes += 1
    
    count_scenes = 0
    with open(args.out_path, 'w', encoding='utf-8') as f:
        for scene in nusc.scene:
            if args.first_n_scenes is not None and count_scenes >= args.first_n_scenes:
                break
            
            print(f"处理场景 {count_scenes + 1}: {scene['name']} ({scene['nbr_samples']}帧)")
            sample_token = scene['first_sample_token']
            
            while sample_token:
                g = build_scene_graph_for_sample(
                    nusc,
                    sample_token,
                    nusc_map=nusc_map,
                    compute_bins=(not args.disable_bins),
                    graph_radius=args.graph_radius,
                    min_closing_speed=args.min_closing_speed,
                    min_ttc_dist=args.min_ttc_dist,
                    map_cache=map_cache
                )
                f.write(json.dumps(g) + '\n')
                
                processed_samples += 1
                if processed_samples % 50 == 0:
                    progress = processed_samples / total_samples * 100
                    cache_size = len(map_cache)
                    print(f"  进度: {processed_samples}/{total_samples} ({progress:.1f}%) | 缓存: {cache_size}个位置")
                
                sample = nusc.get('sample', sample_token)
                sample_token = sample['next']
            count_scenes += 1
    
    print(f'\n完成! 处理了 {processed_samples} 帧，保存到 {args.out_path}')
    print(f'地图缓存命中: {len(map_cache)} 个位置')


if __name__ == '__main__':
    main()
