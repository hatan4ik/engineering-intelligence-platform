import pytest
from fastapi.testclient import TestClient
from app.application import create_app
from app.settings import ApplicationSettings


@pytest.fixture
def client():
    """Exercise the same lifespan-bound settings path as an ASGI process."""

    with TestClient(create_app(ApplicationSettings.from_mapping({}))) as test_client:
        yield test_client


def test_healthz(client):
    body = client.get('/healthz').json()
    assert body['status'] == 'ok'
    assert set(body['capabilities']) == {
        'query', 'pr_guardian_webhook', 'feedback_recorder', 'portal', 'operations',
    }


def test_query_returns_citations(client):
    r = client.post('/v1/query', json={'question': 'How should production remediation work?'})
    assert r.status_code == 200
    body = r.json()
    assert body['evidence']
    assert 'policy-authorized' in body['answer']


def test_query_refuses_when_no_authorized_evidence(client):
    r = client.post(
        '/v1/query',
        headers={'x-eip-groups': 'engineering'},
        json={'question': 'Which FinOps cost controls apply?'},
    )
    assert r.status_code == 200
    assert r.json()['model'] == 'none'
    assert r.json()['evidence'] == []
    assert r.json()['answer'] == 'I do not have enough authorized evidence to answer.'


def test_query_filters_deterministic_evidence_by_group_and_repository(client):
    r = client.post(
        '/v1/query',
        headers={'x-eip-groups': 'finance'},
        json={'question': 'Which FinOps cost controls apply?', 'repo': 'finance-planning'},
    )
    assert r.status_code == 200
    body = r.json()
    assert body['model'] == 'deterministic-demo'
    assert [item['source'] for item in body['evidence']] == ['finops/cfo-roi-model.md']
    assert 'FinOps controls' in body['answer']

    denied = client.post(
        '/v1/query',
        headers={'x-eip-groups': 'engineering'},
        json={'question': 'How should production remediation work?', 'repo': 'unrelated-repository'},
    )
    assert denied.status_code == 200
    assert denied.json()['model'] == 'none'
    assert denied.json()['evidence'] == []


def test_empty_question_rejected(client):
    r = client.post('/v1/query', json={'question': '   '})
    assert r.status_code == 400
