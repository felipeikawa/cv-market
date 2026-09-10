"""OCR tests use only a temporary app and synthetic SQLite database."""
import os
import shutil
import unittest
import test_production
import test_conference_mobile

FIXTURE = '''
import app as m
from models import db, Usuario
with m.app.app_context():
    db.create_all()
    user = Usuario(nome='Teste OCR', email='ocr@example.invalid', perfil='operador')
    user.definir_senha('test-only-password')
    db.session.add(user)
    db.session.commit()
c = m.app.test_client()
'''

class OCRTests(unittest.TestCase):
    setUp = test_production.ProductionTests.setUp
    run_code = test_conference_mobile.ConferenceMobileTests.run_code

    def test_route_and_contract(self):
        self.run_code(FIXTURE + '''
assert c.get('/ocr-teste').status_code == 302
assert '/login' in c.get('/ocr-teste').location
c.post('/login', data={'email':'ocr@example.invalid','senha':'test-only-password'})
r = c.get('/ocr-teste')
assert r.status_code == 200
html = r.get_data(as_text=True)
for text in ['Selecionar ou tirar foto', 'Ler texto', 'TEXTO IDENTIFICADO', 'image/*',
             'imagePreview', 'ocrPercent', 'rawText', 'não é salva no sistema']:
    assert text in html, text
assert '<form' not in html and 'capture=' not in html
rules = [r for r in m.app.url_map.iter_rules() if 'ocr' in r.rule]
assert len(rules) == 1 and rules[0].rule == '/ocr-teste'
assert rules[0].methods == {'GET','HEAD','OPTIONS'}
assert c.post('/ocr-teste', data=b'image-bytes').status_code == 405
''')
        source = (test_production.ROOT / 'static/js/ocr_teste.js').read_text()
        for forbidden in ['fetch(', 'XMLHttpRequest', 'FormData', 'sendBeacon', 'eval(', 'innerHTML', 'localStorage']:
            self.assertNotIn(forbidden, source)

    @unittest.skipUnless(os.environ.get('CV_BROWSER_TESTS'), 'Opt-in: requires Playwright browsers')
    def test_browser_interface_and_privacy(self):
        shutil.copytree(test_production.ROOT / 'static', self.cwd / 'static')
        env = dict(self.env, PYTHONPATH=os.environ.get('PYTHONPATH', ''),
                   PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH', ''))
        self.run_code(FIXTURE + r'''
import base64
import threading
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
server = make_server('127.0.0.1', 0, m.app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:' + str(server.server_port)
with sync_playwright() as p:
    for engine in [p.chromium, p.webkit]:
        browser = engine.launch()
        for width, height in [(390,844),(360,800),(768,1024),(1440,900)]:
            page = browser.new_page(viewport={'width':width,'height':height})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url+'/login')
            page.locator('[name=email]').fill('ocr@example.invalid')
            page.locator('[name=senha]').fill('test-only-password')
            page.locator('button[type=submit]').click()
            page.wait_for_url('**/dashboard')
            page.goto(url+'/ocr-teste')
            requests = []
            page.on('request', lambda r: requests.append((r.url, r.method, r.post_data)))
            # Stub the library boundary; exercise all application code without CDN/WASM.
            page.evaluate(r''' + "'''" + r'''
              window.calls = 0; window.terminated = 0;
              window.Tesseract = {createWorker: async (lang, mode, opts) => {
                if (lang !== 'por') throw Error('wrong language');
                return {recognize: async canvas => {
                  window.calls++; window.dimensions = [canvas.width, canvas.height];
                  opts.logger({status:'recognizing text',progress:0.5});
                  await new Promise(r => setTimeout(r, 250));
                  if (window.failOCR) throw Error('Falha de teste');
                  return {data:{text:'  LOTE L240815\nFAB 15/08/26\nVAL 15/12/26\n<script>alert(1)</script>\n'}};
                }, terminate: async () => {window.terminated++;}};
              }};
            ''' + "'''" + r''')
            data = page.evaluate("""() => {const c=document.createElement('canvas'); c.width=4000; c.height=2000; const x=c.getContext('2d'); x.fillStyle='white'; x.fillRect(0,0,4000,2000); return c.toDataURL('image/png').split(',')[1];}""")
            photo = {'name':'embalagem.png','mimeType':'image/png','buffer':base64.b64decode(data)}
            def no_overflow():
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (engine.name,width)
            no_overflow()
            assert page.locator('#chooseImage').bounding_box()['height'] >= 48
            page.locator('#ocrImage').set_input_files(photo)
            expect(page.locator('#readImage')).to_be_enabled()
            expect(page.locator('#imagePreview')).to_be_visible()
            no_overflow()
            page.locator('#readImage').click()
            expect(page.locator('#readImage')).to_be_disabled()
            expect(page.locator('#chooseImage')).to_be_disabled()
            expect(page.locator('#ocrPercent')).to_have_attribute('value','50')
            expect(page.locator('#ocrResult')).to_be_visible()
            assert page.locator('#rawText').input_value() == '  LOTE L240815\nFAB 15/08/26\nVAL 15/12/26\n<script>alert(1)</script>\n'
            assert page.evaluate('window.dimensions') == [2560,1280]
            assert page.evaluate('window.calls') == 1
            assert page.evaluate('window.terminated') == 1
            expect(page.locator('#readImage')).to_have_text('Ler novamente')
            expect(page.locator('#chooseImage')).to_have_text('Escolher outra imagem')
            no_overflow()
            page.screenshot(path='/private/tmp/cv-ocr-'+engine.name+'-'+str(width)+'.png',full_page=True)
            page.evaluate('window.failOCR = true')
            page.locator('#readImage').click()
            expect(page.locator('#ocrError')).to_be_visible()
            expect(page.locator('#readImage')).to_be_enabled()
            expect(page.locator('#ocrResult')).to_be_hidden()
            page.evaluate('window.failOCR = false')
            page.locator('#readImage').click()
            expect(page.locator('#ocrResult')).to_be_visible()
            for name, mime, content in [('bad.txt','text/plain',b'text'),('bad.png','image/png',b'not a picture'),('bad.svg','image/svg+xml',b'<svg/>'),('large.jpg','image/jpeg',b'x'*(20*1024*1024+1))]:
                page.locator('#ocrImage').set_input_files({'name':name,'mimeType':mime,'buffer':content})
                expect(page.locator('#ocrError')).to_be_visible()
                expect(page.locator('#chooseImage')).to_be_enabled()
                expect(page.locator('#readImage')).to_be_disabled()
            page.locator('#ocrImage').set_input_files(photo)
            expect(page.locator('#readImage')).to_be_enabled()
            # Simulate CDN unavailable and ensure a friendly, retryable failure.
            page.evaluate('delete window.Tesseract')
            page.route('https://cdn.jsdelivr.net/**', lambda route: route.abort())
            page.locator('#readImage').click()
            expect(page.locator('#ocrError')).to_contain_text('Verifique sua conexão')
            expect(page.locator('#readImage')).to_be_enabled()
            assert all(method == 'GET' and body is None for _,method,body in requests), requests
            assert all(not request_url.startswith(url) for request_url,_,_ in requests), requests
            assert not errors, errors
            page.close()
        browser.close()
server.shutdown()
''', env)

if __name__ == '__main__':
    unittest.main()
