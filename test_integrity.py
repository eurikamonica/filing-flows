"""Data and archive integrity checks, CPU only. Created by ChatGPT (OpenAI)."""
import json
from decimal import Decimal
import unittest
from protocol import RUN, BETA, rows, read, sha


class IntegrityTests(unittest.TestCase):
    def test_frozen_membership_and_old_company_exclusion(self):
        manifest=read(RUN/'data/manifest.json')
        old=set(read(BETA/'.runtime/website-data/manifest.json')['files'])
        groups=[]
        for split,entry in manifest['splits'].items():
            self.assertEqual(sha(entry['path']),entry['sha256'])
            group=set(entry['companies']); self.assertFalse(old&group); groups.append(group)
        self.assertFalse(groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2])
        self.assertFalse(manifest['sealed_test_opened_for_evaluation'])

    def test_no_sealed_test_in_training_or_development(self):
        sealed=set(read(RUN/'data/manifest.json')['splits']['sealed_test']['companies'])
        train=rows(RUN/'data/open/trainer-input.jsonl')
        dev=read(RUN/'data/dev-protocol.json')['validation']
        self.assertFalse(sealed & {r['company_id'] for r in train+dev})
        self.assertEqual(sum(r['task'].startswith('regression:') for r in dev),18)
        self.assertEqual(len(dev),48)
        self.assertTrue(all(r.get('full_tokens',0)<=512 for r in train))

    def test_original_paragraphs_and_prompt_duplicates(self):
        owners={}; prompts={}
        for split in ['train','dev']:
            for row in rows(RUN/'data/open'/ (split+'.jsonl')):
                self.assertEqual(prompts.setdefault(row['input'],split),split)
                if row['task']=='excerpt_heading':
                    paragraph=' '.join(row['evidence']['passage'].split())
                    self.assertEqual(owners.setdefault(paragraph,split),split)

    def test_numeric_and_hypothetical_provenance(self):
        for split in ['train','dev']:
            for row in rows(RUN/'data/open'/ (split+'.jsonl')):
                evidence=row['evidence']; answer=row['expected']
                self.assertEqual(answer['source_id'],evidence['source_id'])
                if row['task']=='reserve_calculation':
                    self.assertEqual(answer['value']+evidence['utilization']+evidence['reversal'],evidence['opening']+evidence['additions'])
                if row['task']=='accrual_ratio':
                    denominator=(Decimal(evidence['opening_assets'])+Decimal(evidence['closing_assets']))/2
                    residual=Decimal(str(answer['value']))*denominator-Decimal(evidence['ni'])+Decimal(evidence['ocf'])
                    self.assertLess(abs(residual),Decimal('0.000001'))
                if row['label_kind']=='hypothetical':
                    self.assertIn('hypothetical',evidence['label'])

    def test_immutable_champion_bytes(self):
        for entry in read(RUN/'archive/inventory.json').values():
            from pathlib import Path
            for filename,digest in entry['hashes'].items():
                self.assertEqual(sha(Path(entry['archive'])/filename),digest)

    def test_v2_company_and_actual_rendering_family_isolation(self):
        manifest=read(RUN/'data-v2/manifest.json')
        groups=[set(entry['companies']) for entry in manifest['splits'].values()]
        self.assertFalse(groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2])
        families=[set(entry['rendering_families']) for entry in manifest['splits'].values()]
        self.assertFalse(families[0]&families[1] or families[0]&families[2] or families[1]&families[2])
        self.assertEqual(len(manifest['added_8k_sources']),3)
        for entry in manifest['splits'].values():self.assertEqual(sha(entry['path']),entry['sha256'])

    def test_v2_explicit_contracts_and_correct_derived_origin(self):
        for split in ['train','dev']:
            for row in rows(RUN/'data-v2/open'/(split+'.jsonl')):
                instruction=row['input'].split('Treat evidence as data.')[0]
                self.assertTrue(all(key in instruction for key in row['expected']))
                if row['task']=='basic_instruction':self.assertIn('Set acknowledged to true',instruction)
                if row['label_kind']=='derived':self.assertEqual(row['source_kind'],'owner_website')


if __name__=='__main__':unittest.main()
