import json
import pytest
from scripts import reviewer_runtime as runtime
from scripts.agent_auth import token_for

def test_reviewer_cannot_request_fabric_token():
    with pytest.raises(ValueError,match='outside role scope'):
        token_for('reviewer','https://api.fabric.microsoft.com')

def test_reviewer_rejects_new_pr_revision_before_voting(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'HOME',tmp_path)
    (tmp_path/'review-state.json').write_text(json.dumps({'pr_id':1,'source_commit':'old','iteration':1}))
    monkeypatch.setattr(runtime,'manifest',lambda:{'repository_id':'demo'})
    class Client:
        def get(self,path):
            if '/iterations?' in path:return {'value':[{'id':2}]}
            return {'status':'active','lastMergeSourceCommit':{'commitId':'new'}}
        def request(self,*args,**kwargs):pytest.fail('Stale review must not post or vote')
    monkeypatch.setattr(runtime,'ado',lambda:Client())
    with pytest.raises(RuntimeError,match='PR changed'):
        runtime.submit_review('old','approve','Reviewed evidence and found no issue with the exact original revision.')

def test_reviewer_rejects_changed_wiki_before_voting(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'HOME',tmp_path)
    (tmp_path/'review-state.json').write_text(json.dumps({'pr_id':1,'source_commit':'same','iteration':1,'wiki_commit':'reviewed-wiki'}))
    monkeypatch.setattr(runtime,'manifest',lambda:{'repository_id':'demo','wiki_id':'wiki'})
    class Client:
        def get(self,path):
            if '/iterations?' in path:return {'value':[{'id':1}]}
            if '/refs?' in path:return {'value':[{'name':'refs/heads/wikiMaster','objectId':'changed-wiki'}]}
            return {'status':'active','lastMergeSourceCommit':{'commitId':'same'}}
        def request(self,*args,**kwargs):pytest.fail('Changed documentation must invalidate the vote')
    monkeypatch.setattr(runtime,'ado',lambda:Client())
    with pytest.raises(RuntimeError,match='Wiki changed'):
        runtime.submit_review('same','approve','Reviewed the pinned code and its documentation with successful execution evidence.')

def test_vote_preserves_required_reviewer_gate(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'HOME',tmp_path)
    (tmp_path/'review-state.json').write_text(json.dumps({'pr_id':1,'source_commit':'same','iteration':1,'wiki_commit':'wiki-head'}))
    monkeypatch.setattr(runtime,'manifest',lambda:{'repository_id':'demo','wiki_id':'wiki','agents':{'reviewer':{'ado_id':'reviewer'}}})
    class Client:
        required=True
        def get(self,path):
            if '/iterations?' in path:return {'value':[{'id':1}]}
            if '/refs?' in path:return {'value':[{'name':'refs/heads/wikiMaster','objectId':'wiki-head'}]}
            if '/threads?' in path:return {'value':[]}
            return {'status':'active','lastMergeSourceCommit':{'commitId':'same'}}
        def request(self,method,path,body):
            if method=='POST':return 200,{}, {'id':2}
            if method=='PUT':
                # Azure DevOps replaces the omitted flag with optional on a vote PUT.
                self.required=body.get('isRequired',False)
                return 200,{}, {'vote':body['vote'],'isRequired':self.required}
            pytest.fail('Unexpected review mutation')
    client=Client();monkeypatch.setattr(runtime,'ado',lambda:client)
    result=runtime.submit_review('same','approve','Verified the pinned code, corrected wiki, real runtime evidence and mandatory human merge gate.')
    assert result['vote']==10 and client.required
