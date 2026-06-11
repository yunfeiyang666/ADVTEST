"""
=================================================================================
NuScenes-QA 官方答案处理机制详细批注
=================================================================================
作者: NuScenes-QA官方团队 (https://github.com/qiantianwen/NuScenes-QA)
批注整理: 2025-11-27

本文档详细解析NuScenes-QA数据集的官方评估机制，包括：
1. 数据加载流程
2. 答案索引映射机制
3. 严格匹配评估策略
4. 分类统计方法
5. 业界使用规范
=================================================================================
"""

import json
import numpy as np
from collections import defaultdict


# =============================================================================
# 第一部分：答案字典加载机制
# =============================================================================

def load_ans_table(answer_table_path):
    """
    加载答案映射字典
    
    功能说明:
        NuScenes-QA使用预定义的答案字典，而不是开放式答案
        这确保了评估的一致性和可重复性
    
    参数:
        answer_table_path (str): 答案字典文件路径
            通常为: './src/datasets/answer_dict.json'
    
    返回:
        ans2ix (dict): 答案文本 -> 索引的映射
            例如: {'yes': 0, 'no': 1, 'car': 2, ...}
        ix2ans (dict): 索引 -> 答案文本的映射  
            例如: {'0': 'yes', '1': 'no', '2': 'car', ...}
    
    注意事项:
        1. 答案字典是固定的，包含所有可能的答案
        2. 答案总数通常为数千个（包括所有对象类别、数字、yes/no等）
        3. 这个字典在训练和测试时必须保持一致
    """
    ans2ix, ix2ans = json.load(open(answer_table_path, 'r'))
    return ans2ix, ix2ans


# =============================================================================
# 第二部分：模型预测处理
# =============================================================================

def process_model_prediction(pred_logits, dataset):
    """
    处理模型的原始输出，转换为答案索引
    
    功能说明:
        模型输出是一个概率分布，需要转换为具体的答案索引
    
    参数:
        pred_logits (np.ndarray): 模型输出的logits，形状为 [batch_size, ans_size]
            例如: [[0.1, 0.8, 0.05, ...], [0.3, 0.2, 0.4, ...]]
        dataset: 数据集对象，包含ix2ans映射
    
    返回:
        ans_ix_list (list): 预测的答案索引列表
            例如: [1, 2, 0, 5, ...]
    
    处理步骤:
        1. 对每个样本的logits应用argmax，获得最高概率的索引
        2. 使用ix2ans将索引映射回答案文本（可选）
        3. 返回索引供后续评估使用
    
    关键点:
        - 使用argmax而不是softmax+sampling，确保确定性输出
        - 不做任何后处理或平滑，保持原始预测
    """
    # 获取每个样本的最大概率索引
    pred_argmax = np.argmax(pred_logits, axis=1)
    
    # 注释: 这里返回的是索引，不是答案文本
    # 实际评估时会通过ix2ans转换为文本进行比较
    return pred_argmax


# =============================================================================
# 第三部分：核心评估函数（官方实现）
# =============================================================================

