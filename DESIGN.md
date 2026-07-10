# SmartCS 设计规范

基于 taste-skill 设计方法论，适用于本项目所有前端开发。

---

## 1. Design Read（设计定位）

> "B2C e-commerce customer service web app for end-users and admin operators,
> with a Linear-style clean tool aesthetic, restrained teal accent."

| 维度 | 设定 |
|---|---|
| **页面类型** | SaaS 客服工具（聊天 + 管理后台 + 数据看板） |
| **受众** | C 端用户（聊天） + B 端管理员（后台） |
| **风格** | Linear-style SaaS 工具型 — 专业、高效、可信 |
| **技术栈** | Flask + Jinja2 + 原生 CSS（非 React/Tailwind） |

---

## 2. Three Dials（三 Dial 基准）

| Dial | 值 | 含义 |
|---|---|---|
| **DESIGN_VARIANCE** | `5` | 偏对称整洁，不允许艺术化/非对称布局 |
| **MOTION_INTENSITY** | `4` | 仅 CSS transition/animation，不做滚动驱动动画 |
| **VISUAL_DENSITY** | `5` | 中等信息密度，聊天气泡区松散 + 数据面板紧凑 |

**页面预设覆盖：**
| 页面 | VARIANCE | MOTION | DENSITY | 原因 |
|---|---|---|---|---|
| 聊天页 | 5 | 4 | 4 | 聊天气泡需要呼吸感 |
| 管理后台 | 4 | 3 | 6 | 数据表格紧凑 |
| 数据看板 | 5 | 3 | 6 | KPI + 图表密度高 |
| 登录/注册 | 4 | 3 | 3 | 品牌感 + 留白 |

---

## 3. 色彩体系

### 3.1 主色调 — Teal

```
--primary:        #0d9488   (主色)
--primary-light:  #5eead4   (高亮)
--primary-dark:   #0f766e   (深色/hover)
--primary-subtle: rgba(13, 148, 136, 0.08)  (微妙背景)
--primary-glow:   rgba(13, 148, 136, 0.18)  (focus 光环)
```

### 3.2 中性色 — Slate

| Token | Light | Dark |
|---|---|---|
| `--bg-primary` | `#f8fafc` | `#0b1120` |
| `--bg-secondary` | `#f1f5f9` | `#121b2d` |
| `--bg-card` | `#ffffff` | `#121b2d` |
| `--text-primary` | `#0f172a` | `#f1f5f9` |
| `--text-secondary` | `#475569` | `#94a3b8` |
| `--text-muted` | `#94a3b8` | `#64748b` |
| `--border` | `#e2e8f0` | `#1e293b` |

### 3.3 语义色

```
--success:  #059669
--warning:  #d97706
--danger:   #dc2626
--info:     #0284c7
```

### 3.4 规则

- **禁止** `#000000` 和 `#ffffff` 纯黑纯白
- **禁止** AI-purple (`#4f46e5` 等)
- **禁止** `linear-gradient` 双色按钮
- **禁止** warm gray 和 cool gray 混用
- **禁止** 纯黑透明度阴影 → 用 tinted shadow
- 一个页面只用一个 accent，不允许突然换色
- 深色模式下语义色需调透明度（`rgba` 代替硬编码 hex）

---

## 4. 字体

| 用途 | 字体 | weight |
|---|---|---|
| **正文/UI** | Outfit | 400/500/600/700 |
| **等宽/数字** | JetBrains Mono | 400/500/600 |

```css
--font-sans: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;
```

### 规则

- **禁止** Inter 作为默认字体
- **禁止** Serif 字体（本项目为工具型 SaaS，不是编辑/创意型）
- 数字必须 `font-variant-numeric: tabular-nums`
- 标题 letter-spacing: `-0.01em` 到 `-0.02em`
- UI 标签 letter-spacing: `0.03em` 到 `0.06em`

---

## 5. 圆角

```css
--radius-xs:  4px   (消息角标)
--radius-sm:  6px   (按钮、标签)
--radius-md:  10px  (输入框、卡片内容)
--radius-lg:  14px  (卡片、模态框)
--radius-xl:  20px  (大容器)
--radius-full: 9999px (头像、pill标签)
```

### 规则
- 全项目统一，不允许混用不同的圆角体系
- 按钮/输入框/卡片必须用同一套 radius

