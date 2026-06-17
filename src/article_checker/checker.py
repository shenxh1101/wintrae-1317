import fnmatch
import re
from pathlib import Path
from typing import List, Set, Dict, Optional

from bs4 import BeautifulSoup

from .types import (
    ArticleFile,
    ImageFile,
    Issue,
    IssueType,
    IssueSeverity,
    ScanResult,
)


def _should_ignore(
    file_path: Path,
    base_dir: Path,
    ignore_patterns: Optional[List[str]] = None,
    ignore_files: Optional[List[str]] = None,
) -> bool:
    if not ignore_patterns and not ignore_files:
        return False
    
    try:
        rel_path = file_path.relative_to(base_dir)
        rel_str = str(rel_path).replace('\\', '/')
    except ValueError:
        rel_str = file_path.name
    
    if ignore_files:
        for ig_file in ignore_files:
            ig_path = Path(ig_file)
            try:
                if file_path.resolve() == ig_path.resolve():
                    return True
            except (OSError, FileNotFoundError):
                pass
            if file_path.name == ig_path.name:
                return True
            if str(rel_path) == ig_file or rel_str == ig_file.replace('\\', '/'):
                return True
    
    if ignore_patterns:
        parts = rel_str.split('/')
        for pattern in ignore_patterns:
            pattern = pattern.strip().rstrip('/')
            if not pattern:
                continue
            if fnmatch.fnmatch(rel_str, pattern):
                return True
            if fnmatch.fnmatch(file_path.name, pattern):
                return True
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
            if pattern.rstrip('/') in parts:
                return True
    
    return False


