#!/usr/bin/env python
"""测试场景图导入到Neo4j（scene-0103）"""
import json
import sys
from pathlib import Path

# 添加core_pipeline路径
sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig, logger

# 加载scene-0103的场景图
with open('output/scene_graphs/all_scene_graphs_full_relation.json', 'r', encoding='utf-8') as f:
    all_scenes = json.load(f)

scene_103 = None
for sg in all_scenes:
    if sg['scene_name'] == 'scene-0103':
        scene_103 = sg
        break

if scene_103 is None:
    print("Error: scene-0103 not found!")
    sys.exit(1)

print(f"Found scene: {scene_103['scene_name']}")
print(f"Objects: {len(scene_103['objects'])}")
print(f"Relationships: {len(scene_103['relationships'])}")

# 导入到Neo4j
config = Neo4jConfig.from_env()
print(f"\nConnecting to Neo4j at {config.uri}...")

with Neo4jImporter(config) as importer:
    print("\nClearing database...")
    importer.clear_database()
    
    print("\nCreating schema...")
    importer.create_schema()
    
    print("\nImporting scene-0103...")
    importer.import_scene(scene_103)
    
    print("\nVerifying import...")
    importer.verify_import()
    
print("\n✓ Import completed successfully!")
print("\nTest a sample relationship with dual coordinate frames:")
print("MATCH (car1:Object {unique_id: 'car1'})-[r:RELATES_TO]->(p:Object)")
print("WHERE p.type = 'pedestrian'")
print("RETURN car1.unique_id, p.unique_id, r.distance,")
print("       r.angle_source, r.direction_8_source, r.angle_matches_source,")
print("       r.angle_ego, r.direction_8_ego, r.angle_matches_ego")
print("LIMIT 3")
