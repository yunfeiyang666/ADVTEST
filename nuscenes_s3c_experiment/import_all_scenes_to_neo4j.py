#!/usr/bin/env python
"""批量导入所有场景到Neo4j"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig, logger

def main():
    # 加载所有场景图
    data_path = Path('output/scene_graphs/all_scene_graphs_full_relation.json')
    print(f"Loading scene graphs from {data_path}...")
    
    with open(data_path, 'r', encoding='utf-8') as f:
        all_scenes = json.load(f)
    
    print(f"Found {len(all_scenes)} scenes to import")
    
    # 连接Neo4j
    config = Neo4jConfig.from_env()
    print(f"\nConnecting to Neo4j at {config.uri}...")
    
    with Neo4jImporter(config) as importer:
        # 清空数据库
        print("\n[Step 1/4] Clearing database...")
        importer.clear_database()
        
        # 创建schema
        print("\n[Step 2/4] Creating schema...")
        importer.create_schema()
        
        # 批量导入所有场景
        print("\n[Step 3/4] Importing all scenes...")
        total_objects = 0
        total_relationships = 0
        
        for i, scene in enumerate(all_scenes):
            scene_name = scene['scene_name']
            num_objects = len(scene['objects'])
            num_rels = len(scene['relationships'])
            
            print(f"\n  [{i+1}/{len(all_scenes)}] Importing {scene_name}...")
            print(f"       Objects: {num_objects}, Relationships: {num_rels}")
            
            # 为每个场景的对象添加scene_name前缀，避免冲突
            for obj in scene['objects']:
                obj['unique_id'] = f"{scene_name}_{obj['unique_id']}"
                obj['scene_name'] = scene_name
            
            for rel in scene['relationships']:
                rel['source'] = f"{scene_name}_{rel['source']}"
                rel['target'] = f"{scene_name}_{rel['target']}"
            
            # 导入（跳过验证和日志，提高速度）
            importer._import_nodes_batch(scene['objects'])
            importer._import_relationships_batch(scene['relationships'])
            
            total_objects += num_objects
            total_relationships += num_rels
        
        print(f"\n[Step 4/4] Verifying import...")
        importer.verify_import()
        
        print("\n" + "="*60)
        print("✓ All scenes imported successfully!")
        print(f"  Total scenes: {len(all_scenes)}")
        print(f"  Total objects: {total_objects}")
        print(f"  Total relationships: {total_relationships}")
        print("="*60)

if __name__ == "__main__":
    main()
