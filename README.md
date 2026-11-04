# pdf2ko

pdf2ko는 Codex로 영문 PDF를 한국어로 번역하는 프로젝트입니다.
번역을 요청하면 Codex가 문서별 폴더(`documents/<id>/`)에 용어집과 본문 대조표를 작성합니다. 두 파일을 검토하고 저장한 뒤 한글 PDF 생성을 요청하면, 본문 대조표에 저장한 번역을 원본 PDF에 반영합니다.

| 파일 | 용도 |
| --- | --- |
| `review/glossary.md` | **용어집**. 영어 용어와 한국어 표기를 짝지어 정리합니다. 같은 용어를 문서 전체에서 어떻게 옮길지 정할 때 봅니다. |
| `review/trans.md` | **본문 대조표**. PDF 페이지별로 영어 원문과 한국어 번역을 나란히 보여 줍니다. 한글 PDF에 들어갈 문장을 여기서 다듬습니다. |


## 번역 예시

**NumPy로 하는 배열 프로그래밍**은 pdf2ko로 영문 논문을 한국어로 번역하고 지면에 맞춰 다시 조판한 비공식 번역 예시입니다.

[영문 원본 PDF](examples/Array_programming_with_NumPy.pdf) · [한국어 번역 PDF (v001)](examples/array-programming-with-numpy-ko-v001.pdf)

원문은 Charles R. Harris 외 저자들의 「Array programming with NumPy」로, *Nature* 585, 357–362 (2020)에 실렸습니다. © The Author(s) 2020. [원문 DOI](https://doi.org/10.1038/s41586-020-2649-2) · [원문 라이선스 CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)


## 번역 요청부터 한글 PDF까지

1. **번역을 요청합니다.** `inbox/`에 영문 PDF를 넣고 이 프로젝트를 연 Codex에 “`inbox/Example Rules.pdf`를 번역해 줘.”라고 요청합니다.
2. **두 파일을 검토하고 저장합니다.** 용어집과 본문 대조표에서 `한국어 번역` 열을 수정합니다. 용어집에서 ‘게임판’을 ‘보드’로 바꿨다면 본문 대조표에서도 해당 표현을 바꿉니다.
3. **한글 PDF 생성을 요청합니다.** “저장한 번역으로 `Example Rules.pdf`의 한글 PDF를 만들어 줘.”라고 요청하면 Codex가 현재 저장된 번역을 원본에 반영합니다.
4. **결과를 확인합니다.** 전달받은 PDF를 열어 번역 누락, 글자 잘림, 표나 그림과의 겹침을 확인합니다. 결과는 `documents/<id>/output/<id>-ko-v001.pdf`처럼 버전별로 저장됩니다.


## 실행 환경 준비

Codex에서 이 저장소를 엽니다. 한글 PDF를 생성하려면 Codex에서 **PdfCraft MCP**를 사용할 수 있어야 합니다.

Python 가상 환경을 활성화한 뒤 저장소 최상위 폴더에서 아래 명령을 실행합니다. 예시는 `sh` 호환 셸 기준이며 Windows에서는 Git Bash를 사용할 수 있습니다.

```sh
export PDF2KO_PYTHON=python
python -m pip install -r requirements.txt
scripts/setup.sh
```

`setup.sh`는 Python 의존성을 확인하고 `inbox/`와 `documents/`를 준비합니다.

## 검토 파일 편집 예시

두 파일 모두 아래와 같은 표 하나로 구성됩니다. 표 머리글, ID, PDF 페이지, 영어 원문은 그대로 두고 한국어 번역을 수정합니다.

**용어집** (`review/glossary.md`)

| 용어 id | 영어 용어 | 한국어 번역 |
| --- | --- | --- |
| term-001 | board | 게임판 |

**본문 대조표** (`review/trans.md`)

| 문단id | pdf페이지 | 영어 원문 | 한국어 번역 |
| --- | --- | --- | --- |
| p001-s001 | 1 | Place the board on the table. | 게임판을 탁자 위에 놓습니다. |

본문의 한 행은 문단, 제목, 목록 항목, 그림 설명처럼 의미가 통하는 한 단위입니다. 페이지 번호는 PDF의 첫 페이지를 1로 셉니다.

셀 안에서 줄을 바꿀 때는 `<br>`를 씁니다. 세로줄과 역슬래시는 각각 `\|`와 `\\`로, 문자 그대로의 `&`, `<`, `>`는 각각 `&amp;`, `&lt;`, `&gt;`로 씁니다.

## 명령어 참고

번역과 PDF 편집은 Codex가 수행합니다. 아래는 그 과정에서 쓰는 문서 관리 명령입니다. 예시 문서 ID는 `example-rules`입니다.

```sh
# 문서를 등록하고 원문 텍스트와 위치 확인
scripts/run.sh register --pdf "inbox/Example Rules.pdf" --id example-rules --kind boardgame
scripts/run.sh extract example-rules

# 검토 파일을 저장한 뒤 표 구조와 문서 상태 확인
scripts/run.sh validate example-rules
scripts/run.sh status example-rules

# PDF 생성 요청 후 편집 버전 준비
scripts/run.sh prepare-edit example-rules

# PdfCraft로 편집본을 저장한 뒤 결과 폴더에 복사 (첫 버전 예시)
scripts/run.sh publish example-rules --version v001 \
  --pdf documents/example-rules/work/edit-v001/candidate.pdf
```

- `register`는 새 원본을 문서의 `source/`로 옮깁니다. 내용이 같은 PDF가 이미 등록되어 있으면 기존 문서를 사용합니다. 문서 종류(`--kind`)는 `boardgame`, `"research paper"`, `other` 중에서 선택합니다.
- `extract`는 추출 결과를 표준 출력으로 보여 줍니다. 텍스트가 없는 스캔 페이지는 번역할 때 OCR과 원본 대조가 필요합니다.
- `prepare-edit`는 원본과 검토 파일의 해시를 기록합니다. 진행 중인 버전은 `--version v001`처럼 지정해 재개합니다.
- 전체 문서 상태는 `scripts/run.sh status`로 확인합니다. 다른 프로젝트 폴더를 사용하려면 `scripts/run.sh --root /path/to/project status`처럼 명령 이름 앞에 `--root`를 넣습니다.

에이전트의 작업 절차와 파일 보존 규칙은 [AGENTS.md](AGENTS.md)에 있습니다. 구현을 변경한 뒤에는 `scripts/test.sh`로 테스트를 실행할 수 있습니다.
