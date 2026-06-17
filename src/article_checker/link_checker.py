import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse

import requests

from .types import Issue, IssueType, IssueSeverity, ArticleFile


DEFAULT_TIMEOUT = 10
DEFAULT_MAX_WORKERS = 10
DEFAULT_RETRY_COUNT = 2


def _is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def _check_link(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    retry_count: int = DEFAULT_RETRY_COUNT,
    verify_ssl: bool = True,
) -> Tuple[bool, int, str]:
    if not _is_valid_url(url):
        return False, 0, "Invalid URL format"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    last_error = ""
    for attempt in range(retry_count + 1):
        try:
            response = requests.head(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
                verify=verify_ssl,
            )
            
            if response.status_code < 400:
                return True, response.status_code, "OK"
            
            if response.status_code == 405:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True,
                    verify=verify_ssl,
                    stream=True,
                )
                if response.status_code < 400:
                    return True, response.status_code, "OK"
            
            return False, response.status_code, f"HTTP {response.status_code}"
            
        except requests.exceptions.SSLError as e:
            last_error = f"SSL Error: {str(e)[:50]}"
        except requests.exceptions.Timeout as e:
            last_error = f"Timeout: {str(e)[:50]}"
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection Error: {str(e)[:50]}"
        except requests.exceptions.RequestException as e:
            last_error = f"Request Error: {str(e)[:50]}"
        except Exception as e:
            last_error = f"Error: {str(e)[:50]}"
        
        if attempt < retry_count:
            time.sleep(1)
    
    return False, 0, last_error


def check_links(
    scan_result,
    timeout: int = DEFAULT_TIMEOUT,
    max_workers: int = DEFAULT_MAX_WORKERS,
    retry_count: int = DEFAULT_RETRY_COUNT,
    verify_ssl: bool = True,
) -> List[Issue]:
    links_to_check: Dict[str, List[Path]] = {}
    
    for article in scan_result.articles:
        for link in article.referenced_links:
            if link.startswith(('http://', 'https://')):
                links_to_check.setdefault(link, []).append(article.path)
    
    issues: List[Issue] = []
    
    if not links_to_check:
        return issues
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(
                _check_link, url, timeout, retry_count, verify_ssl
            ): url
            for url in links_to_check
        }
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                is_valid, status_code, message = future.result()
                
                if not is_valid:
                    articles_with_link = links_to_check[url]
                    issues.append(Issue(
                        type=IssueType.BAD_LINK,
                        severity=IssueSeverity.ERROR if status_code >= 400 or status_code == 0 else IssueSeverity.WARNING,
                        message=f"链接失效: {url} ({message})",
                        file_path=articles_with_link[0] if articles_with_link else None,
                        details={
                            "url": url,
                            "status_code": status_code,
                            "error": message,
                            "articles": [str(p) for p in articles_with_link],
                        },
                    ))
            except Exception as e:
                articles_with_link = links_to_check[url]
                issues.append(Issue(
                    type=IssueType.BAD_LINK,
                    severity=IssueSeverity.WARNING,
                    message=f"链接检查异常: {url} ({str(e)[:50]})",
                    file_path=articles_with_link[0] if articles_with_link else None,
                    details={
                        "url": url,
                        "error": str(e),
                        "articles": [str(p) for p in articles_with_link],
                    },
                ))
    
    return issues
