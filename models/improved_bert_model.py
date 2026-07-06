"""
改进的BERT模型架构：多头注意力聚合 + 自注意力Pooling
用于中文情感分析任务

主要改进：
1. Multi-Head Attention Aggregation: 使用多头注意力聚合BERT输出的序列表示
2. Self-Attention Pooling: 可学习的自注意力Pooling，替代简单的[CLS]或平均池化
3. 增强的分类头：多层感知机分类器，带有残差连接和层归一化
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import BertModel, BertPreTrainedModel


class MultiHeadAttentionAggregation(nn.Module):
    """
    多头注意力聚合层
    将BERT输出的序列表示聚合成单个向量
    """

    def __init__(self, hidden_size: int, num_heads: int = 8, dropout: float = 0.1):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads

        assert self.head_dim * num_heads == hidden_size, "hidden_size must be divisible by num_heads"

        self.query = nn.Linear(hidden_size, hidden_size)
        self.key = nn.Linear(hidden_size, hidden_size)
        self.value = nn.Linear(hidden_size, hidden_size)
        self.output = nn.Linear(hidden_size, hidden_size)

        self.dropout = nn.Dropout(dropout)
        self.scale = self.head_dim ** -0.5

    def forward(self, hidden_states: torch.Tensor, attention_mask: torch.Tensor = None):
        """
        Args:
            hidden_states: BERT输出 [batch_size, seq_len, hidden_size]
            attention_mask: 注意力掩码 [batch_size, seq_len]
        Returns:
            aggregated: 聚合后的向量 [batch_size, hidden_size]
        """
        batch_size, seq_len, _ = hidden_states.shape

        # QKV变换
        q = self.query(hidden_states)
        k = self.key(hidden_states)
        v = self.value(hidden_states)

        # reshape for multi-head attention
        q = q.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)

        # 计算注意力分数
        attn_scores = torch.matmul(q, k.transpose(-2, -1)) * self.scale

        # 应用注意力掩码
        if attention_mask is not None:
            # 扩展掩码维度以匹配多头
            attn_mask = attention_mask.unsqueeze(1).unsqueeze(2)  # [batch, 1, 1, seq_len]
            attn_mask = (1.0 - attn_mask) * -10000.0
            attn_scores = attn_scores + attn_mask

        # 注意力权重
        attn_weights = F.softmax(attn_scores, dim=-1)
        attn_weights = self.dropout(attn_weights)

        # 应用注意力到values
        context = torch.matmul(attn_weights, v)

        # 合并多头
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len, self.hidden_size)

        # 输出投影
        output = self.output(context)

        return output, attn_weights


class SelfAttentionPooling(nn.Module):
    """
    自注意力Pooling层
    可学习的注意力权重对序列进行加权求和
    """

    def __init__(self, hidden_size: int, dropout: float = 0.1):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1, bias=False)
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, hidden_states: torch.Tensor, attention_mask: torch.Tensor = None):
        """
        Args:
            hidden_states: BERT输出 [batch_size, seq_len, hidden_size]
            attention_mask: 注意力掩码 [batch_size, seq_len]
        Returns:
            pooled: 加权聚合后的向量 [batch_size, hidden_size]
        """
        # 计算注意力分数
        attn_scores = self.attention(hidden_states).squeeze(-1)  # [batch_size, seq_len]

        # 应用掩码
        if attention_mask is not None:
            attn_scores = attn_scores + (1 - attention_mask) * -10000.0

        # softmax归一化
        attn_weights = F.softmax(attn_scores, dim=-1)  # [batch_size, seq_len]
        attn_weights = self.dropout(attn_weights)

        # 加权求和
        pooled = torch.bmm(attn_weights.unsqueeze(1), hidden_states).squeeze(1)  # [batch_size, hidden_size]

        return pooled, attn_weights


class EnhancedClassificationHead(nn.Module):
    """
    增强的分类头
    多层感知机 + 残差连接 + 层归一化
    """

    def __init__(self, hidden_size: int, num_labels: int, dropout: float = 0.1):
        super().__init__()
        self.dense = nn.Linear(hidden_size, hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.out_proj = nn.Linear(hidden_size, num_labels)

        self.layer_norm = nn.LayerNorm(hidden_size)
        self.activation = nn.GELU()

    def forward(self, hidden_states: torch.Tensor):
        """
        Args:
            hidden_states: 输入向量 [batch_size, hidden_size]
        Returns:
            logits: 分类logits [batch_size, num_labels]
        """
        # 残差连接
        hidden_states = self.layer_norm(hidden_states + self.dense(self.activation(hidden_states)))
        hidden_states = self.dropout(hidden_states)
        logits = self.out_proj(hidden_states)
        return logits


class ImprovedBertForSequenceClassification(BertPreTrainedModel):
    """
    改进的BERT分类模型

    结合了：
    1. 多头注意力聚合层
    2. 自注意力Pooling层
    3. 增强的分类头

    支持多种Pooling方式的组合：
    - mha_pool: 多头注意力 + 自注意力Pooling
    - cls_mha: [CLS] + 多头注意力
    - all_concat: 拼接所有表示
    """

    def __init__(
        self,
        config,
        num_labels: int = None,
        pooling_strategy: str = "mha_pool",
        num_attention_heads: int = 8,
        use_weighted_pooling: bool = True,
        **kwargs
    ):
        super().__init__(config, **kwargs)

        self.num_labels = config.num_labels if num_labels is None else num_labels
        self.pooling_strategy = pooling_strategy
        self.hidden_size = config.hidden_size

        # BERT主干
        self.bert = BertModel(config)

        # 多头注意力聚合
        self.mha = MultiHeadAttentionAggregation(
            hidden_size=self.hidden_size,
            num_heads=num_attention_heads,
            dropout=config.hidden_dropout_prob
        )

        # 自注意力Pooling
        self.self_attn_pool = SelfAttentionPooling(
            hidden_size=self.hidden_size,
            dropout=config.hidden_dropout_prob
        )

        # 分类器配置
        classifier_dropout = (
            config.classifier_dropout if hasattr(config, 'classifier_dropout') and config.classifier_dropout is not None
            else config.hidden_dropout_prob
        )

        # 根据Pooling策略确定分类器输入维度
        if pooling_strategy == "all_concat":
            classifier_input_dim = self.hidden_size * 3  # [CLS] + MHA + SAP
        else:
            classifier_input_dim = self.hidden_size

        # 增强的分类头
        self.classifier = nn.Sequential(
            nn.Linear(classifier_input_dim, self.hidden_size),
            nn.LayerNorm(self.hidden_size),
            nn.GELU(),
            nn.Dropout(classifier_dropout),
            EnhancedClassificationHead(self.hidden_size, self.num_labels, classifier_dropout)
        )

        # 可学习的Pooling权重（用于组合多种表示）
        if use_weighted_pooling and pooling_strategy == "all_concat":
            self.pooling_weights = nn.Parameter(torch.ones(3) / 3)
        else:
            self.pooling_weights = None

        # 初始化权重
        self.post_init()

    def get_attention_weights(self, input_ids, attention_mask=None, token_type_ids=None):
        """获取注意力权重，用于可视化分析"""
        outputs = self.bert(
            input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            output_hidden_states=False
        )
        hidden_states = outputs.last_hidden_state

        if self.pooling_strategy in ["mha", "mha_pool"]:
            _, mha_attn = self.mha(hidden_states, attention_mask)
        else:
            mha_attn = None

        if self.pooling_strategy in ["sap", "mha_pool"]:
            _, sap_attn = self.self_attn_pool(hidden_states, attention_mask)
        else:
            sap_attn = None

        return {
            "mha_attention": mha_attn,
            "sap_attention": sap_attn,
            "bert_attention": outputs.attentions[-1] if outputs.attentions else None
        }

    def forward(
        self,
        input_ids,
        attention_mask=None,
        token_type_ids=None,
        position_ids=None,
        head_mask=None,
        inputs_embeds=None,
        labels=None,
        output_attentions=False,
        output_hidden_states=False,
        return_dict=None,
        **kwargs
    ):
        r"""
        labels (`torch.LongTensor` of shape `(batch_size,)`, *optional*):
            Labels for computing the sequence classification/regression loss.
        """
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        # BERT编码
        outputs = self.bert(
            input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        hidden_states = outputs[0]  # [batch_size, seq_len, hidden_size]

        # 根据策略选择Pooling方式
        if self.pooling_strategy == "cls":
            pooled = hidden_states[:, 0]  # [CLS] token

        elif self.pooling_strategy == "mean":
            # 平均池化
            if attention_mask is not None:
                mask_expanded = attention_mask.unsqueeze(-1).expand(hidden_states.size()).float()
                sum_embeddings = torch.sum(hidden_states * mask_expanded, 1)
                sum_mask = mask_expanded.sum(1)
                sum_mask = torch.clamp(sum_mask, min=1e-9)
                pooled = sum_embeddings / sum_mask
            else:
                pooled = torch.mean(hidden_states, 1)

        elif self.pooling_strategy == "max":
            # 最大池化
            pooled, _ = torch.max(hidden_states + (1 - attention_mask.unsqueeze(-1)) * -10000.0, 1)

        elif self.pooling_strategy == "mha":
            # 仅使用多头注意力聚合
            mha_output, _ = self.mha(hidden_states, attention_mask)
            pooled = mha_output[:, 0]  # 取[CLS]位置

        elif self.pooling_strategy == "sap":
            # 仅使用自注意力Pooling
            pooled, _ = self.self_attn_pool(hidden_states, attention_mask)

        elif self.pooling_strategy == "mha_pool":
            # 多头注意力 + 自注意力Pooling组合
            mha_output, _ = self.mha(hidden_states, attention_mask)
            pooled, _ = self.self_attn_pool(mha_output, attention_mask)

        elif self.pooling_strategy == "all_concat":
            # 拼接所有表示
            cls_output = hidden_states[:, 0]
            mha_output, _ = self.mha(hidden_states, attention_mask)
            mha_pooled = mha_output[:, 0]
            sap_pooled, _ = self.self_attn_pool(hidden_states, attention_mask)

            if self.pooling_weights is not None:
                # 加权组合
                weights = F.softmax(self.pooling_weights, dim=0)
                pooled = weights[0] * cls_output + weights[1] * mha_pooled + weights[2] * sap_pooled
            else:
                # 直接拼接
                pooled = torch.cat([cls_output, mha_pooled, sap_pooled], dim=-1)

        else:
            # 默认使用[CLS]
            pooled = hidden_states[:, 0]

        # 分类
        logits = self.classifier(pooled)

        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss()
            loss = loss_fct(logits.view(-1, self.num_labels), labels.view(-1))

        output = (logits,) + outputs[2:] if output_hidden_states or output_attentions else (logits,)
        if output_attentions:
            output = output + (outputs.attentions[-1],)  # 返回最后一层注意力

        return {
            "loss": loss,
            "logits": logits,
            "hidden_states": outputs.hidden_states if output_hidden_states else None,
            "attentions": outputs.attentions if output_attentions else None,
            "pooled_output": pooled,
        }


def create_improved_model(
    model_name: str = 'hfl/chinese-macbert-base',
    num_labels: int = 6,
    pooling_strategy: str = "mha_pool",
    num_attention_heads: int = 8,
    use_weighted_pooling: bool = True,
    **kwargs
):
    """
    创建改进模型的便捷函数

    Args:
        model_name: 预训练模型名称
        num_labels: 分类标签数量
        pooling_strategy: Pooling策略
            - "cls": 仅使用[CLS] token
            - "mean": 平均池化
            - "max": 最大池化
            - "mha": 多头注意力聚合
            - "sap": 自注意力Pooling
            - "mha_pool": 多头注意力 + 自注意力Pooling (推荐)
            - "all_concat": 拼接所有表示
        num_attention_heads: 多头注意力的头数
        use_weighted_pooling: 是否使用可学习的Pooling权重
    """
    from transformers import AutoTokenizer, AutoConfig

    config = AutoConfig.from_pretrained(model_name)
    config.num_labels = num_labels

    model = ImprovedBertForSequenceClassification(
        config,
        num_labels=num_labels,
        pooling_strategy=pooling_strategy,
        num_attention_heads=num_attention_heads,
        use_weighted_pooling=use_weighted_pooling,
        **kwargs
    )

    # 加载预训练权重
    pretrained_model = BertModel.from_pretrained(model_name, config=config)

    # 只加载BERT部分的权重，分类器使用随机初始化
    model.bert.load_state_dict(pretrained_model.state_dict(), strict=False)

    return model
