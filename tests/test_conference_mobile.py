"""Synthetic receiving tests: application copied to a temporary SQLite workspace."""
import os
import unittest
import test_production

FIXTURE = '''
from datetime import datetime
import app as m
from models import db, Usuario, NFe, ItemNFe, Conferencia
with m.app.app_context():
    db.create_all()
    user = Usuario(nome='Operador Teste', email='mobile@example.invalid', perfil='operador')
    user.definir_senha('test-only-password')
    db.session.add(user)
    nota = NFe(numero='123', nome_emitente='Fornecedor de testes responsivos', cnpj_emitente='0'*14,
               data_emissao=datetime.now(), data_importacao=datetime.now())
    db.session.add(nota)
    for index in range(3):
        nota.itens.append(ItemNFe(numero_item=index+1, descricao='Produto '+str(index+1)+' descrição longa '+ 'X'*100,
             ean='1234567890123', unidade='UN', quantidade=2, valor_unitario=1, valor_total=2))
    db.session.commit()
c = m.app.test_client()
c.post('/login', data={'email':'mobile@example.invalid','senha':'test-only-password'})
c.post('/nfes-recebidas/1/iniciar-conferencia')
'''


class ConferenceMobileTests(unittest.TestCase):
    setUp = test_production.ProductionTests.setUp
    def run_code(self, code, env=None):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-c', code], cwd=self.cwd,
                                env=env or self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_save_navigation_validation_and_finalization(self):
        self.run_code(FIXTURE + '''
data = {'item_atual':'0', 'navegacao':'proximo', 'quantidade_1':'2',
        'fabricacao_1':'2026-09-01', 'validade_1':'2027-09-01', 'lote_1':'L01',
        'observacao_1':'Teste', 'observacoes':'Observação geral'}
r = c.post('/conferencias/1/salvar', data=data)
assert r.location.endswith('?item=1')
with m.app.app_context():
    conf = db.session.get(Conferencia, 1)
    assert [i.status for i in conf.itens] == ['OK','Pendente','Pendente']
    assert conf.itens[0].data_fabricacao.isoformat() == '2026-09-01'
# Invalid quantity/date rolls back every item and does not advance.
for field, value in [('quantidade_1','-1'), ('validade_1','2026-02-30')]:
    bad = dict(data, **{field:value})
    r = c.post('/conferencias/1/salvar', data=bad)
    assert r.location.endswith('?item=0')
    with m.app.app_context():
        conf = db.session.get(Conferencia, 1)
        assert conf.itens[0].status == 'OK' and conf.itens[0].lote == 'L01'
        assert conf.itens[0].data_validade.isoformat() == '2027-09-01'
# Existing Brazilian date submissions still work; zero is a counted divergence.
data.update(quantidade_2='0', fabricacao_1='01/09/2026', item_atual='1')
assert c.post('/conferencias/1/salvar', data=data).location.endswith('?item=2')
c.post('/conferencias/1/finalizar', data=data)
with m.app.app_context():
    conf = db.session.get(Conferencia, 1)
    assert conf.status == 'Em andamento'
    assert [i.status for i in conf.itens] == ['OK','Divergência','Pendente']
data.update(quantidade_3='2', item_atual='2')
assert c.post('/conferencias/1/salvar', data=data).location.endswith('?item=2')
c.post('/conferencias/1/finalizar', data=data)
with m.app.app_context():
    assert db.session.get(Conferencia, 1).status == 'Com divergência'
c.post('/conferencias/1/salvar', data={'quantidade_1':'999'})
with m.app.app_context():
    assert db.session.get(Conferencia, 1).itens[0].quantidade_recebida == 2
''')

    @unittest.skipUnless(os.environ.get('CV_BROWSER_TESTS'), 'Opt-in: requires Playwright browsers')
    def test_responsive_browser(self):
        import shutil
        shutil.copytree(test_production.ROOT / 'static', self.cwd / 'static')
        env = dict(self.env, PYTHONPATH=os.environ.get('PYTHONPATH', ''),
                   PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH', ''))
        self.run_code(FIXTURE + '''
import threading
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
server = make_server('127.0.0.1', 0, m.app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = 'http://127.0.0.1:' + str(server.server_port)
with sync_playwright() as p:
    for engine in [p.chromium, p.webkit]:
        browser = engine.launch()
        for name, width, height in [('iphone',390,844),('android',360,800),('tablet',768,1024),('desktop',1440,900)]:
            page = browser.new_page(viewport={'width':width,'height':height}, is_mobile=width<900, has_touch=width<900)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url+'/login')
            page.locator('[name=email]').fill('mobile@example.invalid')
            page.locator('[name=senha]').fill('test-only-password')
            page.locator('button[type=submit]').click()
            page.goto(url+'/conferencias/1')
            def no_overflow():
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), (name, 'overflow')
            no_overflow()
            if width < 900:
                page.locator('#menuButton').click()
                assert page.locator('#menuButton').get_attribute('aria-expanded') == 'true'
                page.keyboard.press('Escape')
                assert page.locator('#menuButton').get_attribute('aria-expanded') == 'false'
                page.locator('#menuButton').click()
                page.locator('#menuBackdrop').click(position={'x':width-10,'y':200})
                assert page.locator('#menuButton').get_attribute('aria-expanded') == 'false'
            if width < 600:
                expect(page.locator('.conference-item:visible')).to_have_count(1)
                assert page.locator('#previousItem').is_disabled()
                for selector in ['#previousItem', '#saveNext', '#allItemsButton']:
                    assert page.locator(selector).bounding_box()['height'] >= 44
                assert page.locator('#saveNext').bounding_box()['width'] > page.locator('#previousItem').bounding_box()['width']
                expect(page.locator('.conference-item:visible .camera-placeholder')).to_be_disabled()
                page.locator('#quantidade_1').fill('2')
                page.locator('#lote_1').fill('MOBILE')
                page.locator('#fabricacao_1').fill('2026-09-01')
                page.locator('#validade_1').fill('2027-09-01')
                page.locator('#saveNext').click()
                page.wait_for_url('**/conferencias/1?item=1')
                assert page.locator('#itemPosition').inner_text() == 'Item 2 de 3'
                page.locator('#quantidade_2').fill('0')
                page.locator('#previousItem').click()
                assert page.locator('#lote_1').input_value() == 'MOBILE'
                page.locator('#allItemsButton').click()
                assert page.locator('.item-summary:visible').count() == 3
                expect(page.locator('#allItemsButton')).to_have_text('Voltar ao item')
                for summary in page.locator('.item-summary').all():
                    assert summary.bounding_box()['height'] >= 44
                    assert 'Esperada:' in summary.inner_text() and 'Recebida:' in summary.inner_text()
                    expect(summary.locator('strong')).to_be_visible()
                    expect(summary.locator('.badge')).to_be_visible()
                page.screenshot(path='/private/tmp/cv-summary-'+engine.name+'-'+name+'.png', full_page=True, animations='disabled')
                no_overflow()
                page.locator('.item-summary').nth(1).click()
                assert page.locator('#quantidade_2').input_value() == '0'
                page.locator('#saveNext').click()
                page.wait_for_url('**/conferencias/1?item=2')
                page.locator('#allItemsButton').click()
                assert 'Divergência' in page.locator('.item-summary').nth(1).inner_text()
                page.locator('.item-summary').nth(2).click()
                # Browser validation must reveal an invalid field in a hidden item.
                page.locator('#allItemsButton').click()
                page.locator('.item-summary').nth(0).click()
                page.locator('#quantidade_1').fill('-1')
                page.locator('#allItemsButton').click()
                page.locator('.item-summary').nth(2).click()
                page.locator('#saveNext').click()
                expect(page.locator('#quantidade_1')).to_be_visible()
                assert page.locator('#quantidade_1').input_value() == '-1'
                page.locator('#quantidade_1').fill('2')
                page.locator('#allItemsButton').click()
                page.locator('.item-summary').nth(2).click()
                page.locator('#quantidade_3').fill('2')
                page.locator('#saveNext').click()
                page.wait_for_url('**/conferencias/1?item=2')
                assert page.locator('#itemPosition').inner_text() == 'Item 3 de 3'
                page.set_viewport_size({'width':1024,'height':768})
                expect(page.locator('.conference-item:visible')).to_have_count(3)
                no_overflow()
                page.set_viewport_size({'width':width,'height':height})
                expect(page.locator('.conference-item:visible')).to_have_count(1)
            else:
                expect(page.locator('.conference-item:visible')).to_have_count(3)
            for extra_width in [320,600,601,900,901,1024]:
                page.set_viewport_size({'width':extra_width,'height':height})
                expect(page.locator('.conference-item:visible')).to_have_count(1 if extra_width <= 600 else 3)
                no_overflow()
            page.set_viewport_size({'width':width,'height':height})
            expect(page.locator('.conference-item:visible')).to_have_count(1 if width <= 600 else 3)
            no_overflow()
            page.screenshot(path='/private/tmp/cv-'+engine.name+'-'+name+'.png', full_page=True, animations='disabled')
            assert not errors, errors
            page.close()
        browser.close()
server.shutdown()
''', env)


if __name__ == '__main__':
    unittest.main()
