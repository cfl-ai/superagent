"""第 2 层：网络智能探索（修订版第 5 节(二)）。

- fetch：抓取网页（记录来源 + 内容哈希）
- search：DuckDuckGo 全文检索（无需 API key），结果登记来源
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request

from superagent.core.errors import SuperAgentError
from superagent.layers.base import Layer, TaskContext


class NetworkLayer(Layer):
    name = "layer2_network"

    def run(self, ctx: TaskContext, runtime) -> dict:
        result: dict = {"fetched": [], "searched": [], "sources": 0}
        for ref in ctx.plan.get("references", []):
            if ref.get("kind") == "url":
                try:
                    body = self.fetch(ref["url"])
                    runtime.sources.add(
                        "url",
                        ref.get("title", ref["url"]),
                        ref["url"],
                        content=body,
                        license_note=ref.get("license", ""),
                        cited_at=ref.get("cited_at", ""),
                    )
                    result["fetched"].append(ref["url"])
                    result["sources"] += 1
                except SuperAgentError as exc:
                    ctx.note(f"抓取失败 {ref['url']}: {exc}")
        # 搜索查询
        for q in ctx.plan.get("search_queries", []):
            try:
                hits = self.search(q, max_results=5)
                for h in hits:
                    runtime.sources.add("url", h["title"], h["url"], cited_at="检索")
                result["searched"].append({"query": q, "hits": hits})
                result["sources"] += len(hits)
            except SuperAgentError as exc:
                ctx.note(f"检索失败 {q}: {exc}")
        return result

    def fetch(self, url: str, timeout_s: float = 20.0) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "SuperAgent/0.1 (+source-trace)"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        except (urllib.error.URLError, OSError) as exc:
            raise SuperAgentError(f"网络抓取失败 {url}: {exc}") from exc

    def search(self, query: str, max_results: int = 5, timeout_s: float = 15.0) -> list[dict]:
        """全网检索：Bing 优先（国内可用），DuckDuckGo 回退。返回 [{title, url}]。"""
        errors = []
        for fn in (self._search_bing, self._search_ddg):
            try:
                results = fn(query, max_results, timeout_s)
                if results:
                    return results
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        raise SuperAgentError(f"检索失败 {query}: {'; '.join(errors) or '无结果'}")

    @staticmethod
    def _ua() -> str:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SuperAgent/0.1"

    def _search_bing(self, query: str, max_results: int, timeout_s: float) -> list[dict]:
        url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": self._ua()})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            html = resp.read().decode("utf-8", "replace")
        results = []
        for m in re.finditer(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            href = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if href.startswith("http") and title:
                results.append({"title": title, "url": href})
            if len(results) >= max_results:
                break
        return results

    def _search_ddg(self, query: str, max_results: int, timeout_s: float) -> list[dict]:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": self._ua()})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            html = resp.read().decode("utf-8", "replace")
        results = []
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            href = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            real = self._resolve_ddg_url(href)
            if real:
                results.append({"title": title, "url": real})
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _resolve_ddg_url(href: str) -> str | None:
        if "uddg=" in href:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            if "uddg" in params:
                return params["uddg"][0]
        if href.startswith("//"):
            href = "https:" + href
        return href if href.startswith("http") else None