ARTICLE_EXTENSIONS = {".md", ".markdown", ".html", ".htm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
DEFAULT_MAX_IMAGE_SIZE = 2 * 1024 * 1024

TITLE_PATTERNS = [
    re.compile(r'^#\s+(.+)$', re.MULTILINE),
    re.compile(r'^title:\s*(.+)$', re.MULTILINE),
    re.compile(r'<title>\s*(.+?)\s*</title>', re.IGNORECASE | re.DOTALL),
]

COVER_PATTERNS = [
    re.compile(r'^cover:\s*(.+)$', re.MULTILINE),
    re.compile(r'^banner:\s*(.+)$', re.MULTILINE),
    re.compile(r'^image:\s*(.+)$', re.MULTILINE),
]

IMAGE_MD_PATTERN = re.compile(r'!\[.*?\]\((.*?)\)')
IMAGE_HTML_PATTERN = re.compile(r'<img[^>]+src=["\'](.*?)["\']', re.IGNORECASE)
LINK_MD_PATTERN = re.compile(r'\[.*?\]\((.*?)\)')
LINK_HTML_PATTERN = re.compile(r'<a[^>]+href=["\'](.*?)["\']', re.IGNORECASE)


def _extract_title(content: str) -> str:
    for pattern in TITLE_PATTERNS:
        match = pattern.search(content)
        if match:
            title = match.group(1).strip()
            if title:
                return title
    return ""


def _extract_cover(content: str) -> str:
    for pattern in COVER_PATTERNS:
        match = pattern.search(content)
        if match:
            cover = match.group(1).strip()
            if cover:
                return cover
    return ""


def _extract_referenced_images(content: str) -> List[str]:
    images: Set[str] = set()
    
    for pattern in COVER_PATTERNS:
        for match in pattern.finditer(content):
            img = match.group(1).strip()
            if img and not img.startswith(('http://', 'https://')):
                img = img.strip('"\'')
                images.add(Path(img).name)
    
    for match in IMAGE_MD_PATTERN.finditer(content):
        img = match.group(1).strip()
        if img and not img.startswith(('http://', 'https://')):
            images.add(Path(img).name)
    for match in IMAGE_HTML_PATTERN.finditer(content):
        img = match.group(1).strip()
        if img and not img.startswith(('http://', 'https://')):
            images.add(Path(img).name)
    return list(images)


_TRAILING_PUNCTUATION = (
    '.,;!?)"\'）》」』】〕〗〙〛"',
    '。，；！？）、"',
)


def _clean_link(link: str) -> str:
    link = link.strip()
    changed = True
    while changed:
        changed = False
        for punct_set in _TRAILING_PUNCTUATION:
            for ch in punct_set:
                if link.endswith(ch):
                    link = link[:-1]
                    changed = True
                    break
            if changed:
                break
    
    if link.endswith(')') and '(' not in link:
        link = link[:-1]
    
    if link.endswith('）') and '（' not in link:
        link = link[:-1]
    
    return link.strip()


def _extract_links(content: str) -> List[str]:
    links: Set[str] = set()
    for match in LINK_MD_PATTERN.finditer(content):
        link = _clean_link(match.group(1))
        if link:
            links.add(link)
    for match in LINK_HTML_PATTERN.finditer(content):
        link = _clean_link(match.group(1))
        if link:
            links.add(link)
    for match in re.finditer(r'https?://[^\s<>"\"\']+', content):
        link = _clean_link(match.group(0))
        if link:
            links.add(link)
    return list(links)


def _parse_article(file_path: Path) -> ArticleFile:
    content = file_path.read_text(encoding='utf-8', errors='ignore')
    article = ArticleFile(
        path=file_path,
        title=_extract_title(content),
        content=content,
        referenced_images=_extract_referenced_images(content),
        referenced_links=_extract_links(content),
        has_cover=bool(_extract_cover(content)),
    )
    return article


def _parse_image(file_path: Path) -> ImageFile:
    return ImageFile(
        path=file_path,
        size_bytes=file_path.stat().st_size,
        is_referenced=False,
    )


def _find_duplicate_filenames(
    articles: List[ArticleFile], images: List[ImageFile]
) -> List[Issue]:
    issues: List[Issue] = []
    filename_counts: Dict[str, List[Path]] = {}

    for article in articles:
        name = article.path.name
        filename_counts.setdefault(name, []).append(article.path)

    for image in images:
        name = image.path.name
        filename_counts.setdefault(name, []).append(image.path)

    for name, paths in filename_counts.items():
        if len(paths) > 1:
            issues.append(Issue(
                type=IssueType.DUPLICATE_FILENAME,
                severity=IssueSeverity.WARNING,
                message=f"发现重复文件名: {name}",
                details={"paths": [str(p) for p in paths]},
            ))

    return issues


def _find_large_images(
    images: List[ImageFile], max_size: int
) -> List[Issue]:
    issues: List[Issue] = []
    for image in images:
        if image.size_bytes > max_size:
            size_mb = image.size_bytes / (1024 * 1024)
            issues.append(Issue(
                type=IssueType.LARGE_IMAGE,
                severity=IssueSeverity.WARNING,
                message=f"图片过大: {image.path.name} ({size_mb:.2f} MB)",
                file_path=image.path,
                details={"size_bytes": image.size_bytes, "size_mb": size_mb},
            ))
    return issues


def _find_empty_titles(articles: List[ArticleFile]) -> List[Issue]:
    issues: List[Issue] = []
    for article in articles:
        if not article.title:
            issues.append(Issue(
                type=IssueType.EMPTY_TITLE,
                severity=IssueSeverity.ERROR,
                message=f"文章标题为空: {article.path.name}",
                file_path=article.path,
            ))
    return issues


def _find_missing_covers(articles: List[ArticleFile]) -> List[Issue]:
    issues: List[Issue] = []
    for article in articles:
        if not article.has_cover:
            issues.append(Issue(
                type=IssueType.MISSING_COVER,
                severity=IssueSeverity.WARNING,
                message=f"缺少封面图: {article.path.name}",
                file_path=article.path,
            ))
    return issues


def _find_unused_materials(
    articles: List[ArticleFile], images: List[ImageFile]
) -> List[Issue]:
    issues: List[Issue] = []
    referenced_images: Set[str] = set()

    for article in articles:
        referenced_images.update(article.referenced_images)

    for image in images:
        image_name = image.path.name
        if image_name not in referenced_images:
            image.is_referenced = False
            issues.append(Issue(
                type=IssueType.UNUSED_MATERIAL,
                severity=IssueSeverity.INFO,
                message=f"未引用的素材: {image_name}",
                file_path=image.path,
            ))
        else:
            image.is_referenced = True

    return issues


def scan(
    article_dir: Path,
    image_dir: Path,
    max_image_size: int = DEFAULT_MAX_IMAGE_SIZE,
    ignore_patterns: Optional[List[str]] = None,
    ignore_files: Optional[List[str]] = None,
) -> ScanResult:
    article_dir = Path(article_dir)
    image_dir = Path(image_dir)

    articles: List[ArticleFile] = []
    images: List[ImageFile] = []

    if article_dir.exists():
        for file_path in article_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in ARTICLE_EXTENSIONS:
                if _should_ignore(file_path, article_dir, ignore_patterns, ignore_files):
                    continue
                articles.append(_parse_article(file_path))

    if image_dir.exists():
        for file_path in image_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
                if _should_ignore(file_path, image_dir, ignore_patterns, ignore_files):
                    continue
                images.append(_parse_image(file_path))

    issues: List[Issue] = []
    issues.extend(_find_duplicate_filenames(articles, images))
    issues.extend(_find_large_images(images, max_image_size))
    issues.extend(_find_empty_titles(articles))
    issues.extend(_find_missing_covers(articles))
    issues.extend(_find_unused_materials(articles, images))

    return ScanResult(
        articles=articles,
        images=images,
        issues=issues,
    )


def get_all_links(scan_result: ScanResult) -> List[str]:
    links: Set[str] = set()
    for article in scan_result.articles:
        links.update(article.referenced_links)
    return [link for link in links if link.startswith(('http://', 'https://'))]
