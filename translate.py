"""MyMemory GET API. Only the explicitly collected text is sent."""
import html
import json
import socket
import ssl
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

class TranslationError(Exception): pass

def chunks(text, limit=450):
    """Keep requests below the provider's 500 UTF-8 byte limit."""
    result=[]
    while text:
        size=0; end=0
        for char in text:
            n=len(char.encode('utf-8'))
            if size+n>limit: break
            size+=n; end+=1
        if end<len(text):
            boundary=max(text.rfind(' ',0,end),text.rfind('\n',0,end))
            if boundary>end//2: end=boundary+1
        result.append(text[:end].strip())
        text=text[end:]
    return [part for part in result if part]

def https_open(request, timeout):
    context=ssl.create_default_context()
    # Python.org's macOS build may lack its optional certificate installation.
    # Add Apple's bundled trust roots while keeping verification enabled.
    if Path('/etc/ssl/cert.pem').exists():
        context.load_verify_locations(cafile='/etc/ssl/cert.pem')
    return urllib.request.urlopen(request, timeout=timeout, context=context)

def translate(text, opener=https_open):
    output=[]
    for part in chunks(text):
        query=urllib.parse.urlencode(dict(q=part,langpair='en|zh-CN',mt=1))
        request=urllib.request.Request('https://api.mymemory.translated.net/get?'+query,
            headers={'User-Agent':'EnglishCards/2.0','Accept':'application/json'})
        try:
            with opener(request, timeout=20) as response:
                data=json.loads(response.read(1024*1024).decode('utf-8'))
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
            raise TranslationError('暂时无法连接翻译服务，英文已保留。联网后选中词条，点击“重试翻译”。')
        except (ValueError,UnicodeError):
            raise TranslationError('翻译服务返回了无法读取的内容，请稍后重试。')
        if not isinstance(data,dict): raise TranslationError('翻译服务响应异常，请稍后重试。')
        details=str(data.get('responseDetails','')).upper()
        if data.get('quotaFinished') or str(data.get('responseStatus'))=='429' or 'LIMIT' in details:
            raise TranslationError('翻译服务的免费额度暂时用完，英文已保留。请明天重试。')
        response_data=data.get('responseData')
        if str(data.get('responseStatus'))!='200' or not isinstance(response_data,dict):
            raise TranslationError('翻译服务暂时不可用，英文已保留，请稍后重试。')
        value=response_data.get('translatedText','')
        if not isinstance(value,str) or not value.strip():
            raise TranslationError('没有获得中文释义，英文已保留，请稍后重试。')
        value=html.unescape(value).strip()
        if value.casefold()==part.casefold() or not any('\u3400'<=c<='\u9fff' for c in value):
            raise TranslationError('未获得可用的中文释义。专有名词可双击词条手动补充。')
        output.append(value)
    return '\n'.join(output)