def Eval(__C, dataset, ans_ix_list, log_file, result_eval_file):
    """
    NuScenes-QA官方评估函数
    
    这是官方的标准评估实现，所有论文和基准测试都必须使用此函数
    
    参数:
        __C: 配置对象，包含数据路径等信息
        dataset: 数据集对象，包含ix2ans映射
        ans_ix_list (list): 模型预测的答案索引列表
        log_file (str): 日志文件路径
        result_eval_file (str): 详细结果文件路径（可选）
    
    评估流程:
        1. 加载ground truth答案
        2. 将预测索引转换为答案文本
        3. 进行严格字符串匹配
        4. 按题型和推理跳数统计准确率
        5. 输出结果到日志和文件
    """
    
    # -------------------------------------------------------------------------
    # 步骤1: 加载验证集的ground truth答案
    # -------------------------------------------------------------------------
    ques_file_path = __C.RAW_PATH['val']
    true_answers = []        # 存储真实答案文本
    predicted_answers = []   # 存储预测答案文本
    qu = []                  # 存储问题文本（用于结果输出）
    tokens = []              # 存储sample_token（用于结果输出）
    
    with open(ques_file_path, 'r') as f:
        questions = json.load(f)['questions']
        
        # 遍历所有问题，提取真实答案和预测答案
        for ix, ques in enumerate(questions):
            qu.append(ques['question'])
            tokens.append(ques['sample_token'])
            
            # ★ 关键步骤1: 提取真实答案
            # 注意: 转换为字符串确保类型一致性
            true_answers.append(str(ques['answer']))
            
            # ★ 关键步骤2: 将预测索引转换为答案文本
            # dataset.ix2ans是预定义的索引->答案映射字典
            predicted_answers.append(dataset.ix2ans[str(ans_ix_list[ix])])
    
    # -------------------------------------------------------------------------
    # 步骤2: 初始化分类统计字典
    # -------------------------------------------------------------------------
    # 使用defaultdict自动初始化列表，存储每个类别的正确/错误情况
    correct_by_q_type = defaultdict(list)
    
    # -------------------------------------------------------------------------
    # 步骤3: 验证预测数量和真实答案数量一致
    # -------------------------------------------------------------------------
    num_true, num_pred = len(true_answers), len(predicted_answers)
    assert num_true == num_pred, 'Expected %d answers but got %d' % (
        num_true, num_pred)
    
    # -------------------------------------------------------------------------
    # 步骤4: 逐个比较答案并统计（核心评估逻辑）
    # -------------------------------------------------------------------------
    for i, (true_answer, predicted_answer) in enumerate(zip(true_answers, predicted_answers)):
        
        # ★★★ 核心评估机制：严格字符串匹配 ★★★
        # 这是NuScenes-QA的官方标准，必须完全一致才算正确
        correct = 1 if true_answer == predicted_answer else 0
        
        # 统计1: 总体准确率
        correct_by_q_type['Overall'].append(correct)
        
        # 统计2: 按题型分类（5大类）
        # template_type包括: exist, object, count, comparison, status
        q_type = questions[i]['template_type']
        correct_by_q_type[q_type].append(correct)
        
        # 统计3: 按推理跳数细分
        # 将题型和推理跳数组合，例如: 'exist_1', 'count_2'
        sub_q_type = q_type + '_' + str(questions[i]['num_hop'])
        correct_by_q_type[sub_q_type].append(correct)
    
    # -------------------------------------------------------------------------
    # 步骤5: 计算准确率并输出结果
    # -------------------------------------------------------------------------
    print('Write to log file: {}'.format(log_file))
    logfile = open(log_file, 'a+')
    
    # 计算每个类别的准确率
    q_dict = {}
    for q_type, vals in sorted(correct_by_q_type.items()):
        vals = np.asarray(vals)
        # 统计正确数量和总数量
        q_dict[q_type] = [vals.sum(), vals.shape[0]]
    
    # 输出格式化的统计结果
    for q_type in q_dict:
        val, tol = q_dict[q_type]
        accuracy = 100.0 * val / tol
        print(q_type, '%d / %d = %.2f' % (val, tol, accuracy))
        logfile.write(q_type + ' : ' + '%d / %d = %.2f\n' % (val, tol, accuracy))
    
    logfile.write("\n")
    logfile.close()
    
    # -------------------------------------------------------------------------
    # 步骤6: 输出详细的预测结果（可选）
    # -------------------------------------------------------------------------
    if result_eval_file is not None:
        print('Write prediction to result file: {}'.format(result_eval_file))
        result_fs = open(result_eval_file, 'w')
        
        # 输出格式: sample_token | question | predicted | ground_truth
        for i, (token, que, pred, gt) in enumerate(zip(tokens, qu, predicted_answers, true_answers)):
            result_fs.write(token)
            result_fs.write("    ")
            result_fs.write(que)
            result_fs.write("    ")
            result_fs.write(pred)
            result_fs.write("    ")
            result_fs.write(gt)
            result_fs.write("\n")
        
        result_fs.close()
        print('Finished!')


# =============================================================================
# 第四部分：评估机制的关键特性分析
# =============================================================================

