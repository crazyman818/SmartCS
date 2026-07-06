import torch
from torch.utils.data import Dataset, DataLoader, random_split
from transformers import BertTokenizer, BertForSequenceClassification
from torch.optim import AdamW
import json
import os
import sys
import numpy as np
from typing import List, Tuple, Optional

from dotenv import load_dotenv
load_dotenv()

try:
    from sklearn.metrics import f1_score, classification_report
except Exception:
    f1_score = None
    classification_report = None

# 导入改进的模型（兼容直接运行和模块导入两种方式）
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root_for_import = os.path.dirname(current_dir)
if project_root_for_import not in sys.path:
    sys.path.insert(0, project_root_for_import)

try:
    from models.improved_bert_model import (
        ImprovedBertForSequenceClassification,
        create_improved_model,
        MultiHeadAttentionAggregation,
        SelfAttentionPooling
    )
    IMPROVED_MODEL_AVAILABLE = True
except ImportError:
    try:
        from .improved_bert_model import (
            ImprovedBertForSequenceClassification,
            create_improved_model,
            MultiHeadAttentionAggregation,
            SelfAttentionPooling
        )
        IMPROVED_MODEL_AVAILABLE = True
    except ImportError:
        IMPROVED_MODEL_AVAILABLE = False
        ImprovedBertForSequenceClassification = None
        create_improved_model = None

# ==========================================
# 1. 配置参数
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

# 拼接数据文件的绝对路径
# 训练文件
TRAIN_FILES = [
    os.path.join(project_root, 'data', 'train', 'usual_train.txt'),
    os.path.join(project_root, 'data', 'train', 'virus_train.txt')
]

# 验证文件：使用 eval 目录下的标注评测集
VAL_FILES = [
    os.path.join(project_root, 'data', 'eval（刷榜数据集）', 'usual_eval_labeled.txt'),
    os.path.join(project_root, 'data', 'eval（刷榜数据集）', 'virus_eval_labeled.txt'),
]

SAVE_PATH = os.path.join(project_root, 'models', 'my_finetuned_bert')

# 更强中文底座（可通过环境变量 EMOTION_BASE_MODEL 覆盖）
MODEL_NAME = os.environ.get("EMOTION_BASE_MODEL", "").strip() or 'hfl/chinese-macbert-base'
BATCH_SIZE = 16
EPOCHS = 6  # 方案A：增加训练轮次，让模型充分收敛
MAX_LEN = 128
LR = 1e-5  # 方案A：降低学习率，更稳定收敛
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.06
SEED = 42
RDROP_ALPHA = 3.0  # 方案A：开启 R-Drop 正则化
LABEL_SMOOTHING = 0.1  # 方案A：开启 Label Smoothing，防止过拟合
USE_FGM = True  # 方案A：开启 FGM 对抗训练
FGM_EPS = 1.0  # 常用 0.5~1.0

LABEL_MAP = {'neutral': 0, 'happy': 1, 'angry': 2, 'sad': 3, 'fear': 4, 'surprise': 5}
NUM_LABELS = len(LABEL_MAP)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Using device: {device}")

# ==========================================
# 1.1 模型架构选择
# ==========================================
# MODEL_TYPE: 'bert' (原始) 或 'improved' (改进的多头注意力+自注意力Pooling)
MODEL_TYPE = os.environ.get("EMOTION_MODEL_TYPE", "").strip() or 'improved'
# Pooling策略: 'cls', 'mean', 'max', 'mha', 'sap', 'mha_pool', 'all_concat'
POOLING_STRATEGY = os.environ.get("EMOTION_POOLING_STRATEGY", "").strip() or 'mha_pool'
# 多头注意力头数
NUM_ATTENTION_HEADS = 8
# 是否使用可学习的Pooling权重
USE_WEIGHTED_POOLING = True


# ==========================================
# 2. 数据处理函数
# ==========================================
def load_data_from_json_txt(file_paths):
    all_texts = []
    all_labels = []

    if isinstance(file_paths, str):
        file_paths = [file_paths]

    for file_path in file_paths:
        print(f"读取文件: {os.path.basename(file_path)}")

        if not os.path.exists(file_path):
            print(f"  ⚠️ 文件不存在: {file_path}")
            continue

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data_list = json.load(f)
                count = 0
                for item in data_list:
                    label_str = item.get('label')
                    content = item.get('content')

                    if label_str is None or label_str == 'None' or label_str not in LABEL_MAP:
                        continue

                    all_texts.append(content)
                    all_labels.append(LABEL_MAP[label_str])
                    count += 1
                print(f"  -> 加载 {count} 条")
            except Exception as e:
                print(f"  ❌ 解析失败: {file_path}，错误: {e}")

    return all_texts, all_labels


