import sys
from pathlib import Path

import click

from . import __version__
from .checker import scan as scan_directory, get_all_links, DEFAULT_MAX_IMAGE_SIZE
from .link_checker import check_links, DEFAULT_TIMEOUT, DEFAULT_MAX_WORKERS, DEFAULT_RETRY_COUNT
from .compressor import compress_images, DEFAULT_QUALITY, DEFAULT_MAX_WIDTH, DEFAULT_MAX_HEIGHT
from .renamer import rename_articles, rename_images
from .reporter import generate_text_report, generate_json_report, print_console_summary, SEVERITY_ICONS_SIMPLE


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


@click.group()
@click.version_option(version=__version__, prog_name="article-checker")
@click.option("--article-dir", "-a", type=click.Path(), callback=_validate_dir,
              help="文章目录")
@click.option("--image-dir", "-i", type=click.Path(), callback=_validate_dir,
              help="图片目录")
@click.option("--output-dir", "-o", type=click.Path(), default="./output",
              help="输出目录 (默认: ./output)")
@click.pass_context
def cli(ctx, article_dir, image_dir, output_dir):
    """文章发布前素材包批量检查工具"""
    ctx.ensure_object(dict)
    ctx.obj["article_dir"] = Path(article_dir) if article_dir else None
    ctx.obj["image_dir"] = Path(image_dir) if image_dir else None
    ctx.obj["output_dir"] = Path(output_dir)


@cli.command()
@click.option("--max-image-size", type=int, default=DEFAULT_MAX_IMAGE_SIZE,
              help=f"最大图片大小 (字节, 默认: {DEFAULT_MAX_IMAGE_SIZE})")
@click.pass_context
def scan(ctx, max_image_size):
    """扫描文章和图片，识别各类问题"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    output_dir = ctx.obj["output_dir"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录", err=True)
        sys.exit(1)
    
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
@click.option("--no-date", is_flag=True, help="不使用日期前缀")
@click.option("--no-category", is_flag=True, help="不使用栏目前缀")
@click.option("--prefix", help="自定义文件名前缀")
@click.option("--dry-run", is_flag=True, help="仅预览，不实际执行")
@click.pass_context
def rename(ctx, no_date, no_category, prefix, dry_run):
    """按日期与栏目统一命名文章和图片"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    output_dir = ctx.obj["output_dir"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录", err=True)
        sys.exit(1)
    
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
    
    article_results = rename_articles(
        result.articles,
        image_dir,
        articles_output,
        use_date=not no_date,
        use_category=not no_category,
        custom_prefix=prefix,
        dry_run=dry_run,
    )
    
    image_results = rename_images(
        result.images,
        images_output,
        article_dir,
        use_date=not no_date,
        use_category=not no_category,
        custom_prefix=prefix,
        dry_run=dry_run,
    )
    
    click.echo("文章重命名:")
    for old, new, is_dry in article_results:
        click.echo(f"  {old.name} -> {new.name}")
    
    click.echo(f"\n共重命名 {len(article_results)} 篇文章, {len(image_results)} 张图片")
    
    if not dry_run:
        click.echo(f"\n输出目录:")
        click.echo(f"  文章: {articles_output}")
        click.echo(f"  图片: {images_output}")


@cli.command("check-links")
@click.option("--timeout", type=int, default=DEFAULT_TIMEOUT,
              help=f"请求超时时间 (秒, 默认: {DEFAULT_TIMEOUT})")
@click.option("--max-workers", type=int, default=DEFAULT_MAX_WORKERS,
              help=f"最大并发数 (默认: {DEFAULT_MAX_WORKERS})")
@click.option("--retry-count", type=int, default=DEFAULT_RETRY_COUNT,
              help=f"重试次数 (默认: {DEFAULT_RETRY_COUNT})")
@click.option("--no-verify-ssl", is_flag=True, help="不验证 SSL 证书")
@click.pass_context
def check_links_cmd(ctx, timeout, max_workers, retry_count, no_verify_ssl):
    """检查文章中的外部链接有效性"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录", err=True)
        sys.exit(1)
    
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
        verify_ssl=not no_verify_ssl,
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
@click.option("--quality", type=int, default=DEFAULT_QUALITY,
              help=f"压缩质量 1-100 (默认: {DEFAULT_QUALITY})")
@click.option("--max-width", type=int, default=DEFAULT_MAX_WIDTH,
              help=f"最大宽度 (默认: {DEFAULT_MAX_WIDTH})")
@click.option("--max-height", type=int, default=DEFAULT_MAX_HEIGHT,
              help=f"最大高度 (默认: {DEFAULT_MAX_HEIGHT})")
@click.option("--only-large", is_flag=True, help="仅压缩超过阈值的图片")
@click.option("--large-threshold", type=int, default=DEFAULT_MAX_IMAGE_SIZE,
              help=f"大图片阈值 (字节, 默认: {DEFAULT_MAX_IMAGE_SIZE})")
@click.option("--overwrite", is_flag=True, help="覆盖原文件 (不添加 _compressed 后缀)")
@click.pass_context
def compress(ctx, quality, max_width, max_height, only_large, large_threshold, overwrite):
    """批量压缩图片并保留原文件"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    output_dir = ctx.obj["output_dir"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录", err=True)
        sys.exit(1)
    
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
@click.option("--format", "-f", type=click.Choice(["text", "json", "both"]),
              default="text", help="报告格式 (默认: text)")
@click.option("--filename", default="report", help="报告文件名 (不含扩展名)")
@click.option("--include-links", is_flag=True, help="在报告中包含链接检查结果")
@click.pass_context
def report(ctx, format, filename, include_links):
    """输出检查摘要、问题清单和可复核的文件路径"""
    article_dir = ctx.obj["article_dir"]
    image_dir = ctx.obj["image_dir"]
    output_dir = ctx.obj["output_dir"]
    
    if not article_dir or not image_dir:
        click.echo("错误: 请使用 --article-dir 和 --image-dir 指定目录", err=True)
        sys.exit(1)
    
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
    
    if format in ("text", "both"):
        text_path = output_dir / f"{filename}.txt"
        generate_text_report(result, text_path, link_issues)
        click.echo(f"文本报告已生成: {text_path}")
    
    if format in ("json", "both"):
        json_path = output_dir / f"{filename}.json"
        generate_json_report(result, json_path, link_issues)
        click.echo(f"JSON 报告已生成: {json_path}")
    
    print_console_summary(result, link_issues)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
