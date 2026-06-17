import io
from pathlib import Path
from typing import List, Tuple, Optional

from PIL import Image

from .types import ImageFile


DEFAULT_QUALITY = 80
DEFAULT_MAX_WIDTH = 1920
DEFAULT_MAX_HEIGHT = 1080
COMPRESSED_SUFFIX = "_compressed"


def _compress_image(
    input_path: Path,
    output_path: Path,
    quality: int = DEFAULT_QUALITY,
    max_width: int = DEFAULT_MAX_WIDTH,
    max_height: int = DEFAULT_MAX_HEIGHT,
    keep_original: bool = True,
) -> Tuple[bool, int, int, str]:
    try:
        original_size = input_path.stat().st_size
        
        with Image.open(input_path) as img:
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            
            width, height = img.size
            ratio = min(max_width / width, max_height / height, 1.0)
            
            if ratio < 1.0:
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            ext = input_path.suffix.lower()
            save_kwargs = {}
            
            if ext in ('.jpg', '.jpeg'):
                save_format = 'JPEG'
                save_kwargs['quality'] = quality
                save_kwargs['optimize'] = True
                save_kwargs['progressive'] = True
            elif ext == '.png':
                save_format = 'PNG'
                save_kwargs['optimize'] = True
            elif ext == '.webp':
                save_format = 'WEBP'
                save_kwargs['quality'] = quality
            elif ext == '.gif':
                save_format = 'GIF'
                save_kwargs['optimize'] = True
            else:
                save_format = img.format or 'JPEG'
                save_kwargs['quality'] = quality
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            img.save(output_path, save_format, **save_kwargs)
            
            compressed_size = output_path.stat().st_size
            savings = original_size - compressed_size
            savings_percent = (savings / original_size * 100) if original_size > 0 else 0
            
            return True, compressed_size, savings, f"{savings_percent:.1f}%"
            
    except Exception as e:
        return False, 0, 0, str(e)


def compress_images(
    images: List[ImageFile],
    output_dir: Path,
    quality: int = DEFAULT_QUALITY,
    max_width: int = DEFAULT_MAX_WIDTH,
    max_height: int = DEFAULT_MAX_HEIGHT,
    keep_original: bool = True,
    only_large: bool = False,
    large_threshold: int = 2 * 1024 * 1024,
    suffix: Optional[str] = None,
) -> List[Tuple[Path, Path, bool, int, int, str]]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if suffix is None:
        suffix = COMPRESSED_SUFFIX
    
    results: List[Tuple[Path, Path, bool, int, int, str]] = []
    
    for image in images:
        input_path = image.path
        
        if only_large and image.size_bytes <= large_threshold:
            continue
        
        if keep_original:
            output_path = output_dir / f"{input_path.stem}{suffix}{input_path.suffix.lower()}"
        else:
            output_path = output_dir / input_path.name
        
        success, compressed_size, savings, info = _compress_image(
            input_path,
            output_path,
            quality=quality,
            max_width=max_width,
            max_height=max_height,
            keep_original=keep_original,
        )
        
        results.append((
            input_path,
            output_path,
            success,
            image.size_bytes,
            compressed_size,
            info,
        ))
    
    return results
