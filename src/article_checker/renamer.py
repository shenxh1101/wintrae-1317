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


def _extract_date(content: str, file_path: Path, date_format: str = "%Y%m%d") -> str:
    match = DATE_PATTERN.search(content)
    if match:
        year, month, day = match.groups()
        try:
            dt = datetime(int(year), int(month), int(day))
            return dt.strftime(date_format)
        except ValueError:
            return f"{year}{month}{day}"
    
    match = DATE_PATTERN.search(file_path.name)
    if match:
        year, month, day = match.groups()
        try:
            dt = datetime(int(year), int(month), int(day))
            return dt.strftime(date_format)
        except ValueError:
            return f"{year}{month}{day}"
    
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
    return mtime.strftime(date_format)


def _extract_category(content: str, default: str = "general") -> str:
    for pattern in CATEGORY_PATTERNS:
        match = pattern.search(content)
        if match:
            category = match.group(1).strip()
            if category:
                return _slugify(category.split(',')[0])
    return _slugify(default)


def _extract_title_for_rename(article: ArticleFile) -> str:
    if article.title:
        return _slugify(article.title)
    
    stem = article.path.stem
    stem = DATE_PATTERN.sub('', stem)
    return _slugify(stem) or "untitled"


def _apply_name_template(
    template: str,
    **kwargs: str,
) -> str:
    result = template
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            result = result.replace(placeholder, str(value) if value else "")
    result = re.sub(r'[_-]+', '_', result)
    return result.strip('_').strip('-')


def _generate_article_new_name(
    article: ArticleFile,
    use_date: bool = True,
    use_category: bool = True,
    custom_prefix: Optional[str] = None,
    name_template: Optional[str] = None,
    date_format: str = "%Y%m%d",
    default_category: str = "general",
    index: int = 1,
) -> str:
    if custom_prefix:
        parts = [_slugify(custom_prefix)]
        if use_date:
            date_str = _extract_date(article.content, article.path, date_format)
            parts.append(date_str)
        if use_category:
            category = _extract_category(article.content, default_category)
            parts.append(category)
        title_slug = _extract_title_for_rename(article)
        parts.append(title_slug)
        return '-'.join(filter(None, parts)) + article.path.suffix.lower()
    
    if name_template:
        date_str = _extract_date(article.content, article.path, date_format) if use_date else ""
        category = _extract_category(article.content, default_category) if use_category else _slugify(default_category)
        title_slug = _extract_title_for_rename(article)
        
        name = _apply_name_template(
            name_template,
            date=date_str,
            category=category,
            title=title_slug,
            index=str(index).zfill(2),
            idx=str(index),
        )
        if not name:
            name = title_slug or f"article-{index}"
        return name + article.path.suffix.lower()
    
    parts = []
    if use_date:
        date_str = _extract_date(article.content, article.path, date_format)
        parts.append(date_str)
    if use_category:
        category = _extract_category(article.content, default_category)
        parts.append(category)
    title_slug = _extract_title_for_rename(article)
    parts.append(title_slug)
    return '-'.join(filter(None, parts)) + article.path.suffix.lower()


def _build_image_article_map(
    articles: List[ArticleFile],
    images: List[ImageFile],
) -> Dict[str, ArticleFile]:
    img_name_to_article: Dict[str, ArticleFile] = {}
    for article in articles:
        for ref in article.referenced_images:
            img_name = Path(ref).name
            if img_name not in img_name_to_article:
                img_name_to_article[img_name] = article
    return img_name_to_article


def _generate_image_new_name(
    image: ImageFile,
    custom_prefix: Optional[str] = None,
    name_template: Optional[str] = None,
    date_format: str = "%Y%m%d",
    default_category: str = "general",
    index: int = 1,
    article: Optional[ArticleFile] = None,
) -> str:
    if custom_prefix:
        parts = [_slugify(custom_prefix)]
        stem = _slugify(image.path.stem)
        parts.append(stem)
        return '-'.join(parts) + image.path.suffix.lower()
    
    if name_template:
        date_str = ""
        category = _slugify(default_category)
        if article:
            date_str = _extract_date(article.content, article.path, date_format)
            category = _extract_category(article.content, default_category)
        stem = _slugify(image.path.stem)
        name = _apply_name_template(
            name_template,
            date=date_str,
            category=category,
            title=stem,
            index=str(index).zfill(2),
            idx=str(index),
        )
        if not name:
            name = stem or f"image-{index}"
        return name + image.path.suffix.lower()
    
    stem = _slugify(image.path.stem)
    return stem + image.path.suffix.lower()


