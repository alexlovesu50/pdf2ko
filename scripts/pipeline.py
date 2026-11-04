#!/usr/bin/env python3
"""pdf2ko workflow. Translation and visual editing are agent tasks."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import html
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

if os.name == "nt":
    import msvcrt
else:
    import fcntl

PROJECT = Path(__file__).resolve().parent.parent
SCHEMA = 1
TRANSLATION_HEADERS = ["문단id", "pdf페이지", "영어 원문", "한국어 번역"]
GLOSSARY_HEADERS = ["용어 id", "영어 용어", "한국어 번역"]
REVIEW_FILES = ("trans.md", "glossary.md")


class WorkflowError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise WorkflowError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"JSON을 읽을 수 없습니다: {path}: {exc}") from exc


def write_json(path, value, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".json-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        if replace:
            os.replace(name, path)
        else:
            os.link(name, path)  # Refuse replacement even if another process created it.
    finally:
        Path(name).unlink(missing_ok=True)


def copy_new(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Path(source).open("rb") as src, target.open("xb") as dst:
        shutil.copyfileobj(src, dst)


def identifier(value, label="문서 ID"):
    require(isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", value),
            f"{label}: 영문 소문자·숫자·하이픈을 사용하세요 (최대 80자).")
    return value


def text_value(value, label, *, optional=False):
    if value is None and optional:
        return ""
    require(isinstance(value, str), f"{label}: 문자열이어야 합니다.")
    require(optional or bool(value.strip()), f"{label}: 빈 값입니다.")
    return value


def pdf_info(path):
    from pypdf import PdfReader
    import pdfplumber
    try:
        reader = PdfReader(str(path))
        require(not reader.is_encrypted, "암호화된 PDF는 암호를 해제한 사본으로 등록하세요.")
        require(len(reader.pages) > 0, "빈 PDF는 등록할 수 없습니다.")
        # Use the same displayed coordinate system as extract(), including /Rotate.
        with pdfplumber.open(path) as pdf:
            return [{"page": page.page_number, "width": float(page.width),
                     "height": float(page.height), "rotation": page.rotation}
                    for page in pdf.pages]
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError(f"유효한 PDF를 읽을 수 없습니다: {path}: {exc}") from exc


def init(root):
    for name in ("inbox", "documents"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return {"root": str(root), "inbox": str(root / "inbox")}


def document(root, doc_id):
    path = root / "documents" / identifier(doc_id)
    require(path.is_dir() and not path.is_symlink(), f"문서를 찾을 수 없습니다: {doc_id}")
    meta = read_json(path / "document.json")
    require(meta.get("document_id") == doc_id, "문서 ID가 메타데이터와 다릅니다.")
    source = path / meta["source"]["path"]
    require(source.resolve().is_relative_to((path / "source").resolve()), "원본 경로가 source 밖입니다.")
    require(source.is_file() and not source.is_symlink(), "원본 PDF가 없습니다.")
    require(sha256(source) == meta["source"]["sha256"], "원본 PDF가 변경되었습니다. 개정판은 별도 문서로 등록하세요.")
    return path, meta, source


def register(root, pdf, doc_id=None, kind="other"):
    init(root)
    original = Path(pdf).expanduser().absolute()
    require(original.is_file() and not original.is_symlink(), f"입력 PDF가 없습니다: {original}")
    original = original.resolve()
    require(original.is_relative_to((root / "inbox").resolve()), "새 PDF를 먼저 프로젝트 inbox에 넣으세요.")
    require(original.suffix.lower() == ".pdf", "PDF 파일만 등록할 수 있습니다.")
    source_hash = sha256(original)
    for metadata_path in sorted((root / "documents").glob("*/document.json")):
        meta = read_json(metadata_path)
        if meta.get("source", {}).get("sha256") == source_hash:
            document(root, meta["document_id"])
            return {"document_id": meta["document_id"], "duplicate": True,
                    "path": str(metadata_path.parent), "inbox_file_preserved": str(original)}
    pages = pdf_info(original)
    if not doc_id:
        stem = re.sub(r"[^a-z0-9]+", "-", original.stem.lower()).strip("-")[:65] or "document"
        doc_id = f"{stem}-{source_hash[:8]}"
    identifier(doc_id)
    destination = root / "documents" / doc_id
    require(not destination.exists(), f"이미 사용 중인 문서 ID입니다: {doc_id}. 개정판은 새 ID를 사용하세요.")
    staging = Path(tempfile.mkdtemp(prefix=".register-", dir=root / "documents"))
    try:
        for name in ("source", "work", "review", "output"):
            (staging / name).mkdir()
        shutil.copy2(original, staging / "source" / original.name)
        require(sha256(staging / "source" / original.name) == source_hash, "복사 중 PDF가 변경되었습니다.")
        meta = {"schema_version": SCHEMA, "document_id": doc_id, "kind": kind,
                "registered_at": now(), "source": {"filename": original.name,
                "path": f"source/{original.name}", "sha256": source_hash,
                "page_count": len(pages), "pages": pages}}
        write_json(staging / "document.json", meta)
        staging.rename(destination)
        if sha256(original) == source_hash:
            original.unlink()
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"document_id": doc_id, "duplicate": False, "path": str(destination)}


def extract(root, doc_id):
    """Read source text/coordinates without creating an intermediate file."""
    import pdfplumber
    _, meta, source = document(root, doc_id)
    pages = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            pages.append({"page": page.page_number, "width": page.width, "height": page.height,
                          "text": page.extract_text() or "", "words": [
                              {"text": w["text"], "bbox": [w["x0"], w["top"], w["x1"], w["bottom"]]}
                              for w in words]})
    empty_pages = [p["page"] for p in pages if not p["text"].strip()]
    require(not empty_pages, f"텍스트가 없는 페이지 {empty_pages}: OCR과 원본 대조가 필요합니다.")
    return {"document_id": doc_id, "source_sha256": meta["source"]["sha256"],
            "coordinate_system": "PDF points; origin top-left; bbox=[x0,top,x1,bottom]", "pages": pages}


def markdown_cells(line):
    """Decode the small table format, preserving escaped pipes and backslashes."""
    line = line.strip()
    require(line.startswith("|") and line.endswith("|"), "MD 표의 각 행은 |로 시작하고 끝나야 합니다.")
    cells, current, index = [], [], 1
    while index < len(line) - 1:
        char = line[index]
        if char == "\\" and index + 1 < len(line) - 1 and line[index + 1] in "|\\":
            current.append(line[index + 1])
            index += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return [html.unescape(re.sub(r"<br\s*/?>", "\n", cell, flags=re.I)) for cell in cells]


def read_table(path, headers):
    require(path.is_file(), f"검토 파일이 없습니다: {path.name}")
    lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    require(len(lines) >= 2, f"{path.name}: 표 머리글이 필요합니다.")
    require(markdown_cells(lines[0]) == headers, f"{path.name}: 열은 {headers}여야 합니다.")
    separator = markdown_cells(lines[1])
    require(len(separator) == len(headers) and all(re.fullmatch(r":?-{3,}:?", c) for c in separator),
            f"{path.name}: 표 구분선이 잘못되었습니다.")
    rows = []
    seen = set()
    for number, line in enumerate(lines[2:], start=3):
        row = markdown_cells(line)
        require(len(row) == len(headers), f"{path.name} {number}행: 열 수가 다릅니다. 본문의 |는 \\|로 입력하세요.")
        require(all(cell.strip() for cell in row), f"{path.name} {number}행: 빈 값이 있습니다.")
        key = row[0]
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", key) and key not in seen,
                f"{path.name}: 잘못되거나 중복된 ID: {key}")
        seen.add(key)
        rows.append(row)
    return rows


def review_hashes(path):
    hashes = {}
    for name in REVIEW_FILES:
        file = path / "review" / name
        require(file.is_file() and not file.is_symlink(), f"검토 MD 파일이 없거나 링크입니다: {name}")
        hashes[name] = sha256(file)
    return hashes


def review_content(root, doc_id):
    """Read the user's saved Markdown; never write a draft or approval copy."""
    path, meta, _ = document(root, doc_id)
    before = review_hashes(path)
    rows = read_table(path / "review/trans.md", TRANSLATION_HEADERS)
    require(rows, "trans.md에 번역 문단이 없습니다.")
    segments = []
    for key, page, source_text, final_ko in rows:
        require(page.isascii() and page.isdigit() and 1 <= int(page) <= meta["source"]["page_count"],
                f"{key}: 잘못된 PDF 페이지: {page}")
        segments.append({"id": key, "page": int(page), "source_text": source_text, "final_ko": final_ko})
    glossary = [{"id": key, "en": en, "ko": ko} for key, en, ko in
                read_table(path / "review/glossary.md", GLOSSARY_HEADERS)]
    require(review_hashes(path) == before, "읽는 동안 MD가 변경되었습니다. 저장을 완료한 뒤 다시 실행하세요.")
    return {"segments": sorted(segments, key=lambda s: (s["page"], s["id"])),
            "glossary": sorted(glossary, key=lambda t: t["id"])}


