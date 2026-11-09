"""Local browser-test fixture. All audio/voices are synthetic, never production data."""
import asyncio
import os
import tempfile
from pathlib import Path

import numpy as np
import uvicorn

from conftest import FakeServices
from tts_host.app import create_app
from tts_host.audio import wav_bytes
from tts_host.config import Settings

KEY = 'studio-test-only-key-not-for-production'


class BrowserTTS:
    async def stream(self, texts, voice):
        async for _ in texts:
            for i in range(4):
                await asyncio.sleep(.08)
                yield 24000, (np.sin(np.arange(6000) * .04) * 1800).astype('<i2').tobytes()


class BrowserServices(FakeServices):
    def __init__(self):
        super().__init__()
        self.tts = BrowserTTS()

    def capabilities(self):
        return {name: {'enabled': True, 'backend': 'browser-test-double'} for name in ('asr','tts','translation')}


def create_fixture(root):
    app = create_app(Settings(data_dir=root, api_keys={'browser-test':KEY}, training={'enabled':True}), BrowserServices())
    store = app.state.store
    sample_ids = []
    for i in range(5):
        sample = store.create('sample','browser-test',{'transcript':f'这是第 {i+1} 段测试录音，用来验证素材和训练操作。','duration':4.0})
        store.asset(sample['id']).parent.mkdir(parents=True,exist_ok=True)
        store.asset(sample['id']).write_bytes(wav_bytes(np.sin(np.arange(64000) * (.04 + i*.01)).astype(np.float32)*.1,16000))
        sample_ids.append(sample['id'])
    voices = []
    for i,name in enumerate(('示例 · 日常人声','示例 · 轻声讲述')):
        voices.append(store.create('voice','browser-test',{'name':name,'sample_id':sample_ids[i],'transcript':'这是测试录音。','kind':'zero_shot','version':1,'base_revision':'test-fixture'}))
    fine = store.create('voice','browser-test',{**{k:v for k,v in voices[0].items() if k not in ('id','created_at')},'kind':'finetuned','version':2})
    store.create('job','browser-test',{'voice_id':voices[0]['id'],'sample_ids':sample_ids,'epochs':1,'learning_rate':1e-5,'status':'succeeded','stage':'complete','output_voice_id':fine['id']})
    return app


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='studio-browser-') as directory:
        uvicorn.run(create_fixture(Path(directory)),host='127.0.0.1',port=int(os.environ.get('STUDIO_TEST_PORT','8765')))
