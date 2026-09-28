import hashlib
import html.parser
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3", "h4", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)

    def text(self) -> str:
        raw = " ".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.split("\n")]
        return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class OfficialSource:
    id: str
    priority: int
    category: str
    title: str
    url: str
    authority: str
    purpose: str


class OfficialHealthSourceCollector:
    def __init__(self, registry_path: Path, output_root: Path) -> None:
        self.registry_path = registry_path
        self.output_root = output_root
        self.registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self.allowed_domains = set(self.registry["policy"]["allowed_domains"])

    def sources(self) -> list[OfficialSource]:
        return [OfficialSource(**source) for source in self.registry["sources"]]

    def validate_url(self, url: str) -> None:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if host not in self.allowed_domains:
            raise ValueError(f"Refusing non-allowlisted source: {url}")

    def fetch(self, source: OfficialSource) -> tuple[str, bytes, str]:
        self.validate_url(source.url)
        request = Request(source.url, headers={"User-Agent": "PROXY-OfficialHealthKnowledgeCollector/0.1"})
        with urlopen(request, timeout=30) as response:
            content_type = response.headers.get("content-type", "")
            body = response.read()
            final_url = response.geturl()
        return final_url, body, content_type

    def body_to_text(self, body: bytes, content_type: str) -> str:
        if "html" in content_type.lower() or body.lstrip().startswith(b"<!") or body.lstrip().startswith(b"<html"):
            extractor = TextExtractor()
            extractor.feed(body.decode("utf-8", errors="ignore"))
            return extractor.text()
        return body.decode("utf-8", errors="ignore")

    def write_source(self, source: OfficialSource, final_url: str, body: bytes, content_type: str, text: str) -> dict:
        category_dir = self.output_root / source.category
        metadata_dir = self.output_root / "metadata"
        category_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(body).hexdigest()
        collected_at = datetime.now(timezone.utc).isoformat()
        text_path = category_dir / f"{source.id}.md"
        metadata_path = metadata_dir / f"{source.id}.json"

        front_matter = [
            "---",
            f"source_id: {source.id}",
            f"title: {source.title}",
            f"authority: {source.authority}",
            f"category: {source.category}",
            f"priority: {source.priority}",
            f"url: {source.url}",
            f"final_url: {final_url}",
            f"collected_at: {collected_at}",
            f"content_sha256: {digest}",
            "---",
            "",
            f"# {source.title}",
            "",
            f"Authority: {source.authority}",
            f"Purpose: {source.purpose}",
            f"Citation URL: {final_url}",
            "",
            text,
            "",
        ]
        text_path.write_text("\n".join(front_matter), encoding="utf-8")
        metadata = {
            "source_id": source.id,
            "title": source.title,
            "authority": source.authority,
            "category": source.category,
            "priority": source.priority,
            "url": source.url,
            "final_url": final_url,
            "content_type": content_type,
            "content_sha256": digest,
            "collected_at": collected_at,
            "text_path": str(text_path),
            "purpose": source.purpose,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def collect(self, limit: int | None = None) -> dict:
        results: list[dict] = []
        errors: list[dict] = []
        sources = self.sources()[:limit] if limit else self.sources()
        for source in sources:
            try:
                final_url, body, content_type = self.fetch(source)
                text = self.body_to_text(body, content_type)
                metadata = self.write_source(source, final_url, body, content_type, text)
                results.append(metadata)
            except Exception as exc:
                errors.append({"source_id": source.id, "url": source.url, "error": str(exc)})
        return {"collected": len(results), "failed": len(errors), "results": results, "errors": errors}
