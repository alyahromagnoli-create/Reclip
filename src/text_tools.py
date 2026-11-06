import re
from urllib.parse import urlencode

def clean_text(text):
    text=text.replace('\r\n','\n').replace('\r','\n')
    text=re.sub('[\u200b\u200c\u200d\ufeff]','',text)
    text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',text)
    return re.sub(r'\n{3,}','\n\n','\n'.join(line.rstrip() for line in text.split('\n'))).strip()

def unique(items):
    seen=set();result=[]
    for item in items:
        if item.casefold() not in seen:seen.add(item.casefold());result.append(item)
    return result

def extract_urls(text):
    found=re.findall(r'(?i)(?:https?://|www\.)[^\s<>"\u3000，。；！、（）【】]+',text)
    result=[]
    for url in found:
        url=url.rstrip('.,;:!?，。；：！？”’\"]}')
        while url.endswith(')') and url.count(')')>url.count('('):url=url[:-1]
        if url.lower().startswith('www.'):url='https://'+url
        result.append(url)
    return unique(result)

def extract_emails(text):
    return unique(re.findall(r'(?<![\w.+-])[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+',text))

def translation_url(text):
    if len(text)>5000:raise ValueError('网页翻译每次最多 5000 字，请先在预览中缩短文字。')
    return 'https://www.bing.com/translator?'+urlencode({'from':'auto','to':'zh-Hans','text':text})