---

## 6. 阴影

### 规则
- **禁止** `rgba(0, 0, 0, ...)` 纯黑阴影
- 用带 Slate 色调的阴影
- 深色模式下阴影用更深的透明度

```css
--shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06);
--shadow-md: 0 4px 6px -1px rgba(15, 23, 42, 0.06);
--shadow-lg: 0 10px 15px -3px rgba(15, 23, 42, 0.06);
```

---

## 7. 过渡动画

```css
--transition-fast:   150ms cubic-bezier(0.16, 1, 0.3, 1);
--transition-normal: 250ms cubic-bezier(0.16, 1, 0.3, 1);
--transition-slow:   400ms cubic-bezier(0.16, 1, 0.3, 1);
```

### 规则
- 所有交互元素必须有 transition
- 动画只用 `transform` + `opacity`（GPU 加速）
- **禁止** `window.addEventListener('scroll', ...)`
- **禁止** `top/left/width/height` 动画
- **禁止** 无限循环动画（除 loading skeleton 和状态 pulse dot）

---

## 8. 交互状态

每个交互元素必须覆盖以下 5 态：

| 状态 | 规则 |
|---|---|
| **default** | 正常状态 |
| **hover** | 颜色/背景微变 + `translateY(-1px)` |
| **active** | `transform: scale(0.97)` |
| **focus** | 可见的 focus ring（`var(--shadow-glow)`） |
| **disabled** | `opacity: 0.5` + `cursor: not-allowed` |

---

## 9. 布局规则

- `height: 100vh` → `min-height: 100dvh`（iOS Safari 兼容）
- Grid 优先于 Flexbox 百分比计算
- 容器最大宽度 `max-width: 1240px`（管理后台）或 `max-width: 1400px`（数据看板）
- 移动端 `<768px` 必须显式定义 fallback

---

## 10. 字体图标

- 使用 **Font Awesome 6.4**（已引入）
- **禁止** emoji 作为 UI 图标（emoji 在不同平台渲染不一致）
- 可用文字替代简单状态标记

---

## 11. 内容规范

- **禁止** emoji 出现在代码、标记、文本内容中（聊天内容中的用户表情除外）
- **禁止** AI 文案词："Elevate"、"Seamless"、"Unleash"、"Next-Gen"
- **禁止** 虚假精确数字（如 `99.99%`），用真实数据
- 错误消息直接明确，不用 "Oops!"

---

## 12. 禁止的 AI 设计指纹

| 指纹 | 替代方案 |
|---|---|
| `#4f46e5` AI-purple | `#0d9488` Teal |
| `linear-gradient(135deg, primary, secondary)` | 纯色 `background: var(--primary)` |
| 白色卡片 + border + box-shadow | 减少 border，用 spacing 区分层级 |
| 纯黑透明阴影 | Tinted shadow（Slate 色调） |
| Emoji 作为图标 | Font Awesome |
| Inter 字体 | Outfit |
| Serif 字体 | Sans-serif only |
| `h-screen` | `min-h-[100dvh]` |
| `window.addEventListener('scroll')` | CSS transition / IntersectionObserver |
| `z-index: 9999` | 定义 z-index scale |

---

## 13. 深色模式

- 必须使用 CSS 变量，`[data-theme="dark"]` 选择器
- 每个 hardcoded 颜色必须有 dark variant
- 语义色在 dark mode 下降低饱和度（用 rgba）
- `prefers-color-scheme: dark` 作为自动检测的后备

---

## 14. Pre-Flight Checklist（发布前检查）

- [ ] 页面只用一个 accent color
- [ ] 无 `#000000` / `#ffffff` 硬编码
- [ ] 无 `#4f46e5` 残留
- [ ] 无 emoji 作为 UI 图标
- [ ] 无 `height: 100vh`
- [ ] 所有按钮有 5 态（hover/active/focus/disabled/default）
- [ ] 深色模式所有元素可读
- [ ] 移动端 `<768px` 不破裂
- [ ] 无 `alert()` 调用（用 toast/modal 替代）
- [ ] CSS 变量引用正确（无引用未定义变量）
- [ ] 无 `linear-gradient` 双色按钮

---

*本文件基于 [taste-skill](https://github.com/Leonxlnx/taste-skill) 设计方法论，适用于 SmartCS 项目的所有前端开发。*
