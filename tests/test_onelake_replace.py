import pytest
from scripts.onelake_files import OneLake

def test_metadata_replace_rejects_foreign_revision(monkeypatch):
    lake=OneLake('unused','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002')
    calls=[]
    def request(method,*args,**kwargs):
        calls.append(method)
        return b'foreign',{'ETag':'v2'}
    monkeypatch.setattr(lake,'request',request)
    with pytest.raises(RuntimeError,match='outside the recorded revision'):
        lake.replace('metadata.json',b'old',b'new')
    assert calls==['GET']

def test_metadata_replace_uses_compare_and_swap(monkeypatch):
    lake=OneLake('unused','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002')
    calls=[]
    def request(method,path,query='',body=None,extra=None,return_headers=False):
        calls.append((method,extra))
        return (b'old',{'ETag':'v1'}) if return_headers else b'new'
    monkeypatch.setattr(lake,'request',request)
    lake.replace('metadata.json',b'old',b'new')
    assert calls[1]==('PUT',{'If-Match':'v1'})