def build_image_name_map(
    images: List[ImageFile],
    articles: Optional[List[ArticleFile]] = None,
    custom_prefix: Optional[str] = None,
    name_template: Optional[str] = None,
    date_format: str = "%Y%m%d",
    default_category: str = "general",
) -> Dict[Path, Path]:
    name_map: Dict[Path, Path] = {}
    used_names: set = set()
    
    img_to_article: Dict[str, ArticleFile] = {}
    if articles:
        img_to_article = _build_image_article_map(articles, images)
    
    idx = 1
    for image in images:
        if not image.is_referenced:
            continue
        
        article = img_to_article.get(image.path.name)
        new_name = _generate_image_new_name(
            image,
            custom_prefix=custom_prefix,
            name_template=name_template,
            date_format=date_format,
            default_category=default_category,
            index=idx,
            article=article,
        )
        idx += 1
        
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
    
    old_name_to_new: Dict[str, str] = {}
    for old_path, new_path in image_name_map.items():
        old_name_to_new[old_path.name] = new_path.name
    
    def _replace_cover(match: re.Match) -> str:
        prefix = match.group(1)
        img_ref = match.group(2).strip()
        img_name = Path(img_ref).name
        if img_name in old_name_to_new:
            new_name = old_name_to_new[img_name]
            if new_name != img_name:
                new_ref = str(Path(img_ref).with_name(new_name)).replace('\\', '/')
                if img_ref.startswith('/'):
                    new_ref = '/' + new_ref.lstrip('/')
                changes.append((img_ref, new_ref))
                return prefix + new_ref
        return match.group(0)
    
    def _replace_img(match: re.Match) -> str:
        full_match = match.group(0)
        img_ref = match.group(1)
        img_name = Path(img_ref).name
        if img_name in old_name_to_new:
            new_name = old_name_to_new[img_name]
            if new_name != img_name:
                new_ref = str(Path(img_ref).with_name(new_name)).replace('\\', '/')
                if img_ref.startswith('/'):
                    new_ref = '/' + new_ref.lstrip('/')
                changes.append((img_ref, new_ref))
                return full_match.replace(img_ref, new_ref)
        return full_match
    
    for pattern in COVER_PATTERNS:
        updated_content = pattern.sub(_replace_cover, updated_content)
    
    updated_content = IMAGE_MD_PATTERN.sub(_replace_img, updated_content)
    updated_content = IMAGE_HTML_PATTERN.sub(_replace_img, updated_content)
    
    seen = set()
    unique_changes: List[Tuple[str, str]] = []
    for old, new in changes:
        if old != new and old not in seen:
            seen.add(old)
            unique_changes.append((old, new))
    
    return updated_content, unique_changes


def rename_all(
    articles: List[ArticleFile],
    images: List[ImageFile],
    article_output_dir: Path,
    image_output_dir: Path,
    use_date: bool = True,
    use_category: bool = True,
    custom_prefix: Optional[str] = None,
    name_template: Optional[str] = None,
    date_format: str = "%Y%m%d",
    default_category: str = "general",
    dry_run: bool = False,
) -> Dict:
    article_output_dir = Path(article_output_dir)
    image_output_dir = Path(image_output_dir)
    
    if not dry_run:
        article_output_dir.mkdir(parents=True, exist_ok=True)
        image_output_dir.mkdir(parents=True, exist_ok=True)
    
    image_name_map = build_image_name_map(
        images,
        articles=articles,
        custom_prefix=custom_prefix,
        name_template=name_template,
        date_format=date_format,
        default_category=default_category,
    )
    
    article_results: List[Dict] = []
    used_article_names: set = set()
    
    for idx, article in enumerate(articles, 1):
        new_name = _generate_article_new_name(
            article,
            use_date=use_date,
            use_category=use_category,
            custom_prefix=custom_prefix,
            name_template=name_template,
            date_format=date_format,
            default_category=default_category,
            index=idx,
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
