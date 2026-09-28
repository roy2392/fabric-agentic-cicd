from pathlib import Path
import json,subprocess,sys
import pytest
from scripts.assignment_runtime import Assignment

def runtime(tmp_path,role='developer'):
 a=Assignment.__new__(Assignment);a.role=role;a.clone=tmp_path/'solution';a.clone.mkdir();a.task={'files':['docs/assigned.md']};return a

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
