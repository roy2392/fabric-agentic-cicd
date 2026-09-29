from pathlib import Path
import json,subprocess,sys
import pytest
from scripts.assignment_runtime import Assignment

def runtime(tmp_path,role='developer'):
 a=Assignment.__new__(Assignment);a.role=role;a.clone=tmp_path/'solution';a.clone.mkdir();a.task={'files':['docs/assigned.md']};a.wiki_ready=lambda *args: {};return a

def test_assignment_only_accepts_allowed_writes(tmp_path):
 a=runtime(tmp_path);assert a.write_file('docs/assigned.md','hello')['bytes']==5
 for p in ('../escape','/tmp/escape','fabric/item.json','docs/other.md','docs\\assigned.md'):
  with pytest.raises(ValueError):a.write_file(p,'bad')

def test_reviewer_has_no_write_or_execution(tmp_path):
 a=runtime(tmp_path,'reviewer')
 with pytest.raises(ValueError):a.write_file('docs/assigned.md','bad')
 with pytest.raises(ValueError):a.run_checks()

def test_assigned_symlink_cannot_escape(tmp_path):
 a=runtime(tmp_path);outside=tmp_path/'outside';outside.mkdir();(a.clone/'docs').symlink_to(outside,target_is_directory=True)
 with pytest.raises(ValueError):a.write_file('docs/assigned.md','bad')

def test_assignment_text_limits(tmp_path):
 a=runtime(tmp_path)
 for value in ('a'*100001,'a\x00b'):
  with pytest.raises(ValueError):a.write_file('docs/assigned.md',value)


def test_publication_description_fits_ado_limit():
 from scripts.assignment_runtime import pr_description
 description=pr_description('s'*11999,'a'*40,'test output '*2000)
 assert len(description)<4000
 assert 'a'*40 in description
 assert 'Human merge remains required' in description
 assert 'no new Fabric execution' in description
