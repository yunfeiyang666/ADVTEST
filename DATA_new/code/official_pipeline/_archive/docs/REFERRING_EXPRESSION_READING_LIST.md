# Referring Expression / Scene-Graph Question Generation Reading List

本清单用于支撑当前项目中的 L2 gap `a|b|c` 问题生成、候选集约束、唯一指称、coverage footprint 设计。

## 0. 推荐阅读顺序

### 第一优先级：必须读
1. Dale & Reiter (1995) — Incremental Algorithm
2. Krahmer & van Deemter (2012) — REG Survey
3. Krahmer, van Erk & Verleg (2003) — Graph-based REG
4. CLEVR / GQA question generation papers

### 第二优先级：和视觉/空间关系强相关
5. GRE3D / spatial referring expression work
6. Mao et al. (2016) — Visual referring expressions
7. RefCOCO / RefCOCO+ / RefCOCOg

### 第三优先级：扩展理解
8. TUNA challenge / corpus
9. Scene graph based VQA and question generation
10. Pragmatic / overspecified referring expressions

---

## 1. Dale & Reiter (1995)

**Citation**  
Dale, R., & Reiter, E. (1995). *Computational Interpretations of the Gricean Maxims in the Generation of Referring Expressions*. Cognitive Science.

**Keywords**  
referring expression generation; incremental algorithm; distractor set; distinguishing description; attribute selection.

**Why it matters**  
经典 REG 算法。核心是：target object + distractors，按属性优先级逐个加入描述，每加入一个属性就排除一部分 distractors，直到 target 唯一。

**Project relevance**  
极高。对应我们的约束链：`type → direction → reference object → distance rank`。

---

## 2. Krahmer & van Deemter (2012)

**Citation**  
Krahmer, E., & van Deemter, K. (2012). *Computational Generation of Referring Expressions: A Survey*. Computational Linguistics.

**Keywords**  
REG survey; full brevity; incremental algorithm; relational referring expressions; overspecification; graph-based REG.

**Why it matters**  
REG 综述，帮助理解唯一性、自然性、over-specification、关系型描述等核心概念。

**Project relevance**  
极高。我们的任务就是在 scene graph 中生成既自然又唯一的对象/路径描述。

---

## 3. Krahmer, van Erk & Verleg (2003)

**Citation**  
Krahmer, E., van Erk, S., & Verleg, A. (2003). *Graph-Based Generation of Referring Expressions*. Computational Linguistics.

**Keywords**  
graph-based REG; relational descriptions; subgraph; scene graph; distractor graph; target identification.

**Why it matters**  
和本项目最贴合。我们的 L2 gap `a|b|c` 本身就是图结构，问题生成可看成生成一个区分性子图描述。

**Project relevance**  
极高。直接启发 L2 模板族、candidate set、coverage footprint、relational constraints、reference object selection。

---

## 4. van Deemter (2016) 书

**Citation**  
van Deemter, K. (2016). *Computational Models of Referring: A Study in Cognitive Science*. MIT Press.

**Keywords**  
computational models of referring; ambiguity; vagueness; overspecification; relational reference.

**Why it matters**  
系统理解“指称”问题：什么时候描述算唯一，什么时候描述虽然不最短但更自然。

**Project relevance**  
高。尤其有助于判断 `the car near ego` 这类描述为什么可能不可靠。

---

## 5. GRE3D / Spatial Referring Expressions

**Suggested search queries**
```text
GRE3D referring expressions spatial relations Viethen Dale
GRE3D7 corpus referring expressions
spatial referring expression generation 3D scenes
```

**Keywords**  
GRE3D; spatial referring expressions; 3D scene descriptions; landmark objects; relational descriptions.

**Why it matters**  
关注 3D 场景中的空间指称，例如 `the object to the left of the cube`。

**Project relevance**  
高。对应我们的 direction、distance、reference object 选择。

---

## 6. Mao et al. (2016)

**Citation**  
Mao, J., Huang, J., Toshev, A., Camburu, O., Yuille, A., & Murphy, K. (2016). *Generation and Comprehension of Unambiguous Object Descriptions*. CVPR.

**Keywords**  
visual referring expression; unambiguous object description; discriminative descriptions; image grounding.

**Why it matters**  
视觉指称表达经典工作，目标是生成能在图像中唯一识别对象的描述。

**Project relevance**  
高。对应我们“生成问题，使视觉模型唯一锁定目标对象/路径”。

---

## 7. RefCOCO / RefCOCO+ / RefCOCOg

**Suggested search queries**
```text
RefCOCO referring expressions dataset
RefCOCO+ RefCOCOg visual grounding
UNC referring expression dataset
```

**Keywords**  
visual grounding; referring expression comprehension; object localization; natural language object reference.

**Project relevance**  
中高。可参考人类如何自然描述目标、空间关系如何表达、描述长度与风格。

---

## 8. CLEVR / GQA / Visual Genome

**Suggested search queries**
```text
CLEVR question generation functional programs
GQA scene graph question generation
Visual Genome question answer scene graph
```

**Keywords**  
scene graph VQA; functional programs; compositional reasoning; executable verification; deterministic answers.

**Project relevance**  
极高。对应我们的 template → executable Cypher → answer verification → coverage update 流程。

---

## 9. Relational / Recursive REG

**Suggested search queries**
```text
relational referring expression generation
recursive referring expressions
landmark selection referring expressions
```

**Keywords**  
relational REG; landmark selection; recursive descriptions; reference object; distractor elimination.

**Project relevance**  
极高。对应 ref object selection、跨分支参照、最大淘汰策略、约束链复杂度控制。

---

## 10. Pragmatic / Overspecified Referring Expressions

**Suggested search queries**
```text
overspecified referring expressions human language generation
pragmatic referring expression generation
RSA referring expressions
```

**Project relevance**  
中。帮助解释为什么“最多两个 ref + dist_rank”即使不是最短，也可能更稳妥、更自然。

---

## How these papers map to our system

| Our module | Related literature |
|---|---|
| Constraint chain | Dale & Reiter incremental algorithm |
| Reference object selection | Relational REG / landmark selection |
| L2 template family | Graph-based REG / scene graph question generation |
| Verify Cypher | CLEVR functional programs |
| Scene graph QA | GQA / Visual Genome |
| Natural spatial language | GRE3D / RefCOCO |

