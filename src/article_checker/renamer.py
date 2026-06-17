import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from .types import ArticleFile, ImageFile


INVALID_CHARS_PATTERN = re.compile(r'[\\/:*?"<>|\s]+')
DATE_PATTERN = re.compile(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})')
CATEGORY_PATTERNS = [
    re.compile(r'^category:\s*(.+)$', re.MULTILINE),
    re.compile(r'^tags:\s*\[(.+?)\]', re.MULTILINE),
    re.compile(r'^section:\s*(.+)$', re.MULTILINE),
]

IMAGE_MD_PATTERN = re.compile(r'!\[.*?\]\((.*?)\)')
IMAGE_HTML_PATTERN = re.compile(r'<img[^>]+src=["\'](.*?)["\']', re.IGNORECASE)
COVER_PATTERNS = [
    re.compile(r'^(cover:\s*)(.+)$', re.MULTILINE),
    re.compile(r'^(banner:\s*)(.+)$', re.MULTILINE),
    re.compile(r'^(image:\s*)(.+)$', re.MULTILINE),
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


def _generate_article_new_name(
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


def _generate_image_new_name(
    image: ImageFile,
    custom_prefix: Optional[str] = None,
) -> str:
    parts = []
    
    if custom_prefix:
        parts.append(_slugify(custom_prefix))
    
    stem = _slugify(image.path.stem)
    parts.append(stem)
    
    return '-'.join(parts) + image.path.suffix.lower()


def build_image_name_map(
    images: List[ImageFile],
    custom_prefix: Optional[str] = None,
) -> Dict[Path, Path]:
    name_map: Dict[Path, Path] = {}
    used_names: set = set()
    
    for image in images:
        if not image.is_referenced:
            continue
        
        new_name = _generate_image_new_name(image, custom_prefix)
        
        counter = 1
        base_name = new_name
        while new_name in used_names:
            stem_part = Path(base_name).stem
            suffix = Path(base_name).suffix
            new_name = f"{stem_part}-{counter}{suffix}"
            counter += 1
        
        used_names.add(new_name)
        name_map[image.path] = Path(new_name)
    
    return name_map


def _update_image_references(
    content: str,
    image_name_map: Dict[Path, Path],
) -> Tuple[str, List[Tuple[str, str]]]:
    updated_content = content
    changes: List[Tuple[str, str]] = []
    
    old_names: Dict[str, str] = {}
    for old_path, new_path in image_name_map.items():
        old_names[old_path.name] = new_path.name
        old_names[str(old_path)] = str(new_path)
        old_names[str(old_path).replace('\\', '/')] = str(new_path).replace('\\', '/')
    
    for old_ref, new_ref in old_names.items():
        if old_ref != new_ref and old_ref in updated_content:
            updated_content = updated_content.replace(old_ref, new_ref)
            changes.append((old_ref, new_ref))
    
    return updated_content, changes


def rename_all(
    articles: List[ArticleFile],
    images: List[ImageFile],
    article_output_dir: Path,
    image_output_dir: Path,
    use_date: bool = True,
    use_category: bool = True,
    custom_prefix: Optional[str] = None,
    dry_run: bool = False,
) -> Dict:
    article_output_dir = Path(article_output_dir)
    image_output_dir = Path(image_output_dir)
    
    article_output_dir.mkdir(parents=True, exist_ok=True)
    image_output_dir.mkdir(parents=True, exist_ok=True)
    
    image_name_map = build_image_name_map(images, custom_prefix)
    
    article_results: List[Dict] = []
    used_article_names: set = set()
    
    for article in articles:
        new_name = _generate_article_new_name(
            article, use_date, use_category, custom_prefix
        )
        
        counter = 1
        base_name = new_name
        while new_name in used_article_names:
            stem = Path(base_name).stem
            suffix = Path(base_name).suffix
            new_name = f"{stem}-{counter}{suffix}"
            counter += 1
        
        used_article_names.add(new_name)
        
        old_path = article.path
        new_path = article_output_dir / new_name
        
        updated_content, ref_changes = _update_image_references(
            article.content, image_name_map
        )
        
        if not dry_run:
            new_path.write_text(updated_content, encoding='utf-8')
        
        article_results.append({
            'old_path': old_path,
            'new_path': new_path,
            'ref_changes': ref_changes,
        })
    
    image_results: List[Dict] = []
    for old_path, new_name in image_name_map.items():
        new_path = image_output_dir / new_name
        
        if not dry_run:
            shutil.copy2(old_path, new_path)
        
        image_results.append({
            'old_path': old_path,
            'new_path': new_path,
        })
    
    return {
        'articles': article_results,
        'images': image_results,
        'dry_run': dry_run,
    }


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
        new_name = _generate_article_new_name(
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
            new_path.write_text(article.content, encoding='utf-8')
        
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
    
    name_map = build_image_name_map(images, custom_prefix)
    
    for old_path, new_name in name_map.items():
        new_path = output_dir / new_name
        
        if not dry_run:
            shutil.copy2(old_path, new_path)
        
        results.append((old_path, new_path, dry_run))
    
    return results
