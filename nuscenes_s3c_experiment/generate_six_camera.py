"""
生成单场景的六相机图
"""
import os
import sys
import matplotlib.pyplot as plt

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

from nuscenes.nuscenes import NuScenes
from PIL import Image
import config


def setup_matplotlib():
    """设置matplotlib中文显示"""
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False


def generate_six_camera_view(nusc, sample_token, output_dir):
    """
    生成六相机图
    """
    print("生成六相机图...")
    
    sample = nusc.get('sample', sample_token)
    
    # 六个相机的顺序（按环绕顺序）
    camera_channels = [
        'CAM_FRONT_LEFT',
        'CAM_FRONT',
        'CAM_FRONT_RIGHT',
        'CAM_BACK_LEFT',
        'CAM_BACK',
        'CAM_BACK_RIGHT'
    ]
    
    # 中文名称
    camera_names = [
        '前左相机',
        '前相机',
        '前右相机',
        '后左相机',
        '后相机',
        '后右相机'
    ]
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('NuScenes 六相机环视图 (Scene-0061)', fontsize=18, fontweight='bold')
    
    for idx, (cam_channel, cam_name) in enumerate(zip(camera_channels, camera_names)):
        row = idx // 3
        col = idx % 3
        ax = axes[row, col]
        
        # 获取相机数据
        cam_token = sample['data'][cam_channel]
        cam_data = nusc.get('sample_data', cam_token)
        
        # 读取图像
        img_path = os.path.join(nusc.dataroot, cam_data['filename'])
        img = Image.open(img_path)
        
        # 显示图像
        ax.imshow(img)
        ax.set_title(f'{cam_name}\n({cam_channel})', fontsize=12, fontweight='bold')
        ax.axis('off')
    
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'six_camera_view.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 六相机图已保存: {output_path}")
    return output_path


def main():
    """主函数"""
    setup_matplotlib()
    
    print("=" * 60)
    print("  生成六相机环视图")
    print("=" * 60)
    
    # 创建输出目录
    output_dir = os.path.join(config.OUTPUT_DIR, 'single_scene_demo')
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化NuScenes
    print("\n初始化NuScenes...")
    nusc = NuScenes(version='v1.0-mini', dataroot=config.NUSCENES_DATAROOT, verbose=False)
    
    # 使用第一个场景（scene-0061）
    scene = nusc.scene[0]
    sample_token = scene['first_sample_token']
    
    print(f"场景: {scene['name']}")
    print(f"描述: {scene['description']}")
    
    # 生成六相机图
    output_path = generate_six_camera_view(nusc, sample_token, output_dir)
    
    print("\n" + "=" * 60)
    print(f"✓ 完成！图片保存在: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
