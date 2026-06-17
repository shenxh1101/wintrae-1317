import sys
from pathlib import Path

import click

from . import __version__
from .config import load_config, get_config_value, find_config_file
from .checker import scan as scan_directory, get_all_links, DEFAULT_MAX_IMAGE_SIZE
from .link_checker import check_links, DEFAULT_TIMEOUT, DEFAULT_MAX_WORKERS, DEFAULT_RETRY_COUNT
from .compressor import compress_images, DEFAULT_QUALITY, DEFAULT_MAX_WIDTH, DEFAULT_MAX_HEIGHT
from .renamer import rename_all, rename_articles, rename_images
from .reporter import (
    generate_text_report,
    generate_json_report,
    generate_html_report,
    print_console_summary,
    SEVERITY_ICONS_SIMPLE,
)


def _get_icon(severity: str) -> str:
    return SEVERITY_ICONS_SIMPLE.get(severity, "[*]")


def _validate_dir(ctx, param, value):
    if value is None:
        return value
    path = Path(value)
    if not path.exists():
        raise click.BadParameter(f"目录不存在: {value}")
    if not path.is_dir():
        raise click.BadParameter(f"不是目录: {value}")
    return path


def _resolve_dir(value, config, config_key, default=None):
    if value is not None:
        return Path(value)
    config_val = get_config_value(config, config_key)
    if config_val:
        path = Path(config_val)
        if path.exists() and path.is_dir():
            return path
    return default


@click.group()
@click.version_option(version=__version__, prog_name="article-checker")
@click.option("--article-dir", "-a", type=click.Path(), callback=_validate_dir,
              default=None, help="文章目录 (可在配置文件中设置)")
@click.option("--image-dir", "-i", type=click.Path(), callback=_validate_dir,
              default=None, help="图片目录 (可在配置文件中设置)")
@click.option("--output-dir", "-o", type=click.Path(), default=None,
              help="输出目录 (可在配置文件中设置，默认: ./output)")
@click.option("--config", "-c", type=click.Path(exists=True, dir_okay=False),
              default=None, help="配置文件路径")
@click.pass_context
def cli(ctx, article_dir, image_dir, output_dir, config):
    """文章发布前素材包批量检查工具"""
    ctx.ensure_object(dict)
    
    config_path = Path(config) if config else None
    if not config_path:
        config_path = find_config_file()
    
    config_data = load_config(config_path)
    ctx.obj["config"] = config_data
    ctx.obj["config_path"] = config_path
    
    article_dir = _resolve_dir(article_dir, config_data, "article_dir")
    image_dir = _resolve_dir(image_dir, config_data, "image_dir")
    
    if output_dir is None:
        output_dir = get_config_value(config_data, "output_dir", default="./output")
    output_dir = Path(output_dir)
    
    ctx.obj["article_dir"] = article_dir
    ctx.obj["image_dir"] = image_dir
    ctx.obj["output_dir"] = output_dir
    
    if config_path:
        click.echo(f"使用配置文件: {config_path}")


@cli.command()
@click.option("--max-image-size", type=int, default=None,
              help="最大图片大小 (字节, 可在配置文件中设置)")
