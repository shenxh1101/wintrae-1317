import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from .types import ArticleFile, ImageFile


INVALID_CHARS_PATTERN = re.compile(r'[\\/:*?"<>|\s]+')
DATE_PATTERN = re.compile(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})')
CATEGORY_PATTERNS = [
    re.compile(r'^category:\s*(.+)$', re.MULTILINE),
    re.compile(r'^tags:\s*\[(.+?)\]', re.MULTILINE),
    re.compile(r'^section:\s*(.+)$', re.MULTILINE),
]


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = INVALID_CHARS_PATTERN.sub('-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def _extract_date(content: str, file_path: Path) -> str:
    match = DATE_PATTERN.search(content)
    if match:
        year, month, day = match.groups()
        return f"{year}{month}{day}"
    
    match = DATE_PATTERN.search(file_path.name)
    if match:
        year, month, day = match.groups()
        return f"{year}{month}{day}"
    
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
    return mtime.strftime("%Y%m%d")


def _extract_category(content: str, default: str = "general") -> str:
    for pattern in CATEGORY_PATTERNS:
        match = pattern.search(content)
        if match:
            category = match.group(1).strip()
            if category:
                return _slugify(category.split(',')[0])
    return default


def _extract_title_for_rename(article: ArticleFile) -> str:
    if article.title:
        return _slugify(article.title)
    
    stem = article.path.stem
    stem = DATE_PATTERN.sub('', stem)
    return _slugify(stem) or "untitled"


def _generate_new_name(
    article: ArticleFile,
    use_date: bool = True,
    use_category: bool = True,
    custom_prefix: Optional[str] = None,
) -> str:
    parts = []
    
    if custom_prefix:
        parts.append(_slugify(custom_prefix))
    else:
        if use_date:
            date_str = _extract_date(article.content, article.path)
            parts.append(date_str)
        
        if use_category:
            category = _extract_category(article.content)
            parts.append(category)
    
    title_slug = _extract_title_for_rename(article)
    parts.append(title_slug)
    
    return '-'.join(parts) + article.path.suffix.lower()


def _update_references(
    article: ArticleFile,
    old_name: str,
    new_name: str,
    image_dir: Path,
) -> str:
    content = article.content
    
    old_stem = Path(old_name).stem
    new_stem = Path(new_name).stem
    
    for image_path in image_dir.rglob("*"):
        if image_path.is_file() and image_path.stem == old_stem:
            old_ref = image_path.name
            new_ref = f"{new_stem}{image_path.suffix.lower()}"
            content = content.replace(old_ref, new_ref)
    
    return content


def rename_articles(
    articles: List[ArticleFile],
    image_dir: Path,
    output_dir: Path,
    use_date: bool = True,
    use_category: bool = True,
    custom_prefix: Optional[str] = None,
    dry_run: bool = False,
) -> List[Tuple[Path, Path, bool]]:
    output_dir = Path(output_dir)
    image_dir = Path(image_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results: List[Tuple[Path, Path, bool]] = []
    used_names: set = set()
    
    for article in articles:
        new_name = _generate_new_name(
            article, use_date, use_category, custom_prefix
        )
        
        counter = 1
        base_name = new_name
        while new_name in used_names:
            stem = Path(base_name).stem
            suffix = Path(base_name).suffix
            new_name = f"{stem}-{counter}{suffix}"
            counter += 1
        
        used_names.add(new_name)
        
        old_path = article.path
        new_path = output_dir / new_name
        
        if not dry_run:
            updated_content = _update_references(
                article, old_path.name, new_name, image_dir
            )
            new_path.write_text(updated_content, encoding='utf-8')
        
        results.append((old_path, new_path, dry_run))
    
    return results


def rename_images(
    images: List[ImageFile],
    output_dir: Path,
    article_dir: Path,
    use_date: bool = True,
    use_category: bool = True,
    custom_prefix: Optional[str] = None,
    dry_run: bool = False,
) -> List[Tuple[Path, Path, bool]]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results: List[Tuple[Path, Path, bool]] = []
    used_names: set = set()
    
    for image in images:
        if not image.is_referenced:
            continue
        
        parts = []
        
        if custom_prefix:
            parts.append(_slugify(custom_prefix))
        
        stem = _slugify(image.path.stem)
        parts.append(stem)
        
        new_name = '-'.join(parts) + image.path.suffix.lower()
        
        counter = 1
        base_name = new_name
        while new_name in used_names:
            stem_part = Path(base_name).stem
            suffix = Path(base_name).suffix
            new_name = f"{stem_part}-{counter}{suffix}"
            counter += 1
        
        used_names.add(new_name)
        
        old_path = image.path
        new_path = output_dir / new_name
        
        if not dry_run:
            shutil.copy2(old_path, new_path)
        
        results.append((old_path, new_path, dry_run))
    
    return results
