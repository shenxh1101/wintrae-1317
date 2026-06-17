import json
import sys
from datetime import datetime
from pathlib import Path
from string import Template
from typing import List, Dict, Optional

from .types import (
    Issue,
    IssueType,
    IssueSeverity,
    ScanResult,
)


def _supports_unicode() -> bool:
    try:
        encoding = getattr(sys.stdout, 'encoding', None)
        if encoding:
            "❌".encode(encoding)
            return True
    except (UnicodeEncodeError, LookupError, AttributeError):
        pass
    return False


_UNICODE_SUPPORTED = _supports_unicode()

SEVERITY_ICONS = {
    IssueSeverity.ERROR: "❌" if _UNICODE_SUPPORTED else "[ERROR]",
    IssueSeverity.WARNING: "⚠️" if _UNICODE_SUPPORTED else "[WARN]",
    IssueSeverity.INFO: "ℹ️" if _UNICODE_SUPPORTED else "[INFO]",
}

SEVERITY_ICONS_SIMPLE = {
    IssueSeverity.ERROR: "[ERROR]",
    IssueSeverity.WARNING: "[WARN]",
    IssueSeverity.INFO: "[INFO]",
}

ISSUE_TYPE_LABELS = {
    IssueType.MISSING_COVER: "缺失封面",
    IssueType.DUPLICATE_FILENAME: "重复文件名",
    IssueType.LARGE_IMAGE: "过大图片",
    IssueType.UNUSED_MATERIAL: "未引用素材",
    IssueType.BAD_LINK: "错误链接",
    IssueType.EMPTY_TITLE: "空标题",
}


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def _group_issues_by_type(issues: List[Issue]) -> Dict[IssueType, List[Issue]]:
    grouped: Dict[IssueType, List[Issue]] = {}
    for issue in issues:
        grouped.setdefault(issue.type, []).append(issue)
    return grouped


def _group_issues_by_severity(issues: List[Issue]) -> Dict[IssueSeverity, List[Issue]]:
    grouped: Dict[IssueSeverity, List[Issue]] = {}
    for issue in issues:
        grouped.setdefault(issue.severity, []).append(issue)
    return grouped


