"""LawToMd CLI 入口。

用法:
    lawtomd input.pdf
    lawtomd input.pdf -o output.md
    lawtomd input.pdf --ocr auto --ocr-engine auto
    lawtomd batch ./pdfs/ -o ./output/
"""

from __future__ import annotations

import logging
import json
import sys
from pathlib import Path
from typing import Optional, cast

import click

from src.builder import build_markdown
from src.extractor import extract_pdf
from src.models import LawMeta, Level
from src.structure import parse_structure
from src.types import OcrEngineChoice, OcrMode

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


# ── 性能检测展示 ──────────────────────────────────────────


def _show_device_profile(ocr_engine: str) -> None:
    """当使用 OCR 时，展示设备性能检测结果和方案推荐。"""
    if ocr_engine == "auto":
        from src.profiler import detect_device_profile

        profile = detect_device_profile()
        click.echo(profile.summary(), err=True)
    elif ocr_engine == "paddle":
        click.echo("OCR 方案: PaddleOCR (高性能, 用户手动选择)", err=True)
    elif ocr_engine == "lite":
        click.echo("OCR 方案: RapidOCR (轻量版, 用户手动选择)", err=True)


# ── 单文件转换 ────────────────────────────────────────────

@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="输出路径（默认同文件名 .md）")
@click.option("--max-pages", type=int, default=None, help="只处理前 N 页")
@click.option("--no-filter", is_flag=True, help="不过滤页眉页脚")
@click.option("--toc", is_flag=True, help="生成目录")
@click.option("--no-anchor", is_flag=True, help="不添加 anchor 注释")
@click.option("--validate", is_flag=True, help="校验条号连续性")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["md", "json"]),
    default="md",
    show_default=True,
    help="输出格式: md=Markdown, json=结构化JSON",
)
@click.option(
    "--ocr",
    type=click.Choice(["auto", "force", "off"]),
    default="off",
    show_default=True,
    help="OCR 模式: auto=对无文字页面回退, force=强制所有页面, off=禁用",
)
@click.option(
    "--ocr-engine",
    type=click.Choice(["auto", "paddle", "lite"]),
    default="auto",
    show_default=True,
    help="OCR 引擎: auto=根据设备性能自动推荐, paddle=PaddleOCR高性能, lite=RapidOCR轻量版",
)
def convert(
    pdf_path: str,
    output: Optional[str],
    max_pages: Optional[int],
    no_filter: bool,
    toc: bool,
    no_anchor: bool,
    validate: bool,
    output_format: str,
    ocr: str,
    ocr_engine: str,
) -> None:
    """将单个法律 PDF 转换为 Markdown。"""
    pdf = Path(pdf_path)
    ext = ".json" if output_format == "json" else ".md"
    if not output:
        output = str(pdf.with_suffix(ext))

    click.echo(f"解析: {pdf.name} ...", err=True)

    # 展示设备性能检测和 OCR 方案推荐
    if ocr != "off":
        _show_device_profile(ocr_engine)

    # Step 1: 提取
    lines, meta = extract_pdf(
        str(pdf),
        max_pages=max_pages,
        filter_header_footer=not no_filter,
        ocr_mode=cast(OcrMode, ocr),
        ocr_engine=cast(OcrEngineChoice, ocr_engine),
    )
    click.echo(f"  提取 | 行: {len(lines)} | 法规: {meta.name or '?'}", err=True)

    # Step 2: 结构识别
    tree = parse_structure(lines, doc_type=meta.doc_type, meta=meta)
    total_articles = sum(1 for top in tree for _ in _walk_articles(top))
    click.echo(f"  结构 | 条: {total_articles} | 类型: {meta.doc_type.value}", err=True)

    # 校验条号连续性
    if validate:
        issues = _validate_article_sequence(tree)
        if issues:
            click.echo("  校验 | 发现问题:", err=True)
            for issue in issues:
                click.echo(f"    - {issue}", err=True)
        else:
            click.echo("  校验 | 条号连续性检查通过", err=True)

    # Step 3: 生成输出
    if output_format == "json":
        data = _tree_to_json(tree, meta)
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        click.echo(f"  JSON | → {output}", err=True)
    else:
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
    "--workers",
    type=int,
    default=1,
    show_default=True,
    help="并行工作进程数（>1 时启用多进程）",
)
@click.option(
    "--ocr",
    type=click.Choice(["auto", "force", "off"]),
    default="off",
    show_default=True,
    help="OCR 模式: auto=对无文字页面回退, force=强制所有页面, off=禁用",
)
@click.option(
    "--ocr-engine",
    type=click.Choice(["auto", "paddle", "lite"]),
    default="auto",
    show_default=True,
    help="OCR 引擎: auto=根据设备性能自动推荐, paddle=PaddleOCR高性能, lite=RapidOCR轻量版",
)
def batch(
    pdf_dir: str,
    output: str,
    max_pages: Optional[int],
    flatten: bool,
    no_filter: bool,
    workers: int,
    ocr: str,
    ocr_engine: str,
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

    # 展示设备性能检测和 OCR 方案推荐
    if ocr != "off":
        _show_device_profile(ocr_engine)

    # 构建任务参数
    tasks = []
    for pdf_path in pdf_files:
        rel = pdf_path.relative_to(src_dir)
        out_name = rel.with_suffix(".md")
        if flatten:
            out_path = out_dir / out_name.name
        else:
            out_path = out_dir / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
        tasks.append((str(pdf_path), str(out_path)))

    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        def _process_one(args):
            pdf_path, out_path = args
            try:
                lines, meta = extract_pdf(
                    pdf_path,
                    max_pages=max_pages,
                    filter_header_footer=not no_filter,
                    ocr_mode=cast(OcrMode, ocr),
                    ocr_engine=cast(OcrEngineChoice, ocr_engine),
                )
                tree = parse_structure(lines, doc_type=meta.doc_type, meta=meta)
                md = build_markdown(tree, meta, include_toc=False, article_anchor=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(md)
                return Path(pdf_path).name, None
            except Exception as e:
                return Path(pdf_path).name, str(e)

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_process_one, t): t for t in tasks}
            try:
                from tqdm import tqdm
                pbar = tqdm(total=len(tasks), desc="批量处理", unit="file")
            except ImportError:
                pbar = None

            for future in as_completed(futures):
                name, error = future.result()
                if pbar:
                    pbar.set_postfix_str(f"{'❌' if error else '✓'} {name}")
                    pbar.update(1)
                else:
                    if error:
                        click.echo(f"  ❌ {name}: {error}", err=True)

            if pbar:
                pbar.close()
    else:
        try:
            from tqdm import tqdm
            pbar = tqdm(tasks, desc="批量处理", unit="file")
        except ImportError:
            pbar = None

        iterable = pbar if pbar else tasks
        for pdf_path_str, out_path_str in iterable:
            try:
                lines, meta = extract_pdf(
                    pdf_path_str,
                    max_pages=max_pages,
                    filter_header_footer=not no_filter,
                    ocr_mode=cast(OcrMode, ocr),
                    ocr_engine=cast(OcrEngineChoice, ocr_engine),
                )
                tree = parse_structure(lines, doc_type=meta.doc_type, meta=meta)
                md = build_markdown(tree, meta, include_toc=False, article_anchor=True)
                with open(out_path_str, "w", encoding="utf-8") as f:
                    f.write(md)

                if pbar:
                    pbar.set_postfix_str(f"✓ {Path(pdf_path_str).name}")

                del lines, tree, meta, md
                import gc
                gc.collect()
            except Exception as e:
                if pbar:
                    pbar.set_postfix_str(f"❌ {Path(pdf_path_str).name}")
                else:
                    click.echo(f"  ❌ {Path(pdf_path_str).name}: {e}", err=True)

        if pbar:
            pbar.close()

    click.echo(f"批量完成. 输出至: {out_dir}", err=True)