@click.pass_context
def scan(ctx, max_image_size):
    """扫描文章和图片，识别各类问题"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    config = ctx.obj["config"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录，或在配置文件中设置", err=True)
        sys.exit(1)
    
    if max_image_size is None:
        max_image_size = get_config_value(config, "max_image_size", default=DEFAULT_MAX_IMAGE_SIZE)
    
    click.echo(f"正在扫描...")
    click.echo(f"  文章目录: {article_dir}")
    click.echo(f"  图片目录: {image_dir}")
    
    result = scan_directory(article_dir, image_dir, max_image_size)
    ctx.obj["scan_result"] = result
    
    print_console_summary(result)
    
    for issue in result.issues:
        icon = _get_icon(issue.severity)
        click.echo(f"  {icon} {issue.message}")
        if issue.file_path:
            click.echo(f"     文件: {issue.file_path}")
    
    return result


@cli.command()
@click.option("--no-date", is_flag=True, default=None, help="不使用日期前缀")
@click.option("--no-category", is_flag=True, default=None, help="不使用栏目前缀")
@click.option("--prefix", default=None, help="自定义文件名前缀")
@click.option("--dry-run", is_flag=True, help="仅预览，不实际执行")
@click.option("--show-ref-changes", is_flag=True, help="显示图片引用变更详情")
@click.pass_context
def rename(ctx, no_date, no_category, prefix, dry_run, show_ref_changes):
    """按日期与栏目统一命名文章和图片，自动更新文章内图片引用"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    output_dir = ctx.obj["output_dir"]
    config = ctx.obj["config"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录，或在配置文件中设置", err=True)
        sys.exit(1)
    
    use_date = get_config_value(config, "naming", "use_date", default=True)
    if no_date is not None:
        use_date = not no_date
    
    use_category = get_config_value(config, "naming", "use_category", default=True)
    if no_category is not None:
        use_category = not no_category
    
    if prefix is None:
        prefix = get_config_value(config, "naming", "prefix")
    
    if "scan_result" not in ctx.obj:
        click.echo("正在扫描...")
        result = scan_directory(article_dir, image_dir)
        ctx.obj["scan_result"] = result
    else:
        result = ctx.obj["scan_result"]
    
    if dry_run:
        click.echo("【预览模式】以下是将执行的重命名操作:\n")
    else:
        click.echo("正在重命名...\n")
    
    articles_output = output_dir / "renamed_articles"
    images_output = output_dir / "renamed_images"
    
    rename_result = rename_all(
        result.articles,
        result.images,
        articles_output,
        images_output,
        use_date=use_date,
        use_category=use_category,
        custom_prefix=prefix,
        dry_run=dry_run,
    )
    
    article_results = rename_result["articles"]
    image_results = rename_result["images"]
    
    click.echo("文章重命名:")
    for art in article_results:
        old_name = art["old_path"].name
        new_name = art["new_path"].name
        ref_count = len(art["ref_changes"])
        ref_info = f" (更新 {ref_count} 处图片引用)" if ref_count > 0 else ""
        click.echo(f"  {old_name} -> {new_name}{ref_info}")
        
        if show_ref_changes and art["ref_changes"]:
            for old_ref, new_ref in art["ref_changes"]:
                click.echo(f"    - {old_ref} => {new_ref}")
    
    click.echo("\n图片重命名:")
    for img in image_results:
        click.echo(f"  {img['old_path'].name} -> {img['new_path'].name}")
    
    total_ref_changes = sum(len(art["ref_changes"]) for art in article_results)
    click.echo(f"\n共重命名 {len(article_results)} 篇文章, {len(image_results)} 张图片")
    if total_ref_changes > 0:
        click.echo(f"更新图片引用 {total_ref_changes} 处")
    
    if not dry_run:
        click.echo(f"\n输出目录:")
        click.echo(f"  文章: {articles_output}")
        click.echo(f"  图片: {images_output}")
        click.echo(f"\n交付包已就绪，可直接用于发布")


@cli.command("check-links")
@click.option("--timeout", type=int, default=None,
              help=f"请求超时时间 (秒, 可在配置文件中设置)")
@click.option("--max-workers", type=int, default=None,
              help=f"最大并发数 (可在配置文件中设置)")
@click.option("--retry-count", type=int, default=None,
              help=f"重试次数 (可在配置文件中设置)")
@click.option("--no-verify-ssl", is_flag=True, default=None, help="不验证 SSL 证书")
@click.pass_context
def check_links_cmd(ctx, timeout, max_workers, retry_count, no_verify_ssl):
    """检查文章中的外部链接有效性"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    config = ctx.obj["config"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录，或在配置文件中设置", err=True)
        sys.exit(1)
    
    if timeout is None:
        timeout = get_config_value(config, "link_check", "timeout", default=DEFAULT_TIMEOUT)
    if max_workers is None:
        max_workers = get_config_value(config, "link_check", "max_workers", default=DEFAULT_MAX_WORKERS)
    if retry_count is None:
        retry_count = get_config_value(config, "link_check", "retry_count", default=DEFAULT_RETRY_COUNT)
    
    verify_ssl = get_config_value(config, "link_check", "verify_ssl", default=True)
    if no_verify_ssl is not None:
        verify_ssl = not no_verify_ssl
    
    if "scan_result" not in ctx.obj:
        click.echo("正在扫描...")
        result = scan_directory(article_dir, image_dir)
        ctx.obj["scan_result"] = result
    else:
        result = ctx.obj["scan_result"]
    
    links = get_all_links(result)
    click.echo(f"发现 {len(links)} 个外部链接，开始检查...\n")
    
    issues = check_links(
        result,
        timeout=timeout,
        max_workers=max_workers,
        retry_count=retry_count,
        verify_ssl=verify_ssl,
    )
    
    ctx.obj["link_issues"] = issues
    
    if issues:
        click.echo(f"发现 {len(issues)} 个问题链接:\n")
        for issue in issues:
            icon = _get_icon(issue.severity)
            click.echo(f"  {icon} {issue.message}")
            if "articles" in issue.details:
                for art in issue.details["articles"]:
                    click.echo(f"     出现于: {art}")
    else:
        click.echo("[OK] 所有链接检查通过!")
    
    return issues


@cli.command()
@click.option("--quality", type=int, default=None,
              help=f"压缩质量 1-100 (可在配置文件中设置)")
@click.option("--max-width", type=int, default=None,
              help=f"最大宽度 (可在配置文件中设置)")
@click.option("--max-height", type=int, default=None,
              help=f"最大高度 (可在配置文件中设置)")
@click.option("--only-large", is_flag=True, default=None, help="仅压缩超过阈值的图片")
@click.option("--large-threshold", type=int, default=None,
              help=f"大图片阈值 (字节, 可在配置文件中设置)")
@click.option("--overwrite", is_flag=True, help="覆盖原文件 (不添加 _compressed 后缀)")
@click.pass_context
def compress(ctx, quality, max_width, max_height, only_large, large_threshold, overwrite):
    """批量压缩图片并保留原文件"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    output_dir = ctx.obj["output_dir"]
    config = ctx.obj["config"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录，或在配置文件中设置", err=True)
        sys.exit(1)
    
    if quality is None:
        quality = get_config_value(config, "compress", "quality", default=DEFAULT_QUALITY)
    if max_width is None:
        max_width = get_config_value(config, "compress", "max_width", default=DEFAULT_MAX_WIDTH)
    if max_height is None:
        max_height = get_config_value(config, "compress", "max_height", default=DEFAULT_MAX_HEIGHT)
    if only_large is None:
        only_large = get_config_value(config, "compress", "only_large", default=False)
    if large_threshold is None:
        large_threshold = get_config_value(config, "compress", "large_threshold", default=DEFAULT_MAX_IMAGE_SIZE)
    
    if "scan_result" not in ctx.obj:
        click.echo("正在扫描...")
        result = scan_directory(article_dir, image_dir)
        ctx.obj["scan_result"] = result
    else:
        result = ctx.obj["scan_result"]
    
    compress_output = output_dir / "compressed_images"
    
    click.echo(f"正在压缩图片...")
    if only_large:
        click.echo(f"  仅处理大于 {large_threshold / 1024 / 1024:.2f} MB 的图片")
    
    results = compress_images(
        result.images,
        compress_output,
        quality=quality,
        max_width=max_width,
        max_height=max_height,
        keep_original=not overwrite,
        only_large=only_large,
        large_threshold=large_threshold,
    )
    
    if not results:
        click.echo("没有需要压缩的图片")
        return
    
    click.echo(f"\n压缩结果:")
    total_savings = 0
    success_count = 0
    
    for input_path, output_path, success, orig_size, comp_size, info in results:
        if success:
            success_count += 1
            savings = orig_size - comp_size
            total_savings += savings
            status = "[OK]"
        else:
            status = "[FAIL]"
        
        click.echo(f"  {status} {input_path.name}")
        if success:
            click.echo(f"     {orig_size / 1024:.2f} KB -> {comp_size / 1024:.2f} KB (节省 {info})")
            if not overwrite:
                click.echo(f"     输出: {output_path}")
        else:
            click.echo(f"     错误: {info}")
    
    click.echo(f"\n成功压缩 {success_count}/{len(results)} 张图片")
    click.echo(f"总共节省: {total_savings / 1024 / 1024:.2f} MB")
    if not overwrite:
        click.echo(f"输出目录: {compress_output}")


@cli.command()
@click.option("--format", "-f", type=click.Choice(["text", "json", "html", "all"]),
              default=None, help="报告格式 (可在配置文件中设置，默认: text)")
@click.option("--filename", default=None, help="报告文件名 (不含扩展名)")
@click.option("--include-links", is_flag=True, default=None,
              help="在报告中包含链接检查结果")
@click.pass_context
def report(ctx, format, filename, include_links):
    """输出检查摘要、问题清单和可复核的文件路径"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    output_dir = ctx.obj["output_dir"]
    config = ctx.obj["config"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录，或在配置文件中设置", err=True)
        sys.exit(1)
    
    if format is None:
        format = get_config_value(config, "report", "format", default="text")
    if filename is None:
        filename = get_config_value(config, "report", "filename", default="report")
    if include_links is None:
        include_links = get_config_value(config, "report", "include_links", default=False)
    
    if "scan_result" not in ctx.obj:
        click.echo("正在扫描...")
        result = scan_directory(article_dir, image_dir)
        ctx.obj["scan_result"] = result
    else:
        result = ctx.obj["scan_result"]
    
    link_issues = None
    if include_links:
        if "link_issues" not in ctx.obj:
            click.echo("正在检查链接...")
            link_issues = check_links(result)
            ctx.obj["link_issues"] = link_issues
        else:
            link_issues = ctx.obj["link_issues"]
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if format in ("text", "all"):
        text_path = output_dir / f"{filename}.txt"
        generate_text_report(result, text_path, link_issues)
        click.echo(f"文本报告已生成: {text_path}")
    
    if format in ("json", "all"):
        json_path = output_dir / f"{filename}.json"
        generate_json_report(result, json_path, link_issues)
        click.echo(f"JSON 报告已生成: {json_path}")
    
    if format in ("html", "all"):
        html_path = output_dir / f"{filename}.html"
        generate_html_report(result, html_path, link_issues)
        click.echo(f"HTML 报告已生成: {html_path}")
    
    print_console_summary(result, link_issues)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
