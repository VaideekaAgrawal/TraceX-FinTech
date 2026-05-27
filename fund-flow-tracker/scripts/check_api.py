import urllib.request

urls = ['http://127.0.0.1:8000/api/health', 'http://127.0.0.1:8000/api/metrics']
for u in urls:
    try:
        r = urllib.request.urlopen(u, timeout=5).read().decode('utf-8')
        print('\n---', u, '---')
        print(r[:4000])
    except Exception as e:
        print('\n---', u, 'FAILED ---')
        print(e)
