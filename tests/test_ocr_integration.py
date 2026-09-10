"""Synthetic DB and browser tests; OCR worker is stubbed at its external boundary."""
import os
import shutil
import unittest
import test_production
import test_conference_mobile
FIXTURE = test_conference_mobile.FIXTURE

class OCRIntegrationTests(unittest.TestCase):
    setUp = test_production.ProductionTests.setUp
    run_code = test_conference_mobile.ConferenceMobileTests.run_code

    def test_privacy_contract(self):
        for name in ['ocr_engine.js','ocr_parser.js','ocr_conferencia.js','ocr_teste.js']:
            source = (test_production.ROOT / 'static/js' / name).read_text()
            for forbidden in ['fetch(', 'XMLHttpRequest', 'FormData', 'sendBeacon', 'localStorage', 'indexedDB', 'innerHTML']:
                self.assertNotIn(forbidden, source)
        self.run_code(FIXTURE + """
html = c.get('/conferencias/1').get_data(as_text=True)
assert 'data-ocr-item="1"' in html and 'id="ocrDialog"' in html
assert 'capture=' not in html
assert 'name="conferenceOCRImage"' not in html
""")

    @unittest.skipUnless(os.environ.get('CV_BROWSER_TESTS'), 'Requires Playwright')
    def test_parser_and_confirmation(self):
        shutil.copytree(test_production.ROOT / 'static', self.cwd / 'static')
        env = dict(self.env, PYTHONPATH=os.environ.get('PYTHONPATH',''), PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH',''))
        self.run_code(FIXTURE + r'''
import threading, base64
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
server=make_server('127.0.0.1',0,m.app,threaded=True)
threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://127.0.0.1:'+str(server.server_port)
with sync_playwright() as p:
 for engine in [p.chromium,p.webkit]:
  browser=engine.launch()
  for width,height in [(390,844),(360,800),(768,1024),(1440,900)]:
   page=browser.new_page(viewport={'width':width,'height':height})
   page.goto(url+'/login')
   page.locator('[name=email]').fill('mobile@example.invalid')
   page.locator('[name=senha]').fill('test-only-password')
   page.locator('button[type=submit]').click()
   page.goto(url+'/conferencias/1')
   def parse(text): return page.evaluate('(t)=>CVOCRParser.parse(t)',text)
   for text in ['VAL 15/12/2026','V: 15/12/26','VALIDO ATE\n15.12.2026','VÁL1DO ATÉ 15/12/26','VALlDADE 15/12/26']:
    assert parse(text)['expiry']=='2026-12-15',text
   real_text = "- OFFER AS\nV\nVaio até Válido hasta/Bost betora\n18.11.2013-M3 Uma dic\nL:307712215-18:14 | Para mants\n: Fr: o\n. v E"
   result = parse(real_text)
   assert result['lots']==['307712215'] and result['manufacture']=='' and result['expiry']=='2013-11-18',result
   assert [d['value'] for d in result['dates']]==['18/11/2013']
   for text,iso in [('18.11.2013-M3','2013-11-18'),('18/11/2026ABC','2026-11-18')]:
    result=parse(text)
    assert [d['iso'] for d in result['dates']]==[iso] and not result['expiry'] and not result['manufacture'],result
   for text in ['VAL:18.11.2013-M3','Vaio até\n18.11.2013-M3','Bost betora\n18.11.2013-M3','Válido hasta\n18.11.2013-M3','BEST BEFORE texto adicional\n18.11.2013-M3']:
    result=parse(text); assert result['expiry']=='2013-11-18' and not result['manufacture'],result
   for text in ['V:\n15.12.2026-X','V 15.12.2026-L2']:
    assert parse(text)['expiry']=='2026-12-15',text
   for text in ['FAB 10.09.2026-L1','FAB10/09/2026X']:
    result=parse(text); assert result['manufacture']=='2026-09-10' and not result['expiry'],result
   for text,lot in [('L:307712215-18:14','307712215'),('L:ABC123','ABC123'),('LOT XZ-2026-A','XZ-2026-A'),('LOTE A12345','A12345'),('L:XZ-2026-A-23:59','XZ-2026-A')]:
    assert parse(text)['lots']==[lot],text
   for text in ['18:14','VAL 18:14','31/02/2026ABC','VAL:31/02/2026-M3','118/11/2026','18/11/20260','18/11/2026/01','18/11/2026-01']:
    assert parse(text)['dates']==[],text
   for text in ['vaio qualquer\n18/11/2026','bost qualquer\n18/11/2026','BEST AFTER\n18/11/2026','BEST BEFORE\n\n18/11/2026','BEST BEFORE\ntexto intermediario\n18/11/2026']:
    assert not parse(text)['expiry'],text
   assert parse('BEST BEFORE\n18.11.2026')['expiry']=='2026-11-18'
   for text in ['FAB 10/09/26\nVAL 15/12/26','FAB\n10/09/2026\nVAL\n15/12/2026']:
    result=parse(text); assert result['manufacture']=='2026-09-10' and result['expiry']=='2026-12-15'
   for label in ['VALIDADE','VAL','VAL.','V:','V','VENC','VENC.','VENCIMENTO','VÁLIDO ATÉ','VALIDO ATE','BEST BEFORE','EXP','EXP.','EXPIRY','EXPIRATION']:
    assert parse(label+'\n15/12/26')['expiry']=='2026-12-15',label
   for label in ['FAB','FAB.','F:','FABR','FABRICAÇÃO','FABRICACAO','MFG','MANUFACTURED']:
    assert parse(label+'\n10/09/26')['manufacture']=='2026-09-10',label
   for label in ['L:','LOTE','LOT','L.','BATCH','L0TE']:
    assert parse(label+'\nABC123')['lots']==['ABC123'],label
   for text,count in [('10/09/2026 15/12/2026',2),('10/09/2026 15/12/2026 01/01/2027',3),('sem datas 12345678',0),('VAL 31/02/2026 00/12/26 31/04/26 29/02/2025',0)]:
    result=parse(text); assert len(result['dates'])==count and not result['expiry'] and not result['manufacture'],result
   assert parse('FAB 15/12/26 VAL 10/09/26')['reversed']
   assert parse('VAL 29-02-24')['expiry']=='2024-02-29'
   assert parse('VAL 01/01/70')['expiry']=='1970-01-01'
   assert parse('VAL 01/01/69')['expiry']=='2069-01-01'
   requests=[]; page.on('request',lambda r: requests.append((r.url,r.method)))
   page.evaluate("""() => {window.ocrText='LOTE ABC123\\nFAB 10/09/26\\nVAL 15/12/26'; window.calls=0; window.Tesseract={createWorker:async()=>({recognize:async()=>{window.calls++; await new Promise(r=>setTimeout(r,150));return {data:{text:window.ocrText}}},terminate:async()=>{}})};}""")
   data=page.evaluate("""() => {const c=document.createElement('canvas');c.width=20;c.height=20;return c.toDataURL().split(',')[1]}""")
   photo={'name':'test.png','mimeType':'image/png','buffer':base64.b64decode(data)}
   page.locator('[data-ocr-item="1"]').click()
   expect(page.locator('#ocrDialog')).to_be_visible()
   def read(text=None):
    if text is not None: page.evaluate('(t)=>window.ocrText=t',text)
    page.locator('#conferenceOCRImage').set_input_files(photo)
    expect(page.locator('#ocrConfirmForm')).to_be_visible()
   read(real_text)
   expect(page.locator('#ocrDialog')).to_be_visible()
   assert page.locator('#conferenceOCRRaw').text_content()==real_text
   assert page.locator('#ocrLot').input_value()=='307712215'
   assert page.locator('#ocr-expiry').input_value()=='18/11/2013'
   assert page.locator('#ocr-manufacture').input_value()==''
   assert all(page.locator('#'+field+'_1').input_value()=='' for field in ['lote','fabricacao','validade'])
   page.get_by_role('button',name='Confirmar',exact=True).click()
   expect(page.locator('#ocrDialog')).to_be_hidden()
   assert page.locator('#lote_1').input_value()=='307712215'
   assert page.locator('#validade_1').input_value()=='2013-11-18'
   assert page.locator('#fabricacao_1').input_value()==''
   page.locator('[data-ocr-item="1"]').click()
   read('sem dados')
   page.get_by_role('button',name='Confirmar',exact=True).click()
   page.locator('[data-ocr-item="1"]').click()
   read('LOTE ABC123\nFAB 10/09/26\nVAL 15/12/26')
   assert page.locator('#lote_1').input_value()==''
   assert page.locator('#ocr-manufacture').input_value()=='2026-09-10'
   page.locator('#ocr-expiry').select_option('2026-09-10')
   page.get_by_role('button',name='Confirmar',exact=True).click()
   expect(page.locator('#conferenceOCRError')).to_contain_text('datas diferentes')
   page.locator('#ocr-expiry').select_option('2026-12-15')
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   assert page.locator('#ocrDialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
   page.screenshot(path='/private/tmp/cv-ocr-confirm-'+engine.name+'-'+str(width)+'.png')
   page.get_by_role('button',name='Confirmar',exact=True).click()
   expect(page.locator('#ocrDialog')).to_be_hidden()
   assert page.locator('#lote_1').input_value()=='ABC123'
   assert page.locator('#fabricacao_1').input_value()=='2026-09-10'
   assert page.locator('#validade_1').input_value()=='2026-12-15'
   assert page.locator('#lote_2').input_value()==''
   page.locator('[data-ocr-item="1"]').click()
   read('FAB 15/12/26 VAL 10/09/26 LOTE A123 LOT B456')
   assert page.locator('#ocrLotChoice option').count()==3
   page.get_by_role('button',name='Confirmar',exact=True).click()
   expect(page.locator('#ocrOrderWarning')).to_be_visible()
   page.locator('#ocrCorrect').click()
   page.locator('#ocr-manufacture').fill('31/02/2026')
   page.get_by_role('button',name='Confirmar',exact=True).click()
   expect(page.locator('#conferenceOCRError')).to_contain_text('Data inválida')
   page.locator('#ocr-manufacture').fill('01/09/2026')
   page.locator('#ocrLot').fill('CORRIGIDO')
   page.get_by_role('button',name='Confirmar',exact=True).click()
   assert page.locator('#lote_1').input_value()=='CORRIGIDO'
   page.locator('[data-ocr-item="1"]').click()
   read('sem dados')
   page.get_by_role('button',name='Confirmar',exact=True).click()
   assert all(page.locator('#'+field+'_1').input_value()=='' for field in ['lote','fabricacao','validade'])
   page.locator('[data-ocr-item="1"]').click()
   read('FAB 15/12/26 VAL 10/09/26')
   page.get_by_role('button',name='Confirmar',exact=True).click()
   page.locator('#ocrAcceptOrder').check()
   page.get_by_role('button',name='Confirmar',exact=True).click()
   assert page.locator('#fabricacao_1').input_value()=='2026-12-15'
   page.locator('[data-ocr-item="1"]').click()
   read('10/09/26 15/12/26 01/01/27')
   assert page.locator('#ocr-manufacture').input_value()==''
   assert page.locator('#ocr-expiry option').count()==4
   page.locator('#ocrClose').click()
   assert page.locator('#fabricacao_1').input_value()=='2026-12-15'
   assert all(u.startswith('blob:') and method=='GET' for u,method in requests),requests
   with m.app.app_context():
    item=db.session.get(Conferencia,1).itens[0]
    assert not item.lote and not item.data_validade and item.status=='Pendente'
   page.close()
  browser.close()
server.shutdown()
''',env)
