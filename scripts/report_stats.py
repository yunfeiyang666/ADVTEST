import json, os
from collections import Counter
from nuscenes.nuscenes import NuScenes

dataroot = r"E:\\项目\\自动驾驶图像测试\\data\\nuscenes"
qa_root = r"E:\\项目\\自动驾驶图像测试\\NuScenes-QA\\NuScenes-QA-main\\data\\questions"

nusc = NuScenes(version='v1.0-trainval', dataroot=dataroot, verbose=False)

def tbl(name):
    return getattr(nusc, name)

print("--- nuScenes trainval stats ---")
for k in [
    'scene','sample','sample_data','sample_annotation','instance','category',
    'sensor','calibrated_sensor','ego_pose','visibility','log','map']:
    print(f"{k}={len(tbl(k))}")

print("--- NuScenes-QA stats ---")
val_p = os.path.join(qa_root, 'NuScenes_val_questions.json')
train_p = os.path.join(qa_root, 'NuScenes_train_questions.json')
with open(train_p, 'r', encoding='utf-8') as f:
    qt_obj = json.load(f)
    q_train = qt_obj.get('questions', qt_obj)
with open(val_p, 'r', encoding='utf-8') as f:
    qv_obj = json.load(f)
    q_val = qv_obj.get('questions', qv_obj)
print('train_q_count=', len(q_train))
print('val_q_count=', len(q_val))

def dist(items):
    c = Counter(items)
    for k, v in sorted(c.items(), key=lambda x: (str(x[0]))):
        print(f"{k}={v}")

print('group by template_type (val):')
dist([q.get('template_type') for q in q_val])
print('group by num_hop (val):')
dist([q.get('num_hop') for q in q_val])
print('top answers (val) 20:')
for a, cnt in Counter([q.get('answer') for q in q_val]).most_common(20):
    print(f"{a}={cnt}")
print('unique sample_tokens in val:')
print(len(set(q.get('sample_token') for q in q_val)))
