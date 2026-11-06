from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import pytest
from history import History
from text_tools import clean_text,extract_urls,extract_emails,translation_url
from windows_api import parse_hotkey

def test_history_cap_dedup_and_restart(tmp_path):
    path=tmp_path/'history.db';h=History(path)
    for i in range(55):h.add_text(f'text-{i}')
    assert len(h.items())==50
    assert h.items()[0]['text']=='text-54'
    assert not any(r['text']=='text-0' for r in h.items())
    last=h.add_text('text-10')
    assert len(h.items())==50 and h.items()[0]['id']==last
    assert h.items()[0]['copies']==2
    h.close();h=History(path);assert h.items()[0]['text']=='text-10'
    h.close()

def test_image_storage_delete_clear_and_settings(tmp_path):
    h=History(tmp_path/'history.db');n=h.add_image(b'png-test',20,30)
    assert h.get(n)['image']==b'png-test'
    h.setting('hotkey','Ctrl+Alt+V');assert h.setting('hotkey')=='Ctrl+Alt+V'
    h.delete(n);assert not h.items()
    h.add_text('one');h.add_text('two');h.clear();assert not h.items()
    h.close()

def test_search_filter_and_empty_limits(tmp_path):
    h=History(tmp_path/'db')
    assert h.add_text('') is None
    h.add_text('Hello 世界');h.add_image(b'pic',1,1)
    assert len(h.items('世界'))==1
    assert len(h.items(kind='image'))==1
    with pytest.raises(ValueError):h.add_text('x'*(1024*1024+1))
    with pytest.raises(ValueError):h.add_image(b'x'*(20*1024*1024+1),1,1)
    h.close()

def test_text_tools():
    assert clean_text('\ufeffa\u200bb  \r\n\r\n\r\nc\x00')=='ab\n\nc'
    s='https://example.com/a?x=1，https://example.com/a?x=1 www.example.org/test。 A+B@Example.com；foo@example.cn'
    assert extract_urls(s)==['https://example.com/a?x=1','https://www.example.org/test']
    assert extract_emails(s)==['A+B@Example.com','foo@example.cn']
    assert '%26' in translation_url('A&B')
    assert 'bing.com/translator' in translation_url('hello')

@pytest.mark.parametrize('combo,mod,key', [('Alt+V',1,86),('Ctrl+Alt+V',3,86),('Ctrl+Shift+F8',6,119),('Win+V',8,86)])
def test_hotkey_parse(combo,mod,key):assert parse_hotkey(combo)==(mod,key)

@pytest.mark.parametrize('combo',['V','Ctrl+Alt','Ctrl+V+X','Alt+Space','Ctrl+Ctrl+V','Ctrl+Q'])
def test_invalid_hotkey(combo):
    with pytest.raises(ValueError):parse_hotkey(combo)
