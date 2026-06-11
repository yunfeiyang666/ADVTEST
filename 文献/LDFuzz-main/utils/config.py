kitti = "kitti"
nuscenes = 'nuscenes'

pointpillar = "pointpillar"
pv_rcnn = "pv_rcnn"
second = "second"
pointrcnn = "pointrcnn"

spc = 'spc'
sec = 'sec'
ldfuzz = 'ldfuzz'
error_spc = 'error_spc'
error_sec = 'error_sec'
error_mixed = 'error_mixed'
none = 'none'
lirtest = 'lirtest'

model_data = dict(
    kitti=[pointpillar, pv_rcnn, second, pointrcnn],
    nuscenes=[pointpillar, second],
)

object_level = ['translocate', 'rotation', 'scale', 'insert']
scene_level = ['rain', 'snow', 'fog']

# ---------------------------
'''
|----|----| <-- 70m
| 6  | 5  |
|----|----| <-- 40m
| 4  | 3  |
|----|----| <-- 20m
| 2  | 1  |
|----|----| <-- 0m
^    ^    ^
|    |    |
40m  0m  -40m
'''
# ---------------------------
scene_graph_width_list = [(-40, 0), (0, 40)]
scene_graph_length_list = [(0, 20), (20, 40), (40, 70)]


def get_seed_path(data_name, model_name):
    seed_path = "./__test_seeds/{}_{}".format(data_name, model_name)
    return seed_path


def get_output_base_path(dataset_name, model_name, i=None):
    if i is None:
        output_base_path = "__out/{}_{}".format(dataset_name, model_name)
    else:
        output_base_path = "__out{}/{}_{}".format(i, dataset_name, model_name)
    return output_base_path


def get_output_path(dataset_name, model_name, select, criteria, num=0, i=None):
    output_base_path = get_output_base_path(dataset_name, model_name, i=i)
    output_dir = "{}/{}/{}/{}".format(output_base_path, select, criteria, num)
    return output_dir


def get_model_profile_base_path(data_name, model_name):
    return "./__profile/{}/profiling/{}".format(data_name, model_name)


def get_model_profile_path(data_name, model_name, pickle_name="0_60000"):
    base_path = get_model_profile_base_path(data_name, model_name)
    return "{}/{}.pickle".format(base_path, pickle_name)