def output_versions(path):
    versions = {item.name for item in (path / "output").glob("v*")
                if item.is_dir() and re.fullmatch(r"v\d{3,}", item.name)}
    for item in (path / "output").glob(f"{path.name}-ko-v*.pdf"):
        match = re.fullmatch(re.escape(path.name) + r"-ko-(v\d{3,})\.pdf", item.name)
        if match:
            versions.add(match[1])
    return sorted(versions, key=lambda version: int(version[1:]))


def next_version(path):
    versions = [int(version[1:]) for version in output_versions(path)]
    for folder, prefix in (("work", "edit-"), ("approved", "")):
        for item in (path / folder).glob(f"{prefix}v*"):
            match = re.fullmatch(prefix + r"v(\d{3,})", item.name)
            if match:
                versions.append(int(match[1]))
    return f"v{max(versions, default=0) + 1:03d}"


def edit_job(path, meta, source, version):
    return {"schema_version": 3, "document_id": meta["document_id"], "version": version,
            "pdf_editor": "PdfCraft MCP", "tool_namespace": "mcp__pdfcraft", "fallback_allowed": False,
            "source_pdf": str(source), "source_sha256": meta["source"]["sha256"],
            "trans_md": str(path / "review/trans.md"), "glossary_md": str(path / "review/glossary.md"),
            "review_sha256": review_hashes(path),
            "candidate_pdf": str(path / "work" / f"edit-{version}" / "candidate.pdf"),
            "output_pdf": str(path / "output" / f"{meta['document_id']}-ko-{version}.pdf")}


