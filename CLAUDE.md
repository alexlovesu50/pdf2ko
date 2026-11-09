# CLAUDE.md

이 프로젝트의 에이전트 작업 지침은 AGENTS.md에 있다. Claude Code도 아래 지침을 그대로 따른다.

@AGENTS.md

## Claude Code 실행 메모

- 번역 요청은 [번역 지침](agents/translator.md), 한글 PDF 생성 요청은 [PDF 편집 지침](agents/editor.md)을 읽고 따른다.
- 프로젝트 명령은 `scripts/run.sh`로 실행한다. 스크립트는 `PDF2KO_PYTHON` → `.venv/bin/python` → `python3` 순서로 Python을 찾는다.
- PdfCraft MCP는 저장소의 `.mcp.json`으로 등록된다. 도구 이름은 `mcp__pdfcraft__*` 형태이며, AGENTS.md의 `tool_search`·`command_list`·`doc_open`·`doc_save`는 이 서버의 도구를 가리킨다. 서버가 연결되지 않았으면 한글 PDF 생성을 중단하고 `/mcp`로 연결 상태를 확인하라고 안내한다.
- PDF를 직접 읽을 때는 Read 도구(`pages` 인자)로 원본 페이지를 확인할 수 있다.