def generate_text_report(
    scan_result: ScanResult,
    output_path: Optional[Path] = None,
    link_issues: Optional[List[Issue]] = None,
) -> str:
    all_issues = scan_result.issues.copy()
    if link_issues:
        all_issues.extend(link_issues)
    
    by_type = _group_issues_by_type(all_issues)
    by_severity = _group_issues_by_severity(all_issues)
    
    total_images_size = sum(img.size_bytes for img in scan_result.images)
    referenced_images = [img for img in scan_result.images if img.is_referenced]
    unused_images = [img for img in scan_result.images if not img.is_referenced]
    
    lines = []
    lines.append("=" * 80)
    lines.append("文章素材包检查报告")
    lines.append("=" * 80)
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    lines.append("【检查摘要】")
    lines.append("-" * 80)
    lines.append(f"文章数量: {len(scan_result.articles)}")
    lines.append(f"图片数量: {len(scan_result.images)}")
    lines.append(f"  已引用: {len(referenced_images)}")
    lines.append(f"  未引用: {len(unused_images)}")
    lines.append(f"图片总大小: {_format_size(total_images_size)}")
    lines.append("")
    lines.append(f"问题总数: {len(all_issues)}")
    lines.append(f"  错误: {len(by_severity.get(IssueSeverity.ERROR, []))}")
    lines.append(f"  警告: {len(by_severity.get(IssueSeverity.WARNING, []))}")
    lines.append(f"  提示: {len(by_severity.get(IssueSeverity.INFO, []))}")
    lines.append("")
    
    for issue_type in IssueType:
        count = len(by_type.get(issue_type, []))
        if count > 0:
            lines.append(f"  {ISSUE_TYPE_LABELS[issue_type]}: {count}")
    
    lines.append("")
    lines.append("【问题清单】")
    lines.append("-" * 80)
    
    for severity in [IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO]:
        severity_issues = by_severity.get(severity, [])
        if severity_issues:
            lines.append("")
            lines.append(f"{SEVERITY_ICONS[severity]} {severity.value.upper()} ({len(severity_issues)}):")
            for i, issue in enumerate(severity_issues, 1):
                file_info = f" [{issue.file_path}]" if issue.file_path else ""
                lines.append(f"  {i}. {issue.message}{file_info}")
                if issue.details:
                    if "paths" in issue.details:
                        for p in issue.details["paths"]:
                            lines.append(f"     - {p}")
                    if "articles" in issue.details:
                        lines.append(f"     出现于:")
                        for p in issue.details["articles"]:
                            lines.append(f"       - {p}")
                    if "size_mb" in issue.details:
                        lines.append(f"     大小: {issue.details['size_mb']:.2f} MB")
                    if "url" in issue.details:
                        lines.append(f"     URL: {issue.details['url']}")
    
    check_ok = "[OK]" if _UNICODE_SUPPORTED else "[OK]"
    check_bad = "[X]" if _UNICODE_SUPPORTED else "[X]"
    
    lines.append("")
    lines.append("【文件清单 - 可复核】")
    lines.append("-" * 80)
    
    lines.append("")
    lines.append("文章文件:")
    for i, article in enumerate(scan_result.articles, 1):
        status = check_ok if article.title and article.has_cover else check_bad
        lines.append(f"  {status} {i}. {article.path}")
        if article.title:
            lines.append(f"     标题: {article.title}")
        lines.append(f"     引用图片: {len(article.referenced_images)} 张")
        lines.append(f"     外部链接: {len(article.referenced_links)} 个")
        lines.append(f"     封面: {'已设置' if article.has_cover else '未设置'}")
    
    lines.append("")
    lines.append("图片文件:")
    for i, image in enumerate(scan_result.images, 1):
        status = check_ok if image.is_referenced else check_bad
        lines.append(
            f"  {status} {i}. {image.path} "
            f"({_format_size(image.size_bytes)})"
        )
    
    lines.append("")
    lines.append("=" * 80)
    
    report = "\n".join(lines)
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding='utf-8')
    
    return report


def generate_json_report(
    scan_result: ScanResult,
    output_path: Optional[Path] = None,
    link_issues: Optional[List[Issue]] = None,
) -> str:
    all_issues = scan_result.issues.copy()
    if link_issues:
        all_issues.extend(link_issues)
    
    by_type = _group_issues_by_type(all_issues)
    by_severity = _group_issues_by_severity(all_issues)
    
    referenced_images = [img for img in scan_result.images if img.is_referenced]
    unused_images = [img for img in scan_result.images if not img.is_referenced]
    
    data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "article_count": len(scan_result.articles),
            "image_count": len(scan_result.images),
            "referenced_image_count": len(referenced_images),
            "unused_image_count": len(unused_images),
            "total_image_size_bytes": sum(img.size_bytes for img in scan_result.images),
            "total_issues": len(all_issues),
            "issues_by_severity": {
                k.value: len(v) for k, v in by_severity.items()
            },
            "issues_by_type": {
                k.value: len(v) for k, v in by_type.items()
            },
        },
        "issues": [
            {
                "type": issue.type.value,
                "severity": issue.severity.value,
                "message": issue.message,
                "file_path": str(issue.file_path) if issue.file_path else None,
                "details": issue.details,
            }
            for issue in all_issues
        ],
        "articles": [
            {
                "path": str(article.path),
                "title": article.title,
                "has_cover": article.has_cover,
                "referenced_images": article.referenced_images,
                "referenced_links": article.referenced_links,
            }
            for article in scan_result.articles
        ],
        "images": [
            {
                "path": str(image.path),
                "size_bytes": image.size_bytes,
                "is_referenced": image.is_referenced,
            }
            for image in scan_result.images
        ],
    }
    
    report = json.dumps(data, ensure_ascii=False, indent=2)
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding='utf-8')
    
    return report


