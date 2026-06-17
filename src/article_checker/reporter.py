import json
import sys
from datetime import datetime
from pathlib import Path
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