# ── 性能检测命令 ──────────────────────────────────────────

@cli.command()
def profile() -> None:
    """检测设备性能并显示 OCR 方案推荐。"""
    from src.profiler import detect_device_profile, recommend_ocr_backend
    from src.ocr import is_paddle_available, is_lite_available

    profile_result = detect_device_profile()
    recommended = recommend_ocr_backend(profile_result)

    click.echo(profile_result.summary(), err=True)
    click.echo("", err=True)

    # 显示可用后端
    paddle_ok = is_paddle_available()
    lite_ok = is_lite_available()

    click.echo("OCR 后端可用性:", err=True)
    click.echo(f"  PaddleOCR (高性能): {'已安装' if paddle_ok else '未安装 (pip install lawtomd[ocr])'}", err=True)
    click.echo(f"  RapidOCR (轻量版): {'已安装' if lite_ok else '未安装 (pip install lawtomd[ocr-lite])'}", err=True)
    click.echo("", err=True)

    if recommended == "paddle" and not paddle_ok:
        click.echo("注意: 推荐 PaddleOCR 但未安装，将回退到 RapidOCR", err=True)
    elif recommended == "lite" and not lite_ok:
        click.echo("注意: 推荐 RapidOCR 但未安装，将回退到 PaddleOCR", err=True)


# ── 辅助 ──────────────────────────────────────────────────

def _walk_articles(node):
    if node.level == Level.ARTICLE:
        yield node
    for child in node.children:
        yield from _walk_articles(child)


def _validate_article_sequence(tree: list) -> list[str]:
    """校验条号连续性，返回问题列表。"""
    from src.patterns import cn_to_arabic
    issues: list[str] = []
    prev_num = 0

    for node in tree:
        for article in _walk_articles(node):
            if not article.number:
                continue
            # 处理"之一""之二"后缀
            parts = article.number.split("之")
            try:
                current_num = cn_to_arabic(parts[0])
            except (ValueError, IndexError):
                continue

            if prev_num > 0 and current_num > prev_num + 1:
                issues.append(
                    f"条号不连续: 第{prev_num}条 → 第{current_num}条 (缺失第{prev_num + 1}条)"
                )
            prev_num = max(prev_num, current_num)

    return issues


def _tree_to_json(tree: list, meta: LawMeta) -> dict:
    """将 HierarchyNode 树序列化为 JSON 友好的字典。"""
    return {
        "meta": {
            "name": meta.name,
            "doc_id": meta.doc_id,
            "doc_type": meta.doc_type.value,
            "publish_date": meta.publish_date,
            "effective_date": meta.effective_date,
            "issuing_authority": meta.issuing_authority,
            "source_pdf": meta.source_pdf,
            **meta.extra,
        },
        "tree": [_node_to_dict(n) for n in tree],
    }


def _node_to_dict(node) -> dict:
    """递归将 HierarchyNode 转为字典。"""
    return {
        "level": node.level.value,
        "title": node.title,
        "text": node.text,
        "number": node.number,
        "page_num": node.page_num,
        "hierarchy_path": node.hierarchy_path,
        "law_references": node.law_references,
        "children": [_node_to_dict(c) for c in node.children],
    }


if __name__ == "__main__":
    cli()
