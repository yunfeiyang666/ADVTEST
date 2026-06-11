#!/usr/bin/env python3
"""
Neo4j 自检：在「每条 L1 边都能嵌入某条 2-hop」假设下，查找无法嵌入的边。

用法（official_pipeline 目录，需与 run_method_a 相同 Neo4j 环境变量）:
  python check_l1_embedded_in_l2.py

若最后一条查询返回 0 行，则：对当前库中每条 RELATES_TO，至少满足
  (n)-[r]->(m)-[:RELATES_TO]->(:Object)  或  (:Object)-[:RELATES_TO]->(n)-[r]->(m)
之一（即该边可作为某 2-hop 的第一段或第二段）。
"""
from __future__ import annotations

import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from advtest_env import load_advtest_env

load_advtest_env()

from advtest_paths import NEO4J_PASSWORD as NEO4J_PWD, NEO4J_URI, NEO4J_USER


def main() -> None:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
    try:
        with driver.session() as s:
            c1 = s.run(
                "MATCH (:Object)-[r:RELATES_TO]->(:Object) RETURN count(r) AS c"
            ).single()["c"]
            c2 = s.run(
                """
                MATCH (n:Object)-[:RELATES_TO]->(m:Object)-[:RELATES_TO]->(k:Object)
                WHERE n.unique_id <> k.unique_id
                RETURN count(*) AS c
                """
            ).single()["c"]
            print(f"L1 edge count (RELATES_TO):     {c1}")
            print(f"L2 path count (n!=k 2-hop):    {c2}")

            miss = list(
                s.run(
                    """
                    MATCH (n:Object)-[r:RELATES_TO]->(m:Object)
                    WHERE NOT (n)-[:RELATES_TO]->(m)-[:RELATES_TO]->(:Object)
                      AND NOT (:Object)-[:RELATES_TO]->(n)-[r]->(m)
                    RETURN n.unique_id AS src, m.unique_id AS tgt
                    LIMIT 50
                    """
                )
            )
            print(f"Edges NOT embeddable in any 2-hop (as leg1 or leg2): {len(miss)}")
            for row in miss[:20]:
                print(f"  {row['src']} -> {row['tgt']}")
            if len(miss) > 20:
                print(f"  ... and {len(miss) - 20} more")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
