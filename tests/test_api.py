from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_healthz():
    assert client.get('/healthz').json() == {'status': 'ok'}


def test_query_returns_citations():
    r = client.post('/v1/query', json={'question': 'How should production remediation work?'})
    assert r.status_code == 200
    body = r.json()
    assert body['evidence']
    assert 'policy-authorized' in body['answer']


def test_empty_question_rejected():
    r = client.post('/v1/query', json={'question': '   '})
    assert r.status_code == 400
