# Article Checker - 文章素材包检查工具

文章发布前素材包批量检查命令行工具，帮助内容编辑快速整理和检查发布前的文章素材。

## 功能特性

- **scan** - 扫描文章和图片，自动识别六类问题
- **rename** - 按日期与栏目统一命名文件
- **check-links** - 批量检查外部链接有效性
- **compress** - 批量压缩图片并保留原文件
- **report** - 输出检查摘要、问题清单和可复核文件路径

### 自动识别的问题

| 问题类型 | 严重程度 | 说明 |
|---------|---------|------|
| 缺失封面 | ⚠️ 警告 | 文章未设置 cover/banner/image 字段 |
| 重复文件名 | ⚠️ 警告 | 不同路径下存在相同文件名 |
| 过大图片 | ⚠️ 警告 | 图片超过设定大小阈值（默认2MB） |
| 未引用素材 | ℹ️ 提示 | 图片目录中存在未被文章引用的文件 |
| 错误链接 | ❌ 错误 | 外部链接无法访问或返回错误状态码 |
| 空标题 | ❌ 错误 | 文章未提取到有效标题 |

## 安装

```bash
# 克隆项目后，在项目根目录执行
pip install -e .
```

或直接安装依赖：

```bash
pip install click pillow requests beautifulsoup4 python-dotenv
```

## 快速开始

```bash
# 查看帮助
article-checker --help

# 基本扫描
article-checker -a ./articles -i ./images scan

# 完整工作流示例
article-checker -a ./articles -i ./images -o ./output scan report --format both --include-links
```

## 命令详解

### 全局选项

```
--article-dir, -a   文章目录（支持 .md, .markdown, .html, .htm）
--image-dir, -i     图片目录（支持 .jpg, .jpeg, .png, .gif, .webp, .bmp, .svg）
--output-dir, -o    输出目录（默认: ./output）
```

### 1. scan - 扫描检查

```bash
article-checker -a ./articles -i ./images scan [OPTIONS]
```

**选项：**
- `--max-image-size` 最大图片大小（字节，默认 2097152 = 2MB）

**示例：**
```bash
# 使用 5MB 作为大图阈值
article-checker -a ./articles -i ./images scan --max-image-size 5242880
```

### 2. rename - 统一命名

```bash
article-checker -a ./articles -i ./images rename [OPTIONS]
```

**选项：**
- `--no-date` 不使用日期前缀
- `--no-category` 不使用栏目前缀
- `--prefix` 自定义文件名前缀
- `--dry-run` 仅预览，不实际执行

**命名规则：**
```
[日期]-[栏目]-[标题].md
示例: 20240115-tech-python-introduction.md
```

**示例：**
```bash
# 预览重命名效果
article-checker -a ./articles -i ./images rename --dry-run

# 使用自定义前缀
article-checker -a ./articles -i ./images rename --prefix 2024q1
```

### 3. check-links - 链接检查

```bash
article-checker -a ./articles -i ./images check-links [OPTIONS]
```

**选项：**
- `--timeout` 请求超时时间（秒，默认 10）
- `--max-workers` 最大并发数（默认 10）
- `--retry-count` 重试次数（默认 2）
- `--no-verify-ssl` 不验证 SSL 证书

**示例：**
```bash
# 宽松模式检查
article-checker -a ./articles -i ./images check-links --timeout 20 --retry-count 3 --no-verify-ssl
```

### 4. compress - 图片压缩

```bash
article-checker -a ./articles -i ./images compress [OPTIONS]
```

**选项：**
- `--quality` 压缩质量 1-100（默认 80）
- `--max-width` 最大宽度（默认 1920）
- `--max-height` 最大高度（默认 1080）
- `--only-large` 仅压缩超过阈值的图片
- `--large-threshold` 大图片阈值（字节，默认 2097152）
- `--overwrite` 覆盖原文件（不添加 _compressed 后缀）

**示例：**
```bash
# 仅压缩大于 2MB 的图片
article-checker -a ./articles -i ./images compress --only-large

# 高质量压缩
article-checker -a ./articles -i ./images compress --quality 90
```

### 5. report - 生成报告

```bash
article-checker -a ./articles -i ./images report [OPTIONS]
```

**选项：**
- `--format, -f` 报告格式：text/json/both（默认 text）
- `--filename` 报告文件名（不含扩展名，默认 report）
- `--include-links` 在报告中包含链接检查结果

**示例：**
```bash
# 生成完整报告（包含链接检查）
article-checker -a ./articles -i ./images report --format both --include-links

# 先扫描再生成报告（避免重复扫描）
article-checker -a ./articles -i ./images scan report
```

## 报告格式

### 文本报告 (report.txt)

包含以下章节：
1. **检查摘要** - 统计文章、图片、问题数量
2. **问题清单** - 按严重程度分组列出所有问题
3. **文件清单** - 可复核的文章和图片完整列表

### JSON 报告 (report.json)

结构化数据，便于程序处理：
```json
{
  "generated_at": "2024-01-15T10:30:00",
  "summary": { ... },
  "issues": [ ... ],
  "articles": [ ... ],
  "images": [ ... ]
}
```

## 目录结构示例

```
project/
├── articles/
│   ├── post1.md
│   ├── post2.md
│   └── tech/
│       └── post3.md
├── images/
│   ├── cover1.jpg
│   ├── image1.png
│   └── unused.jpg
└── output/
    ├── report.txt
    ├── report.json
    ├── compressed_images/
    │   └── cover1_compressed.jpg
    └── renamed_articles/
        └── 20240115-general-post1.md
```

## 文章 front-matter 支持

工具可识别以下 front-matter 字段：

```yaml
---
title: 文章标题
date: 2024-01-15
category: tech
tags: [python, tutorial]
cover: /images/cover.jpg
banner: /images/banner.jpg
image: /images/feature.jpg
---
```

## 退出码

- `0` - 执行成功，无严重错误
- `1` - 参数错误或执行失败

## License

MIT
