#!/usr/bin/env python3

import argparse
import json
import math
import numpy as np
from pyquaternion import Quaternion

try:
    from nuscenes.nuscenes import NuScenes
    from nuscenes.utils.data_classes import Box
    from nuscenes.map_expansion.map_api import NuScenesMap
except ImportError:
    from nuscenes.nuscenes import NuScenes
    from nuscenes.utils.data_classes import Box
    from nuscenes.map_expansion.map_api import NuScenesMap


def T_from_qt(q, t):
    T = np.eye(4)
    T[:3, :3] = Quaternion(q).rotation_matrix
    T[:3, 3] = t
    return T


def world_to_ego(p_w, R_ge, t_ge):
    return R_ge.T @ (p_w - t_ge)


def yaw_from_q(q):
    return math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] * q[2] + q[3] * q[3]))


def central_diff(p_p, t_p, p_n, t_n):
    dt = t_n - t_p
    if dt < 1e-6:
        return np.zeros(3)
    return (p_n - p_p) / dt


def get_sample_ego_T(nusc, sample_token):
    s = nusc.get('sample', sample_token)
    sd_lidar = nusc.get('sample_data', s['data']['LIDAR_TOP'])
    cs_lidar = nusc.get('calibrated_sensor', sd_lidar['calibrated_sensor_token'])
    ep = nusc.get('ego_pose', sd_lidar['ego_pose_token'])
    
    T_ego_lidar = T_from_qt(cs_lidar['rotation'], cs_lidar['translation'])
    T_global_ego = T_from_qt(ep['rotation'], ep['translation'])
    T_ge = T_global_ego @ T_ego_lidar
    
    R_ge = T_ge[:3, :3]
    t_ge = T_ge[:3, 3]
    
    return T_ge, R_ge, t_ge, sd_lidar['timestamp']


def classify_sector8(bearing_rad):
    ang = ((bearing_rad + math.pi) % (2 * math.pi)) - math.pi
    boundaries = [-7*math.pi/8, -5*math.pi/8, -3*math.pi/8, -math.pi/8, math.pi/8, 3*math.pi/8, 5*math.pi/8, 7*math.pi/8]
    names = ['back-right', 'right', 'front-right', 'front', 'front-left', 'left', 'back-left', 'back']
    for b, name in zip(boundaries, names):
        if ang <= b:
            return name
    return 'back'


def classify_s3c_angular(bearing_rad):
    """S3C风格的4象限角度分类"""
    angle_deg = math.degrees(bearing_rad)
    angle_deg = (angle_deg + 360) % 360
    
    if 315 <= angle_deg or angle_deg < 45: return "direct_front"
    elif 45 <= angle_deg < 135: return "side_front" 
    elif 135 <= angle_deg < 225: return "direct_rear"
    else: return "side_rear"


def distance_bin(d):
    if d < 2.0: return 'very_close'
    if d < 10.0: return 'close'
    if d < 30.0: return 'medium'
    return 'far'


def s3c_distance_bin(d):
    """S3C风格的距离分档"""
    if d < 2.0: return "safe_hazard"
    elif d < 4.0: return "near_coll"
    elif d < 7.0: return "super_near"
    elif d < 10.0: return "very_near"
    elif d < 16.0: return "near"
    elif d < 25.0: return "visible"
    elif d < 50.0: return "far"
    else: return None


def parse_attributes(nusc, ann):
    result = {
        'moving': None, 'standing': None, 'stopped': None,
        'parked': None, 'with_rider': None, 'without_rider': None,
    }
    for atok in ann.get('attribute_tokens', []) or []:
        attr = nusc.get('attribute', atok)
        name = attr['name']
        if 'moving' in name: result['moving'] = True
        elif 'standing' in name: result['standing'] = True
        elif 'stopped' in name: result['stopped'] = True
        elif 'parked' in name: result['parked'] = True
        elif 'with_rider' in name: result['with_rider'] = True
        elif 'without_rider' in name: result['without_rider'] = True
    return result


