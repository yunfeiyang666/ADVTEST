"""
Neo4j客户端 - 执行Cypher查询
"""
import json
import logging
from typing import Optional, Dict, Any, List
from neo4j import GraphDatabase, Driver, Session
from neo4j.graph import Node, Relationship

from . import config

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j数据库客户端
    
    支持上下文管理器：
        with Neo4jClient() as client:
            result = client.execute_query("MATCH (n) RETURN n LIMIT 10")
    """
    
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri = uri or config.NEO4J_URI
        self.user = user or config.NEO4J_USER
        self.password = password or config.NEO4J_PASSWORD
        self.driver: Optional[Driver] = None
        self._connected: bool = False
    
    def __enter__(self) -> 'Neo4jClient':
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
        
    def connect(self) -> bool:
        """建立数据库连接
        
        Returns:
            True if connection successful, False otherwise
        
        Raises:
            ConnectionError: If connection fails and raise_on_error is True
        """
        if self._connected and self.driver:
            return True
            
        try:
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password)
            )
            # 测试连接 - 实际验证连接是否可用
            with self.driver.session() as session:
                result = session.run("RETURN 1 AS test")
                record = result.single()
                if record is None or record["test"] != 1:
                    raise ConnectionError("Connection test failed")
            
            self._connected = True
            logger.info(f"Neo4j connected: {self.uri}")
            return True
            
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            self._connected = False
            self.driver = None
            return False
    
    def close(self) -> None:
        """关闭连接"""
        if self.driver:
            try:
                self.driver.close()
            except Exception as e:
                logger.warning(f"Error closing Neo4j connection: {e}")
            finally:
                self.driver = None
                self._connected = False
    
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self.driver is not None
            
    def execute_query(self, cypher: str) -> Dict[str, Any]:
        """
        执行Cypher查询
        
        Args:
            cypher: Cypher查询语句
            
        Returns:
            查询结果字典，包含 success, count, data, error(可选) 字段
        """
        # Auto-connect if not connected
        if not self.is_connected():
            if not self.connect():
                return {
                    "success": False,
                    "error": "Failed to connect to Neo4j",
                    "count": 0,
                    "data": []
                }
            
        try:
            with self.driver.session() as session:
                result = session.run(cypher)
                records = list(result)
                
                # 转换为可序列化的格式
                data = []
                for record in records:
                    row = {}
                    for key in record.keys():
                        value = record[key]
                        row[key] = self._convert_value(value)
                    data.append(row)
                
                return {
                    "success": True,
                    "count": len(data),
                    "data": data
                }
                
        except Exception as e:
            logger.error(f"Cypher query failed: {e}")
            logger.debug(f"Failed query: {cypher}")
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "data": []
            }
    
    def _convert_value(self, value: Any) -> Any:
        """将Neo4j类型转换为Python基本类型
        
        Args:
            value: Neo4j value to convert
            
        Returns:
            Python-native equivalent
        """
        if value is None:
            return None
        elif isinstance(value, (int, float, str, bool)):
            return value
        elif isinstance(value, list):
            return [self._convert_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._convert_value(v) for k, v in value.items()}
        elif isinstance(value, Node):
            # Neo4j Node - extract properties and add metadata
            node_dict = dict(value.items())
            node_dict["_labels"] = list(value.labels)
            node_dict["_id"] = value.element_id if hasattr(value, 'element_id') else value.id
            return node_dict
        elif isinstance(value, Relationship):
            # Neo4j Relationship - extract properties and add metadata
            rel_dict = dict(value.items())
            rel_dict["_type"] = value.type
            rel_dict["_id"] = value.element_id if hasattr(value, 'element_id') else value.id
            return rel_dict
        elif hasattr(value, 'items'):
            # Generic mapping type
            return {k: self._convert_value(v) for k, v in value.items()}
        elif hasattr(value, '__iter__'):
            # Generic iterable
            return [self._convert_value(v) for v in value]
        else:
            # Fallback to string representation
            return str(value)
    
    def get_result_as_json(self, cypher: str, indent: int = 2) -> str:
        """执行查询并返回JSON字符串
        
        Args:
            cypher: Cypher query to execute
            indent: JSON indentation level (default 2)
            
        Returns:
            JSON string of query result
        """
        result = self.execute_query(cypher)
        return json.dumps(result, ensure_ascii=False, indent=indent)
    
    def get_scene_summary(self) -> str:
        """获取当前场景的统计信息（简化版，不输出所有对象）
        
        Returns:
            场景统计字符串，只包含对象类型和数量
        """
        if not self.is_connected():
            if not self.connect():
                return "[无法获取场景信息: Neo4j未连接]"
        
        summary_parts = []
        
        # 获取对象类型统计
        stats_query = """
        MATCH (n:Object)
        RETURN n.type AS type, count(n) AS count
        ORDER BY count DESC, type
        """
        stats_result = self.execute_query(stats_query)
        
        if stats_result["success"] and stats_result["data"]:
            summary_parts.append("场景对象统计:")
            for row in stats_result["data"]:
                obj_type = row.get("type", "unknown")
                count = row.get("count", 0)
                summary_parts.append(f"  - {obj_type}: {count}个")
        
        # 获取ego周围对象方位统计
        ego_stats_query = """
        MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
        WITH r.direction_4 AS dir4, count(obj) AS count
        RETURN dir4, count
        ORDER BY dir4
        """
        ego_result = self.execute_query(ego_stats_query)
        
        if ego_result["success"] and ego_result["data"]:
            summary_parts.append("")
            summary_parts.append("ego周围对象方位分布:")
            for row in ego_result["data"]:
                direction = row.get("dir4", "unknown")
                count = row.get("count", 0)
                summary_parts.append(f"  - {direction}: {count}个")
        
        if not summary_parts:
            return "[场景为空或查询失败]"
        
        return "\n".join(summary_parts)


def test_connection() -> bool:
    """测试Neo4j连接
    
    Returns:
        True if connection and test query successful
    """
    # Use context manager to ensure proper cleanup
    with Neo4jClient() as client:
        if not client.is_connected():
            print("✗ Neo4j连接失败")
            return False
        
        print(f"✓ Neo4j连接成功: {client.uri}")
        
        # Test query
        result = client.execute_query("MATCH (n:Object) RETURN count(n) as count")
        if result["success"] and result["data"]:
            count = result["data"][0].get("count", "N/A")
            print(f"  对象数量: {count}")
            return True
        else:
            print(f"  查询失败: {result.get('error', 'Unknown error')}")
            return False


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_connection()