"""
【关键特性1：严格字符串匹配】
---------------------------------------------
评估代码: correct = 1 if true_answer == predicted_answer else 0

特点:
1. 完全匹配: 必须字符完全一致
2. 大小写敏感: 'Yes' != 'yes'
3. 空格敏感: 'car ' != 'car'
4. 无容错: 任何细微差异都算错误

影响:
- 优点: 评估标准明确，可重复性强
- 缺点: 对模型输出格式要求严格，可能低估模型能力


【关键特性2：预定义答案字典】
---------------------------------------------
使用固定的ans2ix和ix2ans映射

优点:
1. 限制答案空间，避免开放式答案的歧义
2. 统一评估标准
3. 支持高效的索引查找

局限:
1. 无法处理字典外的答案（即使语义正确）
2. 数字答案可能有多种表达方式
3. 需要预先定义所有可能答案


【关键特性3：分类统计】
---------------------------------------------
统计维度:
1. Overall: 总体准确率
2. template_type: 5种题型（exist, object, count, comparison, status）
3. num_hop: 推理跳数（1跳、2跳等）
4. 组合: template_type + num_hop（如exist_1, count_2）

价值:
- 细粒度分析模型在不同任务类型上的表现
- 识别模型的强项和弱项
- 指导模型改进方向


【关键特性4：无后处理】
---------------------------------------------
官方评估不包含:
1. 答案规范化（大小写、空格）
2. 同义词匹配
3. 数值近似匹配
4. 部分匹配得分

原因:
- 保持评估的客观性和一致性
- 避免引入人为偏见
- 确保不同模型的公平比较
"""


# =============================================================================
# 第五部分：业界使用规范和最佳实践
# =============================================================================

"""
【官方基准测试规范】
---------------------------------------------
✅ 必须遵守的规则:

1. 使用官方评估函数
   - 直接使用Eval()函数，不做修改
   - 使用官方的answer_dict.json

2. 报告指标
   - Overall准确率（必须）
   - 各题型准确率（建议）
   - 各推理跳数准确率（可选）

3. 数据划分
   - 训练集: NuScenes_train_questions.json (376,604题)
   - 验证集: NuScenes_val_questions.json (83,337题)
   - 不允许在验证集上训练或调参

4. 结果报告
   - 明确说明使用的模型版本
   - 报告超参数设置
   - 提供可复现的代码


【改进评估的合理做法】
---------------------------------------------
⚠️ 如果要自定义评估，必须:

1. 同时报告官方指标
   - 先报告官方Eval()的结果
   - 再报告自定义评估的结果
   - 明确说明差异和原因

2. 明确标注改进点
   - 说明为什么需要改进
   - 详细描述改进的评估策略
   - 提供改进的代码实现

3. 应用场景说明
   - 说明改进评估适用的特定场景
   - 不能用改进评估替代官方评估
   - 作为补充分析而非主要指标


【常见的改进评估示例】
---------------------------------------------
示例1: 大小写不敏感评估
def relaxed_match(pred, gt):
    return pred.lower().strip() == gt.lower().strip()

用途: 分析模型语义理解能力（排除格式影响）

示例2: 同义词匹配
synonyms = {
    'yes': ['yeah', 'yep', 'correct'],
    'no': ['nope', 'nah', 'incorrect']
}

用途: 评估模型语义理解（非格式匹配）

示例3: 数值容差匹配
def numeric_match(pred, gt, tolerance=1):
    try:
        return abs(float(pred) - float(gt)) <= tolerance
    except:
        return pred == gt

用途: 计数问题的宽松评估
"""


# =============================================================================
# 第六部分：与其他VQA数据集的对比
# =============================================================================

"""
【NuScenes-QA vs VQA v2.0】
---------------------------------------------
相同点:
1. 都使用预定义答案字典
2. 都采用严格字符串匹配
3. 都有分类统计

不同点:
1. NuScenes-QA专注于3D自动驾驶场景
2. 题型更加结构化（5大类）
3. 有推理跳数标注


【NuScenes-QA vs GQA】
---------------------------------------------
相同点:
1. 都有结构化的题型分类
2. 都有多跳推理标注

不同点:
1. GQA使用场景图作为中间表示
2. GQA有更细粒度的技能标注
3. NuScenes-QA专注于自动驾驶领域


【NuScenes-QA vs OK-VQA】
---------------------------------------------
相同点:
1. 都关注知识推理

不同点:
1. OK-VQA需要外部知识
2. NuScenes-QA主要基于视觉理解
3. 答案评估方式不同（OK-VQA更宽松）
"""


if __name__ == "__main__":
    print(__doc__)
    print("\n" + "="*80)
    print("本文档提供了NuScenes-QA官方答案处理机制的完整批注")
    print("所有论文和基准测试都应遵循官方评估标准")
    print("="*80)