def est_inst_state(nusc, ann):
    p_c = np.asarray(ann['translation'], dtype=float)
    t_c = ann.get('timestamp', 0) / 1e6
    v_w = np.zeros(3)
    a_w = np.zeros(3)
    
    if ann['prev'] and ann['next']:
        ap = nusc.get('sample_annotation', ann['prev'])
        an = nusc.get('sample_annotation', ann['next'])
        p_p = np.asarray(ap['translation'], dtype=float)
        p_n = np.asarray(an['translation'], dtype=float)
        t_p = ap.get('timestamp', 0) / 1e6
        t_n = an.get('timestamp', 0) / 1e6
        v_w = central_diff(p_p, t_p, p_n, t_n)
        dt = (t_n - t_p) / 2.0
        a_w = (p_n - 2 * p_c + p_p) / max(1e-6, dt * dt)
    return p_c, t_c, v_w, a_w


def build_scene_graph_for_sample(nusc, sample_token, nusc_map=None, compute_bins=True, 
                                graph_radius=60.0, min_ttc_dist=1.0, min_closing_speed=0.1, map_cache=None):
    T_ge, R_ge, t_ge, ts = get_sample_ego_T(nusc, sample_token)
    
    s = nusc.get('sample', sample_token)
    s_prev = nusc.get('sample', s['prev']) if s['prev'] else None
    s_next = nusc.get('sample', s['next']) if s['next'] else None
    
    def ego_state(sample):
        sd = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
        ep = nusc.get('ego_pose', sd['ego_pose_token'])
        p = np.asarray(ep['translation'], dtype=float)
        v = np.asarray(ep.get('velocity', [0, 0, 0]), dtype=float)
        return p, v
    
    p_ego_w, v_ego_w = ego_state(s)
    w_ego_e = np.zeros(3)
    
    nodes = []
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
        
        # 地图挂接
        on_layer = None
        on_lane_id = None
        in_intersection = None
        if nusc_map is not None:
            try:
                cache_key = f"{p_w[0]:.1f},{p_w[1]:.1f}"
                if map_cache and cache_key in map_cache:
                    cached_result = map_cache[cache_key]
                    on_layer = cached_result['layer']
                    on_lane_id = cached_result['lane_id']
                    in_intersection = cached_result['in_intersection']
                else:
                    lane_tok = nusc_map.record_on_point(float(p_w[0]), float(p_w[1]), 'lane')
                    if lane_tok:
                        on_layer = 'lane'
                        on_lane_id = lane_tok
                        in_intersection = False
                    else:
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
                        
                        if on_lane_id is None:
                            lane_closest = nusc_map.get_closest_lane(float(p_w[0]), float(p_w[1]), radius=10.0)
                            if lane_closest:
                                on_layer = 'lane'
                                on_lane_id = lane_closest
                                in_intersection = False
                    
                    if map_cache is not None:
                        map_cache[cache_key] = {
                            'layer': on_layer,
                            'lane_id': on_lane_id, 
                            'in_intersection': in_intersection
                        }
            except Exception as e:
                pass
        
        attrs = parse_attributes(nusc, ann)
        
        dist = float(np.linalg.norm(p_e[:2]))
        bearing = math.atan2(p_e[1], p_e[0])
        
        sector8 = classify_sector8(bearing) if compute_bins else None
        dist_bin = distance_bin(dist) if compute_bins else None
        s3c_angular = classify_s3c_angular(bearing) if compute_bins else None
        s3c_distance = s3c_distance_bin(dist) if compute_bins else None
        
        # S3C策略：超过50m的对象不包含在场景图中
        if dist > 50.0:
            continue
        
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
                's3c_angular': s3c_angular,
                's3c_distance': s3c_distance
            }
        })
    
    id_to_node = {n['id']: n for n in nodes}
    ids = [n['id'] for n in nodes]
    
    edges = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            ni = id_to_node[ids[i]]
            nj = id_to_node[ids[j]]
            pi = np.asarray(ni['pose']['ego']['center'], dtype=float)
            pj = np.asarray(nj['pose']['ego']['center'], dtype=float)
            vi = np.asarray(ni['velocity']['ego'], dtype=float)
            vj = np.asarray(nj['velocity']['ego'], dtype=float)
            
            delta = pj - pi
            dist = np.linalg.norm(delta)
            if dist > min(graph_radius, 50.0):
                continue
            
            bearing = math.atan2(delta[1], delta[0])
            rel = vj - vi
            ttc = None
            if dist > min_ttc_dist:
                u = delta / dist
                closing = -float(np.dot(rel, u))
                if closing > min_closing_speed:
                    ttc = dist / closing
            
            phi = abs(bearing)
            if (ni.get('map') and ni['map'].get('in_intersection')) or (nj.get('map') and nj['map'].get('in_intersection')):
                relation_type = 'intersecting'
            else:
                relation_type = 'longitudinal' if (phi <= math.pi/4 or phi >= 3*math.pi/4) else 'lateral'
            
            same_lane = False
            adjacent_lane = False
            if (ni.get('map') and ni['map'].get('on_lane_id') and 
                nj.get('map') and nj['map'].get('on_lane_id')):
                same_lane = (ni['map']['on_lane_id'] == nj['map']['on_lane_id'])
            
            tau_x, tau_y = 0.5, 0.5
            edges.append({
                'from': ids[i],
                'to': ids[j],
                'distance': float(dist),
                'bearing_ego': bearing,
                'front_of': bool(delta[0] > tau_x),
                'left_of': bool(delta[1] > tau_y),
                'ttc': ttc,
                'relation_type': relation_type,
                'same_lane': same_lane,
                'adjacent_lane': adjacent_lane
            })
    
    return {
        'sample_token': sample_token,
        'timestamp': int(ts),
        'prev_sample_token': s['prev'],
        'next_sample_token': s['next'],
        'nodes': nodes,
        'edges': edges
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataroot', type=str, required=True)
    parser.add_argument('--version', type=str, default='v1.0-mini')
    parser.add_argument('--out_path', type=str, default='scene_graph.jsonl')
    parser.add_argument('--graph_radius', type=float, default=60.0)
    parser.add_argument('--first_n_scenes', type=int, default=None)
    parser.add_argument('--disable_map', action='store_true')
    parser.add_argument('--disable_bins', action='store_true')
    args = parser.parse_args()
    
    nusc = NuScenes(version=args.version, dataroot=args.dataroot, verbose=True)
    
    nusc_map = None
    map_cache = {}
    if not args.disable_map:
        try:
            nusc_map = NuScenesMap(dataroot=args.dataroot, map_name='singapore-onenorth')
            print(f"地图加载成功: singapore-onenorth")
        except Exception as e:
            print(f"地图加载失败: {e}")
    
    count_scenes = 0
    total_samples = sum(scene['nbr_samples'] for scene in nusc.scene[:args.first_n_scenes])
    processed_samples = 0
    
    with open(args.out_path, 'w', encoding='utf-8') as f:
        for scene in nusc.scene:
            if args.first_n_scenes is not None and count_scenes >= args.first_n_scenes:
                break
            
            print(f"处理场景 {count_scenes + 1}: {scene['name']} ({scene['nbr_samples']}帧)")
            sample_token = scene['first_sample_token']
            
            while sample_token:
                g = build_scene_graph_for_sample(
                    nusc, sample_token, nusc_map=nusc_map,
                    compute_bins=(not args.disable_bins),
                    graph_radius=args.graph_radius,
                    map_cache=map_cache
                )
                f.write(json.dumps(g) + '\n')
                
                processed_samples += 1
                if processed_samples % 50 == 0:
                    progress = processed_samples / total_samples * 100
                    print(f"  进度: {processed_samples}/{total_samples} ({progress:.1f}%) | 缓存: {len(map_cache)}个位置")
                
                sample = nusc.get('sample', sample_token)
                sample_token = sample['next']
            count_scenes += 1
    
    print(f'\n完成! 处理了 {processed_samples} 帧，保存到 {args.out_path}')
    print(f'地图缓存命中: {len(map_cache)} 个位置')


if __name__ == '__main__':
    main()
