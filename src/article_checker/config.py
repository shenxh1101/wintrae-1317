import json
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


DEFAULT_CONFIG = {
    "article_dir": None,
    "image_dir": None,
    "output_dir": "./output",
    "max_image_size": 2 * 1024 * 1024,
    "naming": {
        "use_date": True,
        "use_category": True,
        "prefix": None,
        "template": "{date}-{category}-{title}",
    },
    "link_check": {
        "timeout": 10,
        "max_workers": 10,
        "retry_count": 2,
        "verify_ssl": True,
    },
    "compress": {
        "quality": 80,
        "max_width": 1920,
        "max_height": 1080,
        "only_large": False,
        "large_threshold": 2 * 1024 * 1024,
    },
    "ignore": {
        "patterns": [],
        "images": [],
    },
    "report": {
        "format": "text",
        "filename": "report",
        "include_links": False,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_json_config(config_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, IOError):
        return None


def _load_toml_config(config_path: Path) -> Optional[Dict[str, Any]]:
    if tomllib is None:
        return None
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        tool_config = data.get("tool", {}).get("article-checker", {})
        return tool_config if tool_config else None
    except Exception:
        return None


def find_config_file(start_dir: Optional[Path] = None) -> Optional[Path]:
    if start_dir is None:
        start_dir = Path.cwd()
    else:
        start_dir = Path(start_dir)
    
    config_filenames = [
        ".article-checker.json",
        "article-checker.json",
        "pyproject.toml",
    ]
    
    current = start_dir.resolve()
    while True:
        for filename in config_filenames:
            config_path = current / filename
            if config_path.is_file():
                return config_path
        
        parent = current.parent
        if parent == current:
            break
        current = parent
    
    return None


def _normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    result = config.copy()
    
    if "image" in result and isinstance(result["image"], dict):
        img = result["image"]
        if "max_size_mb" in img:
            max_size_bytes = int(img["max_size_mb"] * 1024 * 1024)
            result["max_image_size"] = max_size_bytes
            if "compress" not in result:
                result["compress"] = {}
            result["compress"]["large_threshold"] = max_size_bytes
        if "quality" in img:
            if "compress" not in result:
                result["compress"] = {}
            result["compress"]["quality"] = img["quality"]
        if "max_width" in img:
            if "compress" not in result:
                result["compress"] = {}
            result["compress"]["max_width"] = img["max_width"]
        if "max_height" in img:
            if "compress" not in result:
                result["compress"] = {}
            result["compress"]["max_height"] = img["max_height"]
        if "suffix" in img:
            if "compress" not in result:
                result["compress"] = {}
            result["compress"]["suffix"] = img["suffix"]
    
    if "rename" in result and isinstance(result["rename"], dict):
        ren = result["rename"]
        if "naming" not in result:
            result["naming"] = {}
        if "name_template" in ren:
            result["naming"]["template"] = ren["name_template"]
        if "category" in ren:
            result["naming"]["default_category"] = ren["category"]
        if "date_format" in ren:
            result["naming"]["date_format"] = ren["date_format"]
        if "prefix" in ren:
            result["naming"]["prefix"] = ren["prefix"]
        if "use_date" in ren:
            result["naming"]["use_date"] = ren["use_date"]
        if "use_category" in ren:
            result["naming"]["use_category"] = ren["use_category"]
    
    if "check_links" in result and isinstance(result["check_links"], dict):
        cl = result["check_links"]
        if "link_check" not in result:
            result["link_check"] = {}
        if "timeout" in cl:
            result["link_check"]["timeout"] = cl["timeout"]
        if "max_retries" in cl:
            result["link_check"]["retry_count"] = cl["max_retries"]
        if "retry_count" in cl:
            result["link_check"]["retry_count"] = cl["retry_count"]
        if "verify_ssl" in cl:
            result["link_check"]["verify_ssl"] = cl["verify_ssl"]
        if "max_workers" in cl:
            result["link_check"]["max_workers"] = cl["max_workers"]
    
    if "report" not in result:
        result["report"] = {}
    if "format" in result:
        result["report"]["format"] = result["format"]
    if "report_format" in result:
        result["report"]["format"] = result["report_format"]
    
    return result


def load_config(
    config_path: Optional[Path] = None,
    start_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    
    if config_path is None:
        config_path = find_config_file(start_dir)
    
    if config_path is None:
        return config
    
    config_path = Path(config_path)
    
    file_config = None
    if config_path.suffix.lower() == ".json":
        file_config = _load_json_config(config_path)
    elif config_path.suffix.lower() == ".toml":
        file_config = _load_toml_config(config_path)
    
    if file_config:
        file_config = _normalize_config(file_config)
        config = _deep_merge(config, file_config)
    
    return config


def get_config_value(config: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current = config
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
