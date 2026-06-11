"""
单场景Neo4j导入脚本（改进版）

改进内容：
1. 批量导入提升性能
2. 完善的事务管理
3. 细致的错误处理和重试机制
4. 配置文件/环境变量支持
5. 数据验证
6. 代码复用和优化
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from contextlib import contextmanager
from dataclasses import dataclass
import logging
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Neo4jConfig:
    """Neo4j连接配置"""
    uri: str
    user: str
    password: str
    batch_size: int = 500  # 批量导入大小
    max_retry: int = 3      # 最大重试次数
    
    @classmethod
    def from_env(cls) -> 'Neo4jConfig':
        """从环境变量加载配置"""
        return cls(
            uri=os.getenv('NEO4J_URI', 'bolt://localhost:7600'),
            user=os.getenv('NEO4J_USER', 'neo4j'),
            password=os.getenv('NEO4J_PASSWORD', '87017563'),
            batch_size=int(os.getenv('NEO4J_BATCH_SIZE', '500')),
            max_retry=int(os.getenv('NEO4J_MAX_RETRY', '3'))
        )


class Neo4jImporter:
    """Neo4j导入器"""
    
    def __init__(self, config: Neo4jConfig):
        """初始化Neo4j连接"""
        self.config = config
        self.driver = None
        self._connect()
    
    def _connect(self):
        """建立连接"""
        try:
            self.driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password),
                max_connection_lifetime=3600
            )
            # 验证连接
            self.driver.verify_connectivity()
            logger.info(f"✓ 已连接到Neo4j: {self.config.uri}")
        except ServiceUnavailable as e:
            logger.error(f"✗ 无法连接到Neo4j: {e}")
            raise
    
    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()
            logger.info("✓ 连接已关闭")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
    
    @contextmanager
    def _session(self):
        """会话上下文管理器"""
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def _execute_with_retry(self, query: str, parameters: Dict = None, retry_count: int = 0):
        """带重试的查询执行"""
        try:
            with self._session() as session:
                return session.run(query, parameters or {})
        except (ServiceUnavailable, SessionExpired) as e:
            if retry_count < self.config.max_retry:
                logger.warning(f"查询失败，重试 {retry_count + 1}/{self.config.max_retry}: {e}")
                return self._execute_with_retry(query, parameters, retry_count + 1)
            else:
                logger.error(f"查询失败，已达最大重试次数: {e}")
                raise
    
    def clear_database(self):
        """清空数据库"""
        logger.info("清空数据库...")
        
        # 分批删除（避免内存问题）
        with self._session() as session:
            while True:
                result = session.run("""
                    MATCH (n)
                    WITH n LIMIT 10000
                    DETACH DELETE n
                    RETURN count(n) as deleted
                """)
                deleted = result.single()['deleted']
                if deleted == 0:
                    break
                logger.info(f"  已删除 {deleted} 个节点")
        
        logger.info("✓ 数据库已清空")
    
    def create_schema(self):
        """创建约束和索引"""
        logger.info("创建数据库约束和索引...")
        
        with self._session() as session:
            # 唯一约束
            constraints = [
                "CREATE CONSTRAINT object_unique_id IF NOT EXISTS FOR (obj:Object) REQUIRE obj.unique_id IS UNIQUE"
            ]
            
            # 索引
            indexes = [
                "CREATE INDEX object_type IF NOT EXISTS FOR (obj:Object) ON (obj.type)",
                "CREATE INDEX object_category IF NOT EXISTS FOR (obj:Object) ON (obj.category)",
                "CREATE INDEX object_is_ego IF NOT EXISTS FOR (obj:Object) ON (obj.is_ego)",
                "CREATE INDEX relationship_distance IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.distance)"
            ]
            
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"  ✓ 约束已创建")
                except Exception as e:
                    logger.warning(f"  约束创建跳过: {e}")
            
            for index in indexes:
                try:
                    session.run(index)
                    logger.info(f"  ✓ 索引已创建")
                except Exception as e:
                    logger.warning(f"  索引创建跳过: {e}")
    
    def validate_scene_graph(self, scene_graph: Dict) -> bool:
        """验证场景图数据完整性"""
        logger.info("验证场景图数据...")
        
        errors = []
        
        # 检查必要字段
        if 'scene_name' not in scene_graph:
            errors.append("缺少 'scene_name' 字段")
        
        objects = scene_graph.get('objects') or scene_graph.get('nodes', [])
        relationships = scene_graph.get('relationships') or scene_graph.get('edges', [])
        
        if not objects:
            errors.append("对象列表为空")
        
        # 检查对象数据
        object_ids = set()
        for i, obj in enumerate(objects):
            if 'unique_id' not in obj:
                errors.append(f"对象 {i} 缺少 'unique_id'")
            else:
                if obj['unique_id'] in object_ids:
                    errors.append(f"重复的 unique_id: {obj['unique_id']}")
                object_ids.add(obj['unique_id'])
            
            if 'type' not in obj:
                errors.append(f"对象 {obj.get('unique_id', i)} 缺少 'type'")
        
        # 检查关系数据
        for i, rel in enumerate(relationships):
            if 'source' not in rel:
                errors.append(f"关系 {i} 缺少 'source'")
            elif rel['source'] not in object_ids:
                errors.append(f"关系 {i} 的 source '{rel['source']}' 不存在")
            
            if 'target' not in rel:
                errors.append(f"关系 {i} 缺少 'target'")
            elif rel['target'] not in object_ids:
                errors.append(f"关系 {i} 的 target '{rel['target']}' 不存在")
        
        if errors:
            logger.error("✗ 数据验证失败:")
            for error in errors[:10]:  # 只显示前10个错误
                logger.error(f"  - {error}")
            if len(errors) > 10:
                logger.error(f"  ... 还有 {len(errors) - 10} 个错误")
            return False
        
        logger.info("✓ 数据验证通过")
        return True
    
    @staticmethod
    def _extract_node_properties(obj: Dict) -> Dict[str, Any]:
        """提取节点属性（避免代码重复）"""
        props = {
            'unique_id': obj['unique_id'],
            'type': obj['type'],
        }
        
        # 辅助函数：处理向量数据
        def add_vector(key_prefix: str, data: Any):
            if data is None:
                return
            
            if isinstance(data, dict):
                if 'x' in data:
                    props[f'{key_prefix}_x'] = data['x']
                    props[f'{key_prefix}_y'] = data['y']
                    props[f'{key_prefix}_z'] = data['z']
                elif 'width' in data:
                    props[f'{key_prefix}_width'] = data['width']
                    props[f'{key_prefix}_length'] = data['length']
                    props[f'{key_prefix}_height'] = data['height']
                elif 'vx' in data:
                    props[f'{key_prefix}_vx'] = data['vx']
                    props[f'{key_prefix}_vy'] = data['vy']
                    props[f'{key_prefix}_vz'] = data['vz']
            elif isinstance(data, (list, tuple)) and len(data) == 3:
                if key_prefix == 'size':
                    props[f'{key_prefix}_width'] = data[0]
                    props[f'{key_prefix}_length'] = data[1]
                    props[f'{key_prefix}_height'] = data[2]
                elif key_prefix == 'velocity':
                    props[f'{key_prefix}_vx'] = data[0]
                    props[f'{key_prefix}_vy'] = data[1]
                    props[f'{key_prefix}_vz'] = data[2]
                else:
                    props[f'{key_prefix}_x'] = data[0]
                    props[f'{key_prefix}_y'] = data[1]
                    props[f'{key_prefix}_z'] = data[2]
        
        # 添加位置、尺寸、速度
        add_vector('translation', obj.get('translation'))
        add_vector('size', obj.get('size'))
        add_vector('velocity', obj.get('velocity'))
        
        # 添加简单属性
        simple_fields = ['category', 'num_lidar_pts', 'is_ego', 'status']
        for field in simple_fields:
            if field in obj:
                props[field] = obj[field]
        
        # 处理列表属性
        if 'attributes' in obj and obj['attributes']:
            props['attributes'] = ','.join(str(attr) for attr in obj['attributes'])
        
        return props
    
    @staticmethod
    def _extract_relationship_properties(rel: Dict) -> Dict[str, Any]:
        """提取关系属性（支持双坐标系）"""
        props = {}
        
        # 基本属性
        if 'predicates' in rel:
            props['predicates'] = rel['predicates']
        
        # metrics字段
        if 'metrics' in rel:
            metrics = rel['metrics']
            
            # 距离
            if 'distance' in metrics:
                props['distance'] = metrics['distance']
            
            # --- Source Frame 数据 ---
            if 'angle_source' in metrics:
                props['angle_source'] = metrics['angle_source']
            
            if 'direction_source' in metrics:
                dir_source = metrics['direction_source']
                if isinstance(dir_source, dict):
                    if 'direction_8' in dir_source:
                        props['direction_8_source'] = dir_source['direction_8']
                    if 'angle_matches' in dir_source:
                        props['angle_matches_source'] = dir_source['angle_matches']
            
            if 'relative_position_source' in metrics:
                rel_pos = metrics['relative_position_source']
                props['relative_x_source'] = rel_pos.get('x', rel_pos[0] if isinstance(rel_pos, list) else 0)
                props['relative_y_source'] = rel_pos.get('y', rel_pos[1] if isinstance(rel_pos, list) else 0)
                props['relative_z_source'] = rel_pos.get('z', rel_pos[2] if isinstance(rel_pos, list) else 0)
            
            # --- Ego Frame 数据 ---
            if 'angle_ego' in metrics:
                props['angle_ego'] = metrics['angle_ego']
            
            if 'direction_ego' in metrics:
                dir_ego = metrics['direction_ego']
                if isinstance(dir_ego, dict):
                    if 'direction_8' in dir_ego:
                        props['direction_8_ego'] = dir_ego['direction_8']
                    if 'angle_matches' in dir_ego:
                        props['angle_matches_ego'] = dir_ego['angle_matches']
            
            if 'relative_position_ego' in metrics:
                rel_pos = metrics['relative_position_ego']
                props['relative_x_ego'] = rel_pos.get('x', rel_pos[0] if isinstance(rel_pos, list) else 0)
                props['relative_y_ego'] = rel_pos.get('y', rel_pos[1] if isinstance(rel_pos, list) else 0)
                props['relative_z_ego'] = rel_pos.get('z', rel_pos[2] if isinstance(rel_pos, list) else 0)
            
            # --- 兼容旧版数据格式 ---
            # 旧版未区分坐标系的angle和relative_position
            if 'angle' in metrics and 'angle_source' not in metrics:
                props['angle'] = metrics['angle']
            
            if 'relative_position' in metrics and 'relative_position_source' not in metrics:
                rel_pos = metrics['relative_position']
                props['relative_x'] = rel_pos.get('x', rel_pos[0] if isinstance(rel_pos, list) else 0)
                props['relative_y'] = rel_pos.get('y', rel_pos[1] if isinstance(rel_pos, list) else 0)
                props['relative_z'] = rel_pos.get('z', rel_pos[2] if isinstance(rel_pos, list) else 0)
        
        # 方向字段（兼容旧版）
        if 'direction_4' in rel and rel['direction_4']:
            props['direction_4'] = rel['direction_4']
        if 'direction_8' in rel and rel['direction_8']:
            props['direction_8'] = rel['direction_8']
        
        return props
    
    def import_scene(self, scene_graph: Dict):
        """导入场景图数据（批量优化版）"""
        logger.info(f"开始导入场景: {scene_graph['scene_name']}")
        
        # 验证数据
        if not self.validate_scene_graph(scene_graph):
            raise ValueError("场景图数据验证失败")
        
        objects = scene_graph.get('objects') or scene_graph.get('nodes', [])
        relationships = scene_graph.get('relationships') or scene_graph.get('edges', [])
        
        # 1. 批量创建节点
        logger.info(f"创建 {len(objects)} 个对象节点...")
        self._import_nodes_batch(objects)
        
        # 2. 批量创建关系
        logger.info(f"创建 {len(relationships)} 条关系...")
        self._import_relationships_batch(relationships)
        
        logger.info("✓ 场景导入完成")
    
    def _import_nodes_batch(self, objects: List[Dict]):
        """批量导入节点"""
        batch_size = self.config.batch_size
        total = len(objects)
        
        with self._session() as session:
            for i in range(0, total, batch_size):
                batch = objects[i:i + batch_size]
                batch_props = [self._extract_node_properties(obj) for obj in batch]
                
                # 使用UNWIND批量创建
                session.run(
                    """
                    UNWIND $batch as props
                    CREATE (obj:Object)
                    SET obj = props
                    """,
                    batch=batch_props
                )
                
                processed = min(i + batch_size, total)
                logger.info(f"  已创建 {processed}/{total} 个节点")
        
        logger.info(f"✓ 已创建 {total} 个对象节点")
    
    def _import_relationships_batch(self, relationships: List[Dict]):
        """批量导入关系"""
        batch_size = self.config.batch_size
        total = len(relationships)
        
        with self._session() as session:
            for i in range(0, total, batch_size):
                batch = relationships[i:i + batch_size]
                
                # 准备批量数据
                batch_data = []
                for rel in batch:
                    batch_data.append({
                        'source': rel['source'],
                        'target': rel['target'],
                        'props': self._extract_relationship_properties(rel)
                    })
                
                # 使用UNWIND批量创建关系
                session.run(
                    """
                    UNWIND $batch as item
                    MATCH (a:Object {unique_id: item.source})
                    MATCH (b:Object {unique_id: item.target})
                    CREATE (a)-[r:RELATES_TO]->(b)
                    SET r = item.props
                    """,
                    batch=batch_data
                )
                
                processed = min(i + batch_size, total)
                logger.info(f"  已创建 {processed}/{total} 条关系")
        
        logger.info(f"✓ 已创建 {total} 条关系")
    
    def verify_import(self):
        """验证导入结果"""
        logger.info("验证导入结果...")
        
        with self._session() as session:
            # 统计节点数
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            logger.info(f"  对象节点数: {node_count}")
            
            # 统计关系数
            result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            rel_count = result.single()['count']
            logger.info(f"  关系数: {rel_count}")
            
            # 显示对象类型分布
            result = session.run("""
                MATCH (n:Object) 
                RETURN n.type as type, count(*) as count 
                ORDER BY count DESC
                LIMIT 10
            """)
            logger.info("\n  对象类型分布（Top 10）:")
            for record in result:
                logger.info(f"    {record['type']}: {record['count']}")
            
            # 检查ego车
            result = session.run("MATCH (ego:Object {unique_id: 'ego'}) RETURN ego")
            if result.single():
                # 显示ego周围最近的对象
                result = session.run("""
                    MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
                    RETURN obj.unique_id as id, obj.type as type, r.distance as distance
                    ORDER BY r.distance ASC
                    LIMIT 5
                """)
                logger.info("\n  Ego车周围最近的5个对象:")
                for record in result:
                    logger.info(f"    {record['id']} ({record['type']}): {record['distance']:.2f}m")
            else:
                logger.warning("  未找到Ego车节点")


def load_scene_graph(data_path: Path) -> Dict:
    """加载场景图数据"""
    if not data_path.exists():
        raise FileNotFoundError(f"找不到场景图数据文件: {data_path}")
    
    logger.info(f"加载场景图数据: {data_path}")
    with open(data_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    logger.info(f"✓ 已加载场景: {scene_graph.get('scene_name', 'Unknown')}")
    
    objects = scene_graph.get('objects') or scene_graph.get('nodes', [])
    relationships = scene_graph.get('relationships') or scene_graph.get('edges', [])
    
    logger.info(f"  对象数: {len(objects)}")
    logger.info(f"  关系数: {len(relationships)}")
    
    return scene_graph


def print_usage_guide():
    """打印使用指南"""
    logger.info("\n" + "=" * 70)
    logger.info("✓ 导入完成！")
    logger.info("\n下一步：")
    logger.info("  1. 打开Neo4j Browser: http://localhost:7474")
    logger.info("  2. 执行查询示例（见下方）")
    logger.info("\n查询示例：")
    logger.info("  # 查看所有对象")
    logger.info("  MATCH (n:Object) RETURN n LIMIT 25")
    logger.info("")
    logger.info("  # 查看ego周围的对象")
    logger.info("  MATCH (ego:Object {unique_id: 'ego'})-[r]->(obj)")
    logger.info("  RETURN ego, r, obj")
    logger.info("")
    logger.info("  # 按距离查找附近对象")
    logger.info("  MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj)")
    logger.info("  WHERE r.distance < 10")
    logger.info("  RETURN obj.type, obj.unique_id, r.distance")
    logger.info("  ORDER BY r.distance")
    logger.info("")
    logger.info("  # 查找特定类型的对象")
    logger.info("  MATCH (n:Object) WHERE n.type = 'car'")
    logger.info("  RETURN n LIMIT 10")
    logger.info("=" * 70)


def main():
    """主函数"""
    print("=" * 70)
    print("  单场景Neo4j导入（改进版）")
    print("=" * 70)
    print()
    
    try:
        # 加载场景图数据
        data_path = Path('output/single_scene_demo/single_scene_full_graph.json')
        scene_graph = load_scene_graph(data_path)
        
        # 加载配置
        config = Neo4jConfig.from_env()
        logger.info(f"Neo4j URI: {config.uri}")
        logger.info(f"批量大小: {config.batch_size}")
        
        # 使用上下文管理器确保连接关闭
        with Neo4jImporter(config) as importer:
            # 清空数据库
            importer.clear_database()
            
            # 创建约束和索引
            importer.create_schema()
            
            # 导入场景
            importer.import_scene(scene_graph)
            
            # 验证导入
            importer.verify_import()
        
        # 打印使用指南
        print_usage_guide()
        
    except FileNotFoundError as e:
        logger.error(f"✗ {e}")
        logger.error("  请先运行 single_scene_demo.py 生成数据")
    except ServiceUnavailable as e:
        logger.error(f"✗ 无法连接到Neo4j: {e}")
        logger.error("\n请确保：")
        logger.error("  1. Neo4j服务正在运行")
        logger.error("  2. 连接信息正确（检查环境变量或默认值）")
        logger.error("  3. 已安装neo4j Python驱动: pip install neo4j")
    except Exception as e:
        logger.error(f"✗ 导入失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
