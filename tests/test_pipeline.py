"""Temporary fixtures only: Markdown handoff, input preservation and publishing."""
import html
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from reportlab.pdfgen import canvas

SPEC = importlib.util.spec_from_file_location('pipeline', Path(__file__).resolve().parents[1] / 'scripts/pipeline.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


def make_pdf(path, text='Take one turn.', rotation=0, pages=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    pdf.setPageRotation(rotation)
    for _ in range(pages):
        if text:
            pdf.drawString(72, 700, text)
        pdf.showPage()
    pdf.save()


def table(headers, rows):
    def cell(value):
        return html.escape(str(value), quote=False).replace('\\', '\\\\').replace('|', '\\|').replace('\n', '<br>')
    return '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(['---'] * len(headers)) + ' |\n' + ''.join(
        '| ' + ' | '.join(map(cell, row)) + ' |\n' for row in rows)


class MarkdownWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pdf-md-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / 'inbox/rules.pdf'
        make_pdf(source)
        p.register(self.root, source, 'rules', 'boardgame')
        self.doc = self.root / 'documents/rules'
        self.trans = self.doc / 'review/trans.md'
        self.glossary = self.doc / 'review/glossary.md'
        self.rows = [['p001-s001', 1, 'Take one turn.', '한 차례를 진행합니다.'],
                     ['p001-s002', 1, 'Draw two cards.', '카드 두 장을 뽑습니다.']]
        self.write_review()

    def write_review(self):
        self.trans.write_text(table(p.TRANSLATION_HEADERS, self.rows), encoding='utf-8')
        self.glossary.write_text(table(p.GLOSSARY_HEADERS, [['t001', 'turn', '차례']]), encoding='utf-8')

    def candidate(self):
        job = p.prepare_edit(self.root, 'rules')
        candidate = Path(job['candidate_pdf'])
        make_pdf(candidate, text='Edited candidate.')
        return job, candidate

    def test_direct_md_edit_handoff_and_byte_exact_publish(self):
        self.rows[0][3] = '사람이 저장한 번역'
        self.write_review()
        before = {file.name: file.read_bytes() for file in (self.trans, self.glossary)}
        job, candidate = self.candidate()
        self.assertEqual(job['version'], 'v001')
        self.assertEqual(job['trans_md'], str(self.trans))
        self.assertEqual(p.review_content(self.root, 'rules')['segments'][0]['final_ko'], '사람이 저장한 번역')
        self.assertEqual(p.prepare_edit(self.root, 'rules', 'v001'), job)
        published = p.publish(self.root, 'rules', 'v001', candidate)
        output = Path(published['path'])
        self.assertEqual(output, self.doc / 'output/rules-ko-v001.pdf')
        self.assertEqual(job['output_pdf'], str(output))
        self.assertEqual(output.read_bytes(), candidate.read_bytes())
        receipt = json.loads((candidate.parent / 'receipt.json').read_text())
        self.assertNotIn('visual_qa_confirmed', receipt)
        for file in (self.trans, self.glossary):
            self.assertEqual(file.read_bytes(), before[file.name])
        self.assertFalse((self.doc / 'approved').exists())
        self.assertEqual(sorted(f.name for f in (self.doc / 'work/edit-v001').iterdir()),
                         ['candidate.pdf', 'edit-job.json', 'receipt.json'])
        self.assertEqual(list(output.parent.iterdir()), [output])
        with self.assertRaises(p.WorkflowError):
            p.prepare_edit(self.root, 'rules', 'v001')
        old = output.read_bytes()
        make_pdf(candidate, 'Replacement')
        with self.assertRaises(p.WorkflowError):
            p.publish(self.root, 'rules', 'v001', candidate)
        self.assertEqual(output.read_bytes(), old)

    def test_flat_output_versions_preserve_previous_files_and_status(self):
        first, candidate = self.candidate()
        output = Path(p.publish(self.root, 'rules', first['version'], candidate)['path'])
        original = output.read_bytes()
        second, candidate = self.candidate()
        self.assertEqual(second['version'], 'v002')
        p.publish(self.root, 'rules', second['version'], candidate)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(sorted(f.name for f in output.parent.iterdir()),
                         ['rules-ko-v001.pdf', 'rules-ko-v002.pdf'])
        # Flat PDFs must reserve their versions even if working files are moved away.
        shutil.rmtree(self.doc / 'work/edit-v001')
        shutil.rmtree(self.doc / 'work/edit-v002')
        make_pdf(self.doc / 'output/v003/legacy.pdf')
        self.assertEqual(p.status(self.root, 'rules')['documents'][0]['output_versions'],
                         ['v001', 'v002', 'v003'])
        self.assertEqual(p.prepare_edit(self.root, 'rules')['version'], 'v004')

    def test_failed_publish_leaves_no_flat_output_or_receipt(self):
        job, candidate = self.candidate()
        original_link = p.os.link

        def fail_pdf_link(source, target):
            if Path(target) == Path(job['output_pdf']):
                raise OSError('simulated publication failure')
            return original_link(source, target)

        with patch.object(p.os, 'link', side_effect=fail_pdf_link):
            with self.assertRaises(OSError):
                p.publish(self.root, 'rules', job['version'], candidate)
        self.assertEqual(list((self.doc / 'output').iterdir()), [])
        self.assertFalse((candidate.parent / 'receipt.json').exists())
        # The same prepared input can be retried after the failed write.
        p.publish(self.root, 'rules', job['version'], candidate)

    def test_markdown_escaping_and_reordered_ids(self):
        source = 'A | B \\ path\n<literal> & <br>'
        translation = '가 | 나 \\ 경로\n<문자> & <br>'
        self.rows[0][2:] = [source, translation]
        self.rows.reverse()
        self.write_review()
        segments = p.review_content(self.root, 'rules')['segments']
        self.assertEqual(segments[0]['id'], 'p001-s001')
        self.assertEqual(segments[0]['source_text'], source)
        self.assertEqual(segments[0]['final_ko'], translation)

    def test_invalid_tables_block_edit_without_creating_job(self):
        valid = self.trans.read_text()
        invalid = [valid.replace('p001-s002', 'p001-s001'), valid.replace('p001-s001', ''),
                   valid.replace('한 차례를 진행합니다.', ' '), valid.replace('| 1 |', '| 2 |'),
                   valid.replace('| 1 |', '| one |'), valid.replace('영어 원문', '다른 제목'),
                   valid.replace('Take one turn.', 'Take | one turn.'),
                   '| 문단id | pdf페이지 | 영어 원문 | 한국어 번역 |\n| --- | --- | --- | --- |\n']
        for content in invalid:
            with self.subTest(content=content):
                self.trans.write_text(content)
                with self.assertRaises(p.WorkflowError):
                    p.prepare_edit(self.root, 'rules')
                self.assertEqual(list((self.doc / 'work').iterdir()), [])

    def test_missing_or_invalid_glossary_blocks_edit(self):
        valid = self.glossary.read_text()
        for content in (valid.replace('차례', ''), valid + valid.splitlines()[-1] + '\n'):
            self.glossary.write_text(content)
            with self.assertRaises(p.WorkflowError):
                p.prepare_edit(self.root, 'rules')
        self.glossary.unlink()
        with self.assertRaises(p.WorkflowError):
            p.prepare_edit(self.root, 'rules')

    def test_changed_md_blocks_resume_and_publish_then_new_job_uses_saved_md(self):
        job, candidate = self.candidate()
        old_job = Path(job['path']).read_bytes()
        for file in (self.trans, self.glossary):
            original = file.read_text()
            file.write_text(original.replace('차례', '턴'))
            with self.assertRaises(p.WorkflowError):
                p.prepare_edit(self.root, 'rules', 'v001')
            with self.assertRaises(p.WorkflowError):
                p.publish(self.root, 'rules', 'v001', candidate)
            file.write_text(original)
        self.trans.write_text(self.trans.read_text().replace('차례', '턴'))
        second = p.prepare_edit(self.root, 'rules')
        self.assertEqual(second['version'], 'v002')
        self.assertEqual(second['review_sha256']['trans.md'], p.sha256(self.trans))
        self.assertEqual(Path(job['path']).read_bytes(), old_job)

    def test_preserves_legacy_files_and_skips_existing_versions(self):
        legacy = self.doc / 'approved/v001/approved_translation.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"legacy": true}')
        workbook = self.doc / 'review/translation-review.xlsx'
        workbook.write_bytes(b'legacy workbook')
        result = self.doc / 'output/v002/result.pdf'
        make_pdf(result)
        before = {f: f.read_bytes() for f in (legacy, workbook, result)}
        job = p.prepare_edit(self.root, 'rules')
        self.assertEqual(job['version'], 'v003')
        for f, data in before.items():
            self.assertEqual(f.read_bytes(), data)

    def test_source_changes_block_validation_and_publishing(self):
        _, candidate = self.candidate()
        source = next((self.doc / 'source').glob('*.pdf'))
        with source.open('ab') as stream:
            stream.write(b'\n% changed\n')
        for operation in (lambda: p.review_content(self.root, 'rules'),
                          lambda: p.publish(self.root, 'rules', 'v001', candidate)):
            with self.assertRaises(p.WorkflowError):
                operation()

    def test_publish_rejects_wrong_candidate_source_copy_and_page_count(self):
        job, candidate = self.candidate()
        source = next((self.doc / 'source').glob('*.pdf'))
        other = self.root / 'other.pdf'
        make_pdf(other)
        with self.assertRaises(p.WorkflowError):
            p.publish(self.root, 'rules', job['version'], other)
        shutil.copyfile(source, candidate)
        with self.assertRaises(p.WorkflowError):
            p.publish(self.root, 'rules', job['version'], candidate)
        make_pdf(candidate, 'Edited', pages=2)
        with self.assertRaises(p.WorkflowError):
            p.publish(self.root, 'rules', job['version'], candidate)

    def test_changed_editor_policy_is_rejected(self):
        job, candidate = self.candidate()
        file = Path(job['path'])
        original = json.loads(file.read_text())
        for change in ({'pdf_editor': 'Other editor'}, {'fallback_allowed': True}, {'document_id': 'other'}):
            file.write_text(json.dumps(original | change))
            with self.assertRaises(p.WorkflowError):
                p.publish(self.root, 'rules', job['version'], candidate)

    def test_registration_duplicates_are_reused_and_extract_writes_no_files(self):
        source = next((self.doc / 'source').glob('*.pdf'))
        duplicate = self.root / 'inbox/duplicate.pdf'
        shutil.copyfile(source, duplicate)
        reused = p.register(self.root, duplicate, 'another')
        self.assertEqual(reused['document_id'], 'rules')
        self.assertTrue(duplicate.exists())
        extracted = p.extract(self.root, 'rules')
        self.assertEqual(extracted['pages'][0]['text'], 'Take one turn.')
        self.assertTrue(extracted['pages'][0]['words'])
        self.assertEqual(list((self.doc / 'work').iterdir()), [])

    def test_scanned_pdf_needs_ocr_and_rotated_coordinates_match_metadata(self):
        for doc_id, text, rotation in [('scan', '', 0), ('rotated', 'Text', 90)]:
            source = self.root / 'inbox' / f'{doc_id}.pdf'
            make_pdf(source, text, rotation=rotation)
            p.register(self.root, source, doc_id)
        with self.assertRaises(p.WorkflowError):
            p.extract(self.root, 'scan')
        _, meta, _ = p.document(self.root, 'rotated')
        page = p.extract(self.root, 'rotated')['pages'][0]
        self.assertEqual((page['width'], page['height']),
                         (meta['source']['pages'][0]['width'], meta['source']['pages'][0]['height']))


if __name__ == '__main__':
    unittest.main()
