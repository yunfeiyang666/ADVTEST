"""
Neo4j客户端 - 执行Cypher查询
"""
import json
from neo4j import GraphDatabase

from . import config


class Neo4jClient:
    """Neo4j数据库客户端"""
    
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri = uri or config.NEO4J_URI
        self.user = user or config.NEO4J_USER
        self.password = password or config.NEO4J_PASSWORD
        self.driver = None
        
    def connect(self):
        """建立数据库连接"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password)
            )
            # 测试连接
            with self.driver.session() as session:
                session.run("RETURN 1")
            print(f"✓ Neo4j连接成功: {self.uri}")
            return True
        except Exception as e:
            print(f"✗ Neo4j连接失败: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()
            
    def execute_query(self, cypher: str) -> dict:
        """
        执行Cypher查询
        
        Args:
            cypher: Cypher查询语句
            
        Returns:
            查询结果字典
        """
        if not self.driver:
            self.connect()
            
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
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "data": []
            }
    
    def _convert_value(self, value):
        """将Neo4j类型转换为Python基本类型"""
        if value is None:
            return None
        elif isinstance(value, (int, float, str, bool)):
            return value
        elif isinstance(value, list):
            return [self._convert_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._convert_value(v) for k, v in value.items()}
        elif hasattr(value, '__iter__') and hasattr(value, 'keys'):
            # Node或Relationship
            return dict(value)
        else:
            return str(value)
    
    def get_result_as_json(self, cypher: str) -> str:
        """执行查询并返回JSON字符串"""
        result = self.execute_query(cypher)
        return json.dumps(result, ensure_ascii=False, indent=2)


def test_connection():
    """测试Neo4j连接"""
    client = Neo4jClient()
    if client.connect():
        result = client.execute_query("MATCH (n:Object) RETURN count(n) as count")
        print(f"  对象数量: {result['data'][0]['count']}")
        client.close()
        return True
    return False


if __name__ == "__main__":
    test_connection()
