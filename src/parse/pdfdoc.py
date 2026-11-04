from __future__ import annotations

import threading
from pathlib import Path

import pypdfium2 as pdfium

# pdfium 不是线程安全的：即使是不同文档，并发调用也会让进程直接崩溃（5 线程并发解析实测必现）。
# 解析任务跑在线程池里，所以本进程内所有 pdfium 调用都经过这把锁串行。
_PDFIUM_LOCK = threading.RLock()


class PdfDoc:
    """PDF 文本层访问器（ADR-002：pypdfium2，宽松许可证）。

    页码统一为 1 基（对应用户看到的 PDF 页码），对外不暴露 0 基索引。
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with _PDFIUM_LOCK:
            self._doc = pdfium.PdfDocument(self.path)
            self._page_count = len(self._doc)
        self._text_cache: dict[int, str] = {}

    @property
    def page_count(self) -> int:
        return self._page_count

    def page_text(self, page_number: int) -> str:
        """page_number 为 1 基页码。"""
        if page_number < 1 or page_number > self.page_count:
            raise IndexError(f"页码越界：{page_number}（共 {self.page_count} 页）")
        index = page_number - 1
        if index not in self._text_cache:
            with _PDFIUM_LOCK:
                page = self._doc[index]
                try:
                    textpage = page.get_textpage()
                    try:
                        self._text_cache[index] = textpage.get_text_range()
                    finally:
                        textpage.close()
                finally:
                    page.close()
        return self._text_cache[index]

    def bookmarks(self) -> list[tuple[str, int]]:
        """返回 (标题, 页码) 列表，页码为 1 基；用于独立校验三表位置。"""
        result: list[tuple[str, int]] = []
        with _PDFIUM_LOCK:
            for bookmark in self._doc.get_toc():
                try:
                    title = bookmark.get_title() or ""
                except Exception:  # pragma: no cover - 损坏书签
                    continue
                try:
                    page_number = bookmark.get_dest().get_index() + 1
                except Exception:  # pragma: no cover - 缺失目标
                    continue
                if title and page_number >= 1:
                    result.append((title, page_number))
        return result

    def close(self) -> None:
        with _PDFIUM_LOCK:
            self._doc.close()

    def __enter__(self) -> PdfDoc:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