def print_console_summary(
    scan_result: ScanResult,
    link_issues: Optional[List[Issue]] = None,
) -> None:
    all_issues = scan_result.issues.copy()
    if link_issues:
        all_issues.extend(link_issues)
    
    by_severity = _group_issues_by_severity(all_issues)
    
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)
    print(f"文章: {len(scan_result.articles)} 篇")
    print(f"图片: {len(scan_result.images)} 张")
    print(f"问题: {len(all_issues)} 个")
    print(f"  {SEVERITY_ICONS[IssueSeverity.ERROR]} 错误: {len(by_severity.get(IssueSeverity.ERROR, []))}")
    print(f"  {SEVERITY_ICONS[IssueSeverity.WARNING]} 警告: {len(by_severity.get(IssueSeverity.WARNING, []))}")
    print(f"  {SEVERITY_ICONS[IssueSeverity.INFO]} 提示: {len(by_severity.get(IssueSeverity.INFO, []))}")
    print("=" * 60 + "\n")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文章素材包检查报告</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 24px;
        }
        header h1 { font-size: 24px; margin-bottom: 8px; }
        header .meta { opacity: 0.9; font-size: 14px; }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .summary-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        .summary-card .label { color: #888; font-size: 14px; margin-bottom: 8px; }
        .summary-card .value { font-size: 32px; font-weight: bold; }
        .summary-card.error .value { color: #e74c3c; }
        .summary-card.warning .value { color: #f39c12; }
        .summary-card.info .value { color: #3498db; }
        .summary-card.articles .value { color: #27ae60; }
        .summary-card.images .value { color: #9b59b6; }
        
        .filter-bar {
            background: white;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
        }
        .filter-bar label { font-size: 14px; color: #666; }
        .filter-btn {
            padding: 8px 16px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        .filter-btn:hover { border-color: #667eea; color: #667eea; }
        .filter-btn.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }
        .filter-btn.error.active { background: #e74c3c; border-color: #e74c3c; }
        .filter-btn.warning.active { background: #f39c12; border-color: #f39c12; }
        .filter-btn.info.active { background: #3498db; border-color: #3498db; }
        
        .search-box {
            flex: 1;
            min-width: 200px;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
        }
        .search-box:focus { outline: none; border-color: #667eea; }
        
        .section {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        .section h2 {
            font-size: 18px;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #eee;
        }
        
        .issue-list { list-style: none; }
        .issue-item {
            padding: 14px 16px;
            border-left: 4px solid #ddd;
            margin-bottom: 10px;
            background: #fafafa;
            border-radius: 0 8px 8px 0;
            transition: background 0.2s;
        }
        .issue-item:hover { background: #f0f0f0; }
        .issue-item.error { border-left-color: #e74c3c; }
        .issue-item.warning { border-left-color: #f39c12; }
        .issue-item.info { border-left-color: #3498db; }
        
        .issue-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .issue-type {
            font-size: 12px;
            padding: 2px 8px;
            border-radius: 4px;
            color: white;
            font-weight: 500;
        }
        .issue-type.error { background: #e74c3c; }
        .issue-type.warning { background: #f39c12; }
        .issue-type.info { background: #3498db; }
        .issue-message { font-weight: 500; }
        .issue-file {
            font-size: 13px;
            color: #888;
            margin-top: 4px;
        }
        .issue-file a {
            color: #667eea;
            text-decoration: none;
        }
        .issue-file a:hover { text-decoration: underline; }
        .issue-details {
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px dashed #eee;
            font-size: 13px;
            color: #666;
        }
        .issue-details ul { margin-left: 20px; margin-top: 4px; }
        
        .file-section { margin-bottom: 20px; }
        .file-section h3 {
            font-size: 16px;
            margin-bottom: 12px;
            color: #555;
        }
        .file-list { list-style: none; }
        .file-item {
            padding: 10px 14px;
            border-radius: 6px;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: background 0.2s;
        }
        .file-item:hover { background: #f5f5f5; }
        .file-status {
            width: 20px;
            text-align: center;
            font-weight: bold;
        }
        .file-status.ok { color: #27ae60; }
        .file-status.bad { color: #e74c3c; }
        .file-item a {
            color: #333;
            text-decoration: none;
            flex: 1;
        }
        .file-item a:hover { color: #667eea; text-decoration: underline; }
        .file-size { color: #999; font-size: 13px; }
        
        .tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 16px;
            border-bottom: 2px solid #eee;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            font-size: 14px;
            color: #666;
            transition: all 0.2s;
        }
        .tab:hover { color: #667eea; }
        .tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
            font-weight: 500;
        }
        
        .hidden { display: none; }
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📋 文章素材包检查报告</h1>
            <div class="meta">生成时间: $generated_at</div>
        </header>
        
        <div class="summary-grid">
            <div class="summary-card articles">
                <div class="label">文章数量</div>
                <div class="value">$article_count</div>
            </div>
            <div class="summary-card images">
                <div class="label">图片数量</div>
                <div class="value">$image_count</div>
            </div>
            <div class="summary-card error">
                <div class="label">错误</div>
                <div class="value">$error_count</div>
            </div>
            <div class="summary-card warning">
                <div class="label">警告</div>
                <div class="value">$warning_count</div>
            </div>
            <div class="summary-card info">
                <div class="label">提示</div>
                <div class="value">$info_count</div>
            </div>
        </div>
        
        <div class="filter-bar">
            <label>筛选:</label>
            <button class="filter-btn active" data-filter="all">全部 ($total_issues)</button>
            <button class="filter-btn error" data-filter="error">错误 ($error_count)</button>
            <button class="filter-btn warning" data-filter="warning">警告 ($warning_count)</button>
            <button class="filter-btn info" data-filter="info">提示 ($info_count)</button>
            <input type="text" class="search-box" placeholder="搜索问题..." id="searchInput">
        </div>
        
        <div class="section">
            <h2>问题清单</h2>
            <div class="issue-list" id="issueList">
                $issue_items_html
            </div>
            <div class="empty-state hidden" id="emptyState">没有找到匹配的问题</div>
        </div>
        
        <div class="section">
            <div class="tabs">
                <div class="tab active" data-tab="articles">文章文件 ($article_count)</div>
                <div class="tab" data-tab="images">图片文件 ($image_count)</div>
            </div>
            <div class="tab-content" id="tab-articles">
                <div class="file-list">
                    $article_items_html
                </div>
            </div>
            <div class="tab-content hidden" id="tab-images">
                <div class="file-list">
                    $image_items_html
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // 筛选功能
        const filterBtns = document.querySelectorAll('.filter-btn');
        const issueItems = document.querySelectorAll('.issue-item');
        const searchInput = document.getElementById('searchInput');
        const emptyState = document.getElementById('emptyState');
        const issueList = document.getElementById('issueList');
        
        let currentFilter = 'all';
        let currentSearch = '';
        
        function applyFilters() {
            let visibleCount = 0;
            
            issueItems.forEach(item => {
                const severity = item.dataset.severity;
                const message = item.dataset.message.toLowerCase();
                const matchesFilter = currentFilter === 'all' || severity === currentFilter;
                const matchesSearch = currentSearch === '' || message.includes(currentSearch);
                
                if (matchesFilter && matchesSearch) {
                    item.classList.remove('hidden');
                    visibleCount++;
                } else {
                    item.classList.add('hidden');
                }
            });
            
            if (visibleCount === 0) {
                emptyState.classList.remove('hidden');
                issueList.classList.add('hidden');
            } else {
                emptyState.classList.add('hidden');
                issueList.classList.remove('hidden');
            }
        }
        
        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentFilter = btn.dataset.filter;
                applyFilters();
            });
        });
        
        searchInput.addEventListener('input', (e) => {
            currentSearch = e.target.value.toLowerCase();
            applyFilters();
        });
        
        // Tab 切换
        const tabs = document.querySelectorAll('.tab');
        const tabContents = document.querySelectorAll('.tab-content');
        
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                const tabName = tab.dataset.tab;
                tabContents.forEach(content => {
                    content.classList.add('hidden');
                });
                document.getElementById('tab-' + tabName).classList.remove('hidden');
            });
        });
    </script>
</body>
</html>"""


def _file_uri(path: Path) -> str:
    return f"file:///{path.resolve().as_posix()}"


def generate_html_report(
    scan_result: ScanResult,
    output_path: Optional[Path] = None,
    link_issues: Optional[List[Issue]] = None,
) -> str:
    all_issues = scan_result.issues.copy()
    if link_issues:
        all_issues.extend(link_issues)
    
    by_severity = _group_issues_by_severity(all_issues)
    by_type = _group_issues_by_type(all_issues)
    
    issue_items_html = ""
    for issue in all_issues:
        severity = issue.severity.value
        type_label = ISSUE_TYPE_LABELS.get(issue.type, issue.type.value)
        file_link = ""
        if issue.file_path:
            file_link = f'<div class="issue-file">文件: <a href="{_file_uri(issue.file_path)}" target="_blank">{issue.file_path}</a></div>'
        
        details_html = ""
        if issue.details:
            detail_parts = []
            if "paths" in issue.details:
                paths_list = "".join(f"<li>{p}</li>" for p in issue.details["paths"])
                detail_parts.append(f"<div>相关文件:<ul>{paths_list}</ul></div>")
            if "articles" in issue.details:
                articles_list = "".join(f"<li>{a}</li>" for a in issue.details["articles"])
                detail_parts.append(f"<div>出现于:<ul>{articles_list}</ul></div>")
            if "size_mb" in issue.details:
                detail_parts.append(f"<div>大小: {issue.details['size_mb']:.2f} MB</div>")
            if "url" in issue.details:
                detail_parts.append(f'<div>URL: <a href="{issue.details["url"]}" target="_blank">{issue.details["url"]}</a></div>')
            if detail_parts:
                details_html = f'<div class="issue-details">{"".join(detail_parts)}</div>'
        
        issue_items_html += f'''
            <li class="issue-item {severity}" data-severity="{severity}" data-message="{issue.message}">
                <div class="issue-header">
                    <span class="issue-message">{issue.message}</span>
                    <span class="issue-type {severity}">{type_label}</span>
                </div>
                {file_link}
                {details_html}
            </li>
        '''
    
    article_items_html = ""
    for i, article in enumerate(scan_result.articles, 1):
        is_ok = article.title and article.has_cover
        status_class = "ok" if is_ok else "bad"
        status_icon = "✓" if is_ok else "✗"
        article_items_html += f'''
            <li class="file-item">
                <span class="file-status {status_class}">{status_icon}</span>
                <a href="{_file_uri(article.path)}" target="_blank">{article.path}</a>
                <span class="file-size">{len(article.referenced_images)} 张图片</span>
            </li>
        '''
    
    image_items_html = ""
    for i, image in enumerate(scan_result.images, 1):
        is_ok = image.is_referenced
        status_class = "ok" if is_ok else "bad"
        status_icon = "✓" if is_ok else "✗"
        size_str = _format_size(image.size_bytes)
        image_items_html += f'''
            <li class="file-item">
                <span class="file-status {status_class}">{status_icon}</span>
                <a href="{_file_uri(image.path)}" target="_blank">{image.path}</a>
                <span class="file-size">{size_str}</span>
            </li>
        '''
    
    error_count = len(by_severity.get(IssueSeverity.ERROR, []))
    warning_count = len(by_severity.get(IssueSeverity.WARNING, []))
    info_count = len(by_severity.get(IssueSeverity.INFO, []))
    
    from datetime import datetime
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    template = Template(HTML_TEMPLATE)
    html = template.substitute(
        generated_at=generated_at,
        article_count=len(scan_result.articles),
        image_count=len(scan_result.images),
        total_issues=len(all_issues),
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        issue_items_html=issue_items_html,
        article_items_html=article_items_html,
        image_items_html=image_items_html,
    )
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding='utf-8')
    
    return html
