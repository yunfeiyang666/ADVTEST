import functools

import numpy as np
# from keras.datasets import cifar10, mnist, fashion_mnist

from utils import config, SVNH_DatasetUtil, KITTI_DatasetUtil
from mtest.core.pose_estimulation.road_split import road_split


def imagenet_preprocessing(input_img_data):
    # temp = np.copy(input_img_data)
    # temp = np.float32(temp)
    # qq = preprocess_input(temp)
    raise ValueError(" ")
    # return qq


def mnist_preprocessing(x_test, use_norm=True):
    temp = np.copy(x_test)
    if use_norm:
        temp = temp.astype('float32').reshape(-1, 28, 28, 1)
        temp /= 255
    else:
        temp = temp.reshape(-1, 28, 28, 1)
    return temp


def color_preprocessing(x_test, use_norm=True):
    temp = np.copy(x_test)
    if use_norm:
        temp = temp.astype('float32').reshape(-1, 32, 32, 3)
        temp /= 255
    else:
        temp = temp.reshape(-1, 32, 32, 3)
    return temp


def kitti_preprocessing(args, sample_idx, use_norm=True):
    return


def get_preprocess(data_name, use_norm=True):
    if data_name == config.mnist or data_name == config.fashion:
        processing = mnist_preprocessing
    elif data_name == config.cifar10 or data_name == config.svhn:
        processing = color_preprocessing
    elif data_name == config.iamge_net:
        processing = imagenet_preprocessing
    elif data_name == config.kitti:
        processing = kitti_preprocessing
    else:
        raise ValueError()
    return functools.partial(processing, use_norm=use_norm)


def load_data(data_name, use_norm=True):
    if data_name == config.mnist:
        (x_train, train_label), (x_test, test_label) = mnist.load_data()
    elif data_name == config.fashion:
        (x_train, train_label), (x_test,
                                 test_label) = fashion_mnist.load_data()
    elif data_name == config.cifar10:
        (x_train, train_label), (x_test, test_label) = cifar10.load_data()
        train_label = train_label.reshape(-1)
        test_label = test_label.reshape(-1)
    elif data_name == config.svhn:
        (x_train, y_train), (x_test, y_test) = SVNH_DatasetUtil.load_data()
        train_label = np.argmax(y_train, axis=1)
        test_label = np.argmax(y_test, axis=1)
    else:
        raise ValueError('Please extend the new train data here!')
    # assert x_train.dtype == np.uint8
    # assert x_test.dtype == np.uint8
    # preprocess = get_preprocess(data_name, use_norm=use_norm)
    # x_train = preprocess(x_train)
    # x_test = preprocess(x_test)

    return (x_train, train_label), (x_test, test_label)