def verified_job(root, doc_id, version):
    require(re.fullmatch(r"v\d{3,}", version), "편집 버전은 v001 형식이어야 합니다.")
    path, meta, source = document(root, doc_id)
    job_path = path / "work" / f"edit-{version}" / "edit-job.json"
    job = read_json(job_path)
    require(job == edit_job(path, meta, source, version),
            "MD 또는 편집 작업 정보가 변경되었습니다. 저장된 MD로 prepare-edit를 새로 실행하세요.")
    return path, meta, source, job_path, job


def prepare_edit(root, doc_id, version=None):
    path, meta, source = document(root, doc_id)
    before = review_hashes(path)
    review_content(root, doc_id)
    require(review_hashes(path) == before, "검증 중 MD가 변경되었습니다. 다시 실행하세요.")
    if version is not None:
        path, meta, source, job_path, job = verified_job(root, doc_id, version)
    else:
        version = next_version(path)
        job = edit_job(path, meta, source, version)
        require(job["review_sha256"] == before, "준비 중 MD가 변경되었습니다. 다시 실행하세요.")
        job_path = path / "work" / f"edit-{version}" / "edit-job.json"
        write_json(job_path, job)
    require(version not in output_versions(path) and not (job_path.parent / "receipt.json").exists(),
            "이 버전의 결과가 이미 있습니다. 새 편집 버전을 사용하세요.")
    return {"path": str(job_path), **job}


