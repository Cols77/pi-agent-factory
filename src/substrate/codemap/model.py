from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IndexSignature:
    kind: str
    name: str
    signature: str
    line: int
    summary: str = ""


@dataclass
class IndexFile:
    language: str
    module_doc: str = ""
    signatures: list[IndexSignature] = field(default_factory=list)


@dataclass
class CodeIndex:
    schema: int = 1
    engine: str = "stdlib-ast"
    generated_at: str = ""
    fingerprint: str = ""
    files: dict[str, IndexFile] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "CodeIndex":
        files: dict[str, IndexFile] = {}
        for rel, f in (data.get("files") or {}).items():
            sigs = [
                IndexSignature(
                    kind=s.get("kind", "function"),
                    name=s.get("name", ""),
                    signature=s.get("signature", ""),
                    line=int(s.get("line", 0)),
                    summary=s.get("summary", ""),
                )
                for s in (f.get("signatures") or [])
            ]
            files[rel] = IndexFile(
                language=f.get("language", ""),
                module_doc=f.get("module_doc", ""),
                signatures=sigs,
            )
        return cls(
            schema=int(data.get("schema", 1)),
            engine=data.get("engine", "stdlib-ast"),
            generated_at=data.get("generated_at", ""),
            fingerprint=data.get("fingerprint", ""),
            files=files,
        )

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "engine": self.engine,
            "generated_at": self.generated_at,
            "fingerprint": self.fingerprint,
            "files": {
                rel: {
                    "language": f.language,
                    "module_doc": f.module_doc,
                    "signatures": [
                        {
                            "kind": s.kind,
                            "name": s.name,
                            "signature": s.signature,
                            "line": s.line,
                            "summary": s.summary,
                        }
                        for s in f.signatures
                    ],
                }
                for rel, f in self.files.items()
            },
        }