# ==========================================
# 3. 数据集类
# ==========================================
class WeiboEmotionDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, item):
        text = str(self.texts[item])
        label = self.labels[item]

        # transformers v5 中推荐直接调用 tokenizer，而不是 encode_plus
        encoding = self.tokenizer(
            text,
            padding="max_length",
            truncation=True,
            max_length=self.max_len,
            return_tensors="pt",
        )

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(label, dtype=torch.long),
        }


# ==========================================
# 4. 训练流程
# ==========================================
def set_seed(seed: int) -> None:
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_class_weights(labels: List[int], num_labels: int) -> torch.Tensor:
    """
    用于处理类别不均衡：weight_i = total / (num_labels * count_i)
    """
    counts = np.bincount(np.array(labels, dtype=np.int64), minlength=num_labels).astype(np.float64)
    counts[counts == 0] = 1.0
    total = float(counts.sum())
    w = total / (num_labels * counts)
    w = w / w.mean()
    return torch.tensor(w, dtype=torch.float)


def kl_div_loss(p_logits: torch.Tensor, q_logits: torch.Tensor) -> torch.Tensor:
    """
    对称 KL：KL(p||q) + KL(q||p)，输入为未归一化 logits
    """
    p = torch.nn.functional.log_softmax(p_logits, dim=-1)
    q = torch.nn.functional.log_softmax(q_logits, dim=-1)
    p2 = torch.nn.functional.softmax(p_logits, dim=-1)
    q2 = torch.nn.functional.softmax(q_logits, dim=-1)
    kl_pq = torch.nn.functional.kl_div(p, q2, reduction="batchmean")
    kl_qp = torch.nn.functional.kl_div(q, p2, reduction="batchmean")
    return kl_pq + kl_qp


def label_smoothed_ce(logits: torch.Tensor, target: torch.Tensor, smoothing: float, weight: Optional[torch.Tensor] = None) -> torch.Tensor:
    """
    多分类 label smoothing CE。smoothing=0 时等价普通 CE。
    """
    if smoothing <= 0:
        return torch.nn.functional.cross_entropy(logits, target, weight=weight)
    n_class = logits.size(-1)
    log_probs = torch.nn.functional.log_softmax(logits, dim=-1)
    # NLL
    nll = -log_probs.gather(dim=-1, index=target.unsqueeze(1)).squeeze(1)
    # smooth loss
    smooth = -log_probs.mean(dim=-1)

    if weight is not None:
        # 对真实标签位置加权，平滑项保持均匀
        w = weight.gather(dim=0, index=target)
        nll = nll * w
        # 归一化避免尺度爆炸
        nll = nll / (w.mean().clamp_min(1e-6))

    loss = (1.0 - smoothing) * nll + smoothing * smooth
    return loss.mean()


def eval_metrics(preds: List[int], labels: List[int]) -> Tuple[float, float]:
    """
    返回 (accuracy, macro_f1)。若 sklearn 不可用则 macro_f1 退化为 accuracy。
    """
    preds_np = np.array(preds, dtype=np.int64)
    labels_np = np.array(labels, dtype=np.int64)
    acc = float((preds_np == labels_np).mean()) if len(labels_np) else 0.0
    if f1_score is None:
        return acc, acc
    mf1 = float(f1_score(labels_np, preds_np, average="macro"))
    return acc, mf1


class FGM:
    """
    Fast Gradient Method（对抗训练）：在 embedding 参数上加扰动
    """

    def __init__(self, model: torch.nn.Module, emb_name: str = "embeddings.word_embeddings"):
        self.model = model
        self.emb_name = emb_name
        self.backup = {}

    def attack(self, epsilon: float = 1.0):
        for name, param in self.model.named_parameters():
            if param.requires_grad and self.emb_name in name and param.grad is not None:
                self.backup[name] = param.data.clone()
                grad = param.grad
                norm = torch.norm(grad)
                if norm is None or norm.item() == 0:
                    continue
                r_at = epsilon * grad / norm
                param.data.add_(r_at)

    def restore(self):
        for name, param in self.model.named_parameters():
            if name in self.backup:
                param.data = self.backup[name]
        self.backup = {}


