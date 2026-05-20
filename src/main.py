"""LawToMd CLI 入口。

用法:
    lawtomd input.pdf
    lawtomd input.pdf -o output.md
    lawtomd batch ./pdfs/ -o ./output/
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from src.builder import build_markdown
from src.extractor import extract_pdf
from src.models import DocType, Level
from src.structure import parse_structure

logger = logging.getLogger(__name__)


# ── 全局选项 ──────────────────────────────────────────────

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-v", "--verbose", count=True, help="增加日志详细度")
def cli(verbose: int) -> None:
    """LawToMd — 法律 PDF 转 Markdown 工具。

    自动识别法律文档的编/章/节/条结构，输出结构化 Markdown。
    """
    level = logging.WARNING
    if verbose >= 2:
        level = logging.DEBUG
    elif verbose >= 1:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


# ── 单文件转换 ────────────────────────────────────────────

@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="输出路径（默认同文件名 .md）")
@click.option("--max-pages", type=int, default=None, help="只处理前 N 页")
@click.option("--no-filter", is_flag=True, help="不过滤页眉页脚")
@click.option("--toc", is_flag=True, help="生成目录")
@click.option("--no-anchor", is_flag=True, help="不添加 anchor 注释")
@click.option(
    "--ocr",
    type=click.Choice(["auto", "force", "off"]),
    default="off",
    show_default=True,
    help="OCR 模式: auto=对无文字页面回退, force=强制所有页面, off=禁用",
)
def convert(
    pdf_path: str,
    output: Optional[str],
    max_pages: Optional[int],
    no_filter: bool,
    toc: bool,
    no_anchor: bool,
    ocr: str,
) -> None:
    """将单个法律 PDF 转换为 Markdown。"""
    pdf = Path(pdf_path)
    if not output:
        output = str(pdf.with_suffix(".md"))

    click.echo(f"解析: {pdf.name} ...", err=True)

    # Step 1: 提取
    lines, meta = extract_pdf(str(pdf), max_pages=max_pages, filter_header_footer=not no_filter, ocr_mode=ocr)
    click.echo(f"  提取 | 行: {len(lines)} | 法规: {meta.name or '?'}", err=True)

    # Step 2: 结构识别
    tree = parse_structure(lines, doc_type=meta.doc_type)
    total_articles = sum(1 for top in tree for _ in _walk_articles(top))
    click.echo(f"  结构 | 条: {total_articles} | 类型: {meta.doc_type.value}", err=True)

    # Step 3: 生成 Markdown
    md = build_markdown(tree, meta, include_toc=toc, article_anchor=not no_anchor)
    with open(output, "w", encoding="utf-8") as f:
        f.write(md)
    click.echo(f"  Markdown | → {output}", err=True)

    click.echo("完成.", err=True)


# ── 批量处理 ──────────────────────────────────────────────

@cli.command()
@click.argument("pdf_dir", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", type=click.Path(file_okay=False), default="./output", show_default=True)
@click.option("--max-pages", type=int, default=None, help="每份只处理前 N 页")
@click.option("--flatten", is_flag=True, help="输出到单层目录（默认保持子目录结构）")
@click.option("--no-filter", is_flag=True, help="不过滤页眉页脚")
@click.option(
    "--ocr",
    type=click.Choice(["auto", "force", "off"]),
    default="off",
    show_default=True,
    help="OCR 模式: auto=对无文字页面回退, force=强制所有页面, off=禁用",
)
def batch(
    pdf_dir: str,
    output: str,
    max_pages: Optional[int],
    flatten: bool,
    no_filter: bool,
    ocr: str,
) -> None:
    """批量处理目录中的所有 PDF。"""
    src_dir = Path(pdf_dir)
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(src_dir.rglob("*.pdf"))
    if not pdf_files:
        click.echo("未找到 PDF 文件.", err=True)
        return

    click.echo(f"批量处理: {len(pdf_files)} 个文件", err=True)

    for i, pdf_path in enumerate(pdf_files, start=1):
        rel = pdf_path.relative_to(src_dir)
        out_name = rel.with_suffix(".md")

        if flatten:
            out_path = out_dir / out_name.name
        else:
            out_path = out_dir / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            lines, meta = extract_pdf(str(pdf_path), max_pages=max_pages, filter_header_footer=not no_filter, ocr_mode=ocr)
            tree = parse_structure(lines, doc_type=meta.doc_type)

            md = build_markdown(tree, meta, include_toc=False, article_anchor=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md)

            # 释放当前文件的中间数据，防止批量处理时内存累积
            del lines, tree, meta, md
            import gc
            gc.collect()

            click.echo(f"  [{i}/{len(pdf_files)}] {pdf_path.name}", err=True)
        except Exception as e:
            click.echo(f"  [{i}/{len(pdf_files)}] ❌ {pdf_path.name}: {e}", err=True)

    click.echo(f"批量完成. 输出至: {out_dir}", err=True)


# ── 辅助 ──────────────────────────────────────────────────

def _walk_articles(node):
    if node.level == Level.ARTICLE:
        yield node
    for child in node.children:
        yield from _walk_articles(child)


if __name__ == "__main__":
    cli()
