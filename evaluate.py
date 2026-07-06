#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SmartCS 系统评估脚本
用于评估情感分析模型的准确率、精确率、召回率、F1 分数等指标
"""
import os
import sys
import json
from collections import defaultdict
from typing import Dict, List, Tuple

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

import torch
import torch.nn.functional as F
from transformers import BertTokenizer

# 导入自定义改进模型
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models'))
from improved_bert_model import ImprovedBertForSequenceClassification

LABEL_MAP = {0: "neutral", 1: "happy", 2: "angry", 3: "sad", 4: "fear", 5: "surprise"}
LABEL_MAP_REVERSE = {v: k for k, v in LABEL_MAP.items()}

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_data(data_path: str) -> List[Dict[str, object]]:
    """加载评估数据集（每行一个 JSON：{"text": "...", "label": "happy"}）"""
    if not os.path.exists(data_path):
        print(f"[错误] 数据文件不存在: {data_path}")
        return []

    samples = []
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    text = (obj.get("text") or obj.get("sentence") or obj.get("content") or "").strip()
                    label = (obj.get("label") or obj.get("sentiment") or "").strip()
                    if text and label and label in LABEL_MAP_REVERSE:
                        samples.append({"text": text, "label": label})
                except json.JSONDecodeError:
                    continue
        print(f"[OK] 从 {data_path} 加载了 {len(samples)} 条评估样本")
    except Exception as e:
        print(f"[错误] 加载数据失败: {e}")
    return samples


def load_data_from_dir(dir_path: str) -> List[Dict[str, object]]:
    """从目录下读取所有 .json 文件"""
    all_samples = []
    if not os.path.isdir(dir_path):
        return all_samples
    for fname in sorted(os.listdir(dir_path)):
        fpath = os.path.join(dir_path, fname)
        if fname.endswith(".json"):
            all_samples.extend(load_data(fpath))
    return all_samples


def evaluate_model(
    model: torch.nn.Module,
    tokenizer: BertTokenizer,
    samples: List[Dict[str, object]],
) -> Dict[str, object]:
    """评估模型性能，返回准确率、精确率、召回率、F1、混淆矩阵等"""
    model.eval()
    model.to(device)

    correct = 0
    total = len(samples)
    all_preds: List[str] = []
    all_labels: List[str] = []

    for s in samples:
        text = s["text"]
        true_label = s["label"]

        try:
            inputs = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=128,
            ).to(device)

            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits if hasattr(outputs, "logits") else outputs.get("logits", outputs)
                probs = F.softmax(logits, dim=1)
                _, predicted_class = torch.max(probs, dim=1)

            pred_label = LABEL_MAP.get(int(predicted_class.item()), "neutral")
        except Exception as e:
            print(f"[WARN] 预测出错 (text={text[:30]}...): {e}")
            pred_label = "neutral"

        if pred_label == true_label:
            correct += 1
        all_preds.append(pred_label)
        all_labels.append(true_label)

    # 计算各分类指标
    labels_list = list(LABEL_MAP.values())
    per_class: Dict[str, Dict[str, object]] = {}
    total_tp = 0
    total_fp = 0
    total_fn = 0

    for lbl in labels_list:
        tp = sum(1 for p, t in zip(all_preds, all_labels) if p == lbl and t == lbl)
        fp = sum(1 for p, t in zip(all_preds, all_labels) if p == lbl and t != lbl)
        fn = sum(1 for p, t in zip(all_preds, all_labels) if p != lbl and t == lbl)
        tn = sum(1 for p, t in zip(all_preds, all_labels) if p != lbl and t != lbl)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class[lbl] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    accuracy = correct / total if total > 0 else 0.0
    macro_precision = sum(v["precision"] for v in per_class.values()) / len(labels_list) if labels_list else 0.0
    macro_recall = sum(v["recall"] for v in per_class.values()) / len(labels_list) if labels_list else 0.0
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(labels_list) if labels_list else 0.0

    micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall) if (micro_precision + micro_recall) > 0 else 0.0

    result = {
        "total_samples": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
        "micro_precision": round(micro_precision, 4),
        "micro_recall": round(micro_recall, 4),
        "micro_f1": round(micro_f1, 4),
        "per_class": per_class,
    }

    return result


def main():
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "my_finetuned_bert")

    print("=" * 60)
    print("SmartCS 情感分析模型评估")
    print("=" * 60)

    # 加载评估数据
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test（最终评测集）")
    samples = load_data_from_dir(data_dir) if os.path.isdir(data_dir) else []

    if not samples:
        # 回退到 eval 数据集
        data_dir_alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "eval（刷榜数据集）")
        samples = load_data_from_dir(data_dir_alt) if os.path.isdir(data_dir_alt) else []

    if not samples:
        print("[错误] 没有找到评估数据集（data/test（最终评测集）/ 或 data/eval（刷榜数据集）/）")
        print("请确保放入了 JSON 格式的评估数据文件。")
        return

    print(f"评测样本总数: {len(samples)}")

    # 加载模型
    try:
        tokenizer = BertTokenizer.from_pretrained(model_path)
        # 使用自定义模型类加载（保存时使用了 save_pretrained，加载需指定自定义类）
        model = ImprovedBertForSequenceClassification.from_pretrained(model_path)
        model.to(device)
        model.eval()
        print(f"模型加载成功: {model_path}")
    except Exception as e:
        print(f"模型加载失败: {e}")
        return

    # 执行评估
    result = evaluate_model(model, tokenizer, samples)
    print("\n" + "=" * 60)
    print("评估结果")
    print("=" * 60)
    print(f"总样本数: {result['total_samples']}")
    print(f"正确数: {result['correct']}")
    print(f"准确率 (Accuracy): {result['accuracy']:.2%}")
    print(f"宏精确率 (Macro-Precision): {result['macro_precision']:.4f}")
    print(f"宏召回率 (Macro-Recall): {result['macro_recall']:.4f}")
    print(f"宏 F1 (Macro-F1): {result['macro_f1']:.4f}")
    print(f"微精确率 (Micro-Precision): {result['micro_precision']:.4f}")
    print(f"微召回率 (Micro-Recall): {result['micro_recall']:.4f}")
    print(f"微 F1 (Micro-F1): {result['micro_f1']:.4f}")

    print("\n各分类指标:")
    print("-" * 60)
    print(f"{'类别':<12}{'Precision':<12}{'Recall':<12}{'F1':<12}{'样本数':<8}")
    print("-" * 60)
    for lbl in LABEL_MAP.values():
        pc = result["per_class"].get(lbl, {})
        support = pc.get("tp", 0) + pc.get("fn", 0)
        print(f"{lbl:<12}{pc.get('precision', 0):<12.4f}{pc.get('recall', 0):<12.4f}{pc.get('f1', 0):<12.4f}{support:<8}")

    # 输出 JSON 结果到文件
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluation_result.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n评估结果已保存至: {output_path}")


if __name__ == "__main__":
    main()