def publish(root, doc_id, version, pdf):
    path, meta, source, job_path, job = verified_job(root, doc_id, version)
    candidate = Path(pdf).expanduser().resolve()
    expected_candidate = path / "work" / f"edit-{version}" / "candidate.pdf"
    require(not expected_candidate.is_symlink() and candidate == expected_candidate.resolve(),
            "이 문서·편집 버전의 work/edit-vNNN/candidate.pdf만 게시할 수 있습니다.")
    require(candidate.is_file() and candidate != source.resolve(), "별도 편집 결과 PDF를 지정하세요.")
    candidate_hash = sha256(candidate)
    require(candidate_hash != meta["source"]["sha256"], "원본 PDF를 번역 결과로 게시할 수 없습니다.")
    require(len(pdf_info(candidate)) == meta["source"]["page_count"], "원본과 결과의 페이지 수가 다릅니다.")
    target = Path(job["output_pdf"])
    receipt_path = job_path.parent / "receipt.json"
    require(not target.exists() and not target.is_symlink() and
            not receipt_path.exists() and not receipt_path.is_symlink() and
            not (path / "output" / version).exists(), "기존 결과 버전은 덮어쓸 수 없습니다.")
    staging = Path(tempfile.mkdtemp(prefix=".publish-", dir=path / "output"))
    try:
        filename = target.name
        copy_new(candidate, staging / filename)
        require(sha256(staging / filename) == candidate_hash == sha256(candidate), "게시 중 후보 PDF가 변경되었습니다.")
        verified_job(root, doc_id, version)
        write_json(staging / "receipt.json", {"document_id": doc_id, "version": version,
                   "pdf_editor": "PdfCraft MCP", "source_sha256": meta["source"]["sha256"],
                   "review_sha256": job["review_sha256"], "pdf_sha256": candidate_hash,
                   "published_at": now()})
        os.link(staging / "receipt.json", receipt_path)
        try:
            os.link(staging / filename, target)
        except OSError:
            receipt_path.unlink()
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"path": str(target), "version": version}


def status(root, doc_id=None):
    metadata = ([root / "documents" / identifier(doc_id) / "document.json"] if doc_id
                else sorted((root / "documents").glob("*/document.json")))
    result = []
    for file in metadata:
        meta = read_json(file)
        path, _, _ = document(root, meta["document_id"])
        entry = {"document_id": meta["document_id"], "kind": meta["kind"],
                 "review_exists": all((path / "review" / name).is_file() for name in REVIEW_FILES),
                 "output_versions": output_versions(path)}
        if entry["review_exists"]:
            try:
                content = review_content(root, meta["document_id"])
                entry.update(review_ready=True, segments=len(content["segments"]), terms=len(content["glossary"]))
            except WorkflowError as exc:
                entry.update(review_ready=False, review_issues=str(exc))
        result.append(entry)
    return {"documents": result}


@contextmanager
def project_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".pipeline.lock").open("a+b") as stream:
        if os.name == "nt":
            # Windows에서도 첫 바이트를 잠가 동시 변경 방지
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="pdf2ko: 두 Markdown 파일을 사용하는 PDF 번역·편집")
    parser.add_argument("--root", type=Path, default=PROJECT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    cmd = commands.add_parser("register")
    cmd.add_argument("--pdf", required=True)
    cmd.add_argument("--id", dest="doc_id")
    cmd.add_argument("--kind", choices=["boardgame", "research paper", "other"],
                     default="other")
    for name in ("extract", "validate", "prepare-edit", "publish", "status"):
        cmd = commands.add_parser(name)
        cmd.add_argument("doc_id", nargs="?" if name == "status" else None)
        if name in ("prepare-edit", "publish"):
            cmd.add_argument("--version", required=name == "publish")
        if name == "publish":
            cmd.add_argument("--pdf", required=True)
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        with project_lock(root):
            if args.command == "init": result = init(root)
            elif args.command == "register": result = register(root, args.pdf, args.doc_id, args.kind)
            elif args.command == "extract": result = extract(root, args.doc_id)
            elif args.command == "validate":
                content = review_content(root, args.doc_id)
                result = {"valid": True, "segments": len(content["segments"]), "terms": len(content["glossary"])}
            elif args.command == "prepare-edit": result = prepare_edit(root, args.doc_id, args.version)
            elif args.command == "publish": result = publish(root, args.doc_id, args.version, args.pdf)
            else: result = status(root, args.doc_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkflowError, OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
