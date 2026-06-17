from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class IssueType(str, Enum):
    MISSING_COVER = "missing_cover"
    DUPLICATE_FILENAME = "duplicate_filename"
    LARGE_IMAGE = "large_image"
    UNUSED_MATERIAL = "unused_material"
    BAD_LINK = "bad_link"
    EMPTY_TITLE = "empty_title"


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Issue:
    type: IssueType
    severity: IssueSeverity
    message: str
    file_path: Optional[Path] = None
    details: dict = field(default_factory=dict)


@dataclass
class ArticleFile:
    path: Path
    title: str = ""
    content: str = ""
    referenced_images: List[str] = field(default_factory=list)
    referenced_links: List[str] = field(default_factory=list)
    has_cover: bool = False


@dataclass
class ImageFile:
    path: Path
    size_bytes: int = 0
    is_referenced: bool = False


@dataclass
class ScanResult:
    articles: List[ArticleFile] = field(default_factory=list)
    images: List[ImageFile] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