def train_model():
    set_seed(SEED)
    print("\n[1/5] 加载数据...")
    # 加载所有数据
    train_texts, train_labels = load_data_from_json_txt(TRAIN_FILES)
    val_texts, val_labels = load_data_from_json_txt(VAL_FILES)

    # === 关键修复：如果没找到验证集文件，自动从训练集切分 ===
    tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)

    if len(train_texts) == 0:
        print("❌ 错误: 训练集为空！请检查 data/train 目录。")
        return

    full_train_dataset = WeiboEmotionDataset(train_texts, train_labels, tokenizer, MAX_LEN)

    if len(val_texts) == 0:
        print("\n⚠️ 警告: 未找到有效的验证集文件，或者文件内无标签。")
        print("💡 正在尝试从训练集中自动切分 10% 作为验证集...")

        total_size = len(full_train_dataset)
        val_size = int(0.1 * total_size)
        train_size = total_size - val_size

        train_dataset, val_dataset = random_split(
            full_train_dataset,
            [train_size, val_size],
            generator=torch.Generator().manual_seed(SEED),
        )
        print(f"  -> 自动切分完成: 训练集 {len(train_dataset)} 条, 验证集 {len(val_dataset)} 条")
    else:
        # 正常加载
        train_dataset = full_train_dataset
        val_dataset = WeiboEmotionDataset(val_texts, val_labels, tokenizer, MAX_LEN)
        print(f"  -> 验证集加载成功: {len(val_dataset)} 条")

    # === 防止切分后依然为空 ===
    if len(val_dataset) == 0:
        print("❌ 无法构建验证集，请检查数据源。")
        return

    # DataLoader
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, num_workers=0)

    # 模型初始化
    print(f"\n[3/5] 加载预训练模型: {MODEL_NAME}")
    
    # 决定使用哪个模型类型
    model_type_to_use = MODEL_TYPE
    if model_type_to_use == 'improved':
        if not IMPROVED_MODEL_AVAILABLE:
            print("  ⚠️ 改进模型模块加载失败，回退到原始BERT模型")
            model_type_to_use = 'bert'
        else:
            print(f"  -> 使用改进的模型架构 (Pooling: {POOLING_STRATEGY})")
            model = create_improved_model(
                model_name=MODEL_NAME,
                num_labels=NUM_LABELS,
                pooling_strategy=POOLING_STRATEGY,
                num_attention_heads=NUM_ATTENTION_HEADS,
                use_weighted_pooling=USE_WEIGHTED_POOLING
            )
    
    if model_type_to_use != 'improved':
        print("  -> 使用原始BERT模型")
        model = BertForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=NUM_LABELS)
    
    model = model.to(device)

    optimizer = AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

    # 学习率调度：线性 warmup
    try:
        from transformers import get_linear_schedule_with_warmup
    except Exception:
        get_linear_schedule_with_warmup = None  # type: ignore

    total_steps = max(1, len(train_loader) * EPOCHS)
    warmup_steps = int(total_steps * WARMUP_RATIO)
    scheduler = None
    if get_linear_schedule_with_warmup is not None:
        scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)

    # 类别权重（处理严重不均衡）
    class_weights = build_class_weights(train_labels, NUM_LABELS).to(device)
    print("Class weights:", class_weights.detach().cpu().numpy().round(3).tolist())
    if RDROP_ALPHA > 0:
        print(f"R-Drop enabled: alpha={RDROP_ALPHA}")
    if LABEL_SMOOTHING > 0:
        print(f"Label smoothing enabled: eps={LABEL_SMOOTHING}")
    if USE_FGM:
        print(f"FGM enabled: eps={FGM_EPS}")
    fgm = FGM(model) if USE_FGM else None

    print(f"\n[4/5] 开始训练 ({EPOCHS} Epochs)...")
    best_macro_f1 = -1.0

    for epoch in range(EPOCHS):
        print(f"\n======== Epoch {epoch + 1} / {EPOCHS} ========")
        model.train()
        total_train_loss = 0

        def compute_loss(b_input_ids, b_input_mask, b_labels) -> torch.Tensor:
            if RDROP_ALPHA > 0:
                # 两次 forward（利用 dropout 随机性）
                if model_type_to_use == 'improved':
                    out1 = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                    out2 = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                    logits1, logits2 = out1['logits'], out2['logits']
                else:
                    out1 = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                    out2 = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                    logits1, logits2 = out1.logits, out2.logits
                
                ce1 = label_smoothed_ce(logits1, b_labels, LABEL_SMOOTHING, weight=class_weights)
                ce2 = label_smoothed_ce(logits2, b_labels, LABEL_SMOOTHING, weight=class_weights)
                kl = kl_div_loss(logits1, logits2)
                return 0.5 * (ce1 + ce2) + RDROP_ALPHA * kl

            if model_type_to_use == 'improved':
                outputs = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                logits = outputs['logits']
            else:
                outputs = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                logits = outputs.logits
            return label_smoothed_ce(logits, b_labels, LABEL_SMOOTHING, weight=class_weights)

        for step, batch in enumerate(train_loader):
            b_input_ids = batch['input_ids'].to(device)
            b_input_mask = batch['attention_mask'].to(device)
            b_labels = batch['labels'].to(device)

            model.zero_grad()
            loss = compute_loss(b_input_ids, b_input_mask, b_labels)
            total_train_loss += loss.item()
            loss.backward()

            # FGM 对抗训练：在 embedding 上加扰动，再反向一次
            if fgm is not None:
                fgm.attack(epsilon=FGM_EPS)
                loss_adv = compute_loss(b_input_ids, b_input_mask, b_labels)
                loss_adv.backward()
                fgm.restore()

            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            if scheduler is not None:
                scheduler.step()

            if step % 50 == 0 and step > 0:
                print(f"  Batch {step} | Loss: {loss.item():.4f}")

        avg_train_loss = total_train_loss / len(train_loader)
        print(f"  平均训练 Loss: {avg_train_loss:.4f}")

        # 验证
        print("  正在验证...")
        model.eval()
        total_eval_loss = 0
        all_preds: List[int] = []
        all_labels: List[int] = []

        for batch in val_loader:
            b_input_ids = batch['input_ids'].to(device)
            b_input_mask = batch['attention_mask'].to(device)
            b_labels = batch['labels'].to(device)

            with torch.no_grad():
                if model_type_to_use == 'improved':
                    outputs = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                    logits = outputs['logits']
                else:
                    outputs = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
                    logits = outputs.logits
                loss = label_smoothed_ce(logits, b_labels, LABEL_SMOOTHING, weight=class_weights)
            total_eval_loss += float(loss.item())
            preds = torch.argmax(logits, dim=1).flatten()
            all_preds.extend(preds.detach().cpu().numpy().tolist())
            all_labels.extend(b_labels.detach().cpu().numpy().tolist())

        # 计算平均值（这里如果不加判断，就会报除以0错误，但上面我们已经保证了 val_dataset 不为空）
        avg_val_loss = total_eval_loss / len(val_loader)
        val_acc, val_macro_f1 = eval_metrics(all_preds, all_labels)

        print(f"  验证 Loss: {avg_val_loss:.4f} | Acc: {val_acc:.4f} | Macro-F1: {val_macro_f1:.4f}")
        if classification_report is not None:
            try:
                print(classification_report(all_labels, all_preds, digits=4))
            except Exception:
                pass

        if val_macro_f1 > best_macro_f1:
            best_macro_f1 = val_macro_f1
            print("  ★ 保存最佳模型（按 Macro-F1）...")
            if not os.path.exists(SAVE_PATH): os.makedirs(SAVE_PATH)
            
            # 改进的模型使用相同的保存方法
            model.save_pretrained(SAVE_PATH)
            tokenizer.save_pretrained(SAVE_PATH)
            
            # 额外保存模型类型信息
            model_info = {
                "model_type": MODEL_TYPE,
                "pooling_strategy": POOLING_STRATEGY if MODEL_TYPE == 'improved' else None,
                "num_attention_heads": NUM_ATTENTION_HEADS if MODEL_TYPE == 'improved' else None,
                "base_model": MODEL_NAME,
                "best_macro_f1": float(best_macro_f1)
            }
            with open(os.path.join(SAVE_PATH, "model_info.json"), 'w', encoding='utf-8') as f:
                json.dump(model_info, f, ensure_ascii=False, indent=2)

    print("\n✅ 训练结束！")


if __name__ == '__main__':
    train_model()
