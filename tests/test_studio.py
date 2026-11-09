import re

from conftest import KEY_B


def test_studio_shell_and_static_assets_are_packaged(setup):
    client, _, _ = setup
    client.headers.clear()
    response = client.get('/')
    assert response.status_code == 200
    assert '声间' in response.text
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert 'no-store' in response.headers['cache-control']
    assets = re.findall(r'(?:src|href)="(/studio/assets/[^"]+)"', response.text)
    assert len(assets) >= 2
    for asset in assets:
        assert client.get(asset).status_code == 200
    assert client.get('/studio/../catalog.sqlite3').status_code == 404
    for path in ('/v1/studio/config', '/v1/training/samples', '/v1/voice-training/jobs'):
        assert client.get(path).status_code == 401


def test_studio_samples_and_jobs_are_owner_scoped(setup, voice):
    client, app, _ = setup
    sample = client.get('/v1/training/samples').json()['samples'][0]
    response = client.get(f"/v1/training/samples/{sample['id']}/audio")
    assert response.status_code == 200
    assert response.content.startswith(b'RIFF')
    assert response.headers['cache-control'] == 'no-store'
    job = app.state.store.create('job', 'alice', {'status':'queued'})
    assert client.get('/v1/voice-training/jobs').json()['jobs'][0]['id'] == job['id']
    assert client.get('/v1/studio/config').json()['training_enabled'] is True
    client.headers['Authorization'] = f'Bearer {KEY_B}'
    assert client.get('/v1/training/samples').json()['samples'] == []
    assert client.get('/v1/voice-training/jobs').json()['jobs'] == []
    assert client.get(f"/v1/training/samples/{sample['id']}/audio").status_code == 404
