"""Testes isolados: nunca carregam o .env ou bancos reais do projeto."""
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cv-market-test-")
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        for name in ("app.py", "models.py"):
            shutil.copy2(ROOT / name, self.cwd / name)
        shutil.copytree(ROOT / "templates", self.cwd / "templates")
        self.env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "SYSTEMROOT")}
        self.env.update(SECRET_KEY=secrets.token_hex(32), DATABASE_URL="", APP_ENV="development",
                        PYTHONDONTWRITEBYTECODE="1")

    def run_code(self, code, env=None, success=True):
        result = subprocess.run([sys.executable, "-c", code], cwd=self.cwd,
                                env=env or self.env, capture_output=True, text=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, "Teste isolado falhou: " + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def production_env(self):
        return dict(self.env, APP_ENV="production", DATABASE_URL="postgresql://localhost/unused_test")

    def test_required_production_configuration(self):
        env = self.production_env()
        env["DATABASE_URL"] = ""
        (self.cwd / ".env").write_text("DATABASE_URL=sqlite:///must_not_load.db\nSECRET_KEY=fixture-only\n")
        result = self.run_code("import app", env, success=False)
        self.assertIn("DATABASE_URL é obrigatória", result.stderr)
        env["APP_ENV"] = "development"
        env["RENDER"] = "true"
        result = self.run_code("import app", env, success=False)
        self.assertIn("DATABASE_URL é obrigatória", result.stderr)
        env = self.production_env()
        env.pop("SECRET_KEY")
        result = self.run_code("import app", env, success=False)
        self.assertIn("SECRET_KEY deve ser configurada", result.stderr)
        env = self.production_env()
        env["DATABASE_URL"] = "sqlite:///forbidden.db"
        result = self.run_code("import app", env, success=False)
        self.assertIn("conexão PostgreSQL válida", result.stderr)
        self.assertFalse((self.cwd / "database").exists())

    def test_production_health_without_database_or_filesystem(self):
        self.run_code('''
import io, logging
import app
assert app.PRODUCTION and not app.app.debug
assert not app.app.config['XML_ARCHIVE_ENABLED']
assert app.app.config['SESSION_COOKIE_SECURE']
assert app.app.config['SESSION_COOKIE_HTTPONLY']
c = app.app.test_client()
r = c.get('/health')
assert r.status_code == 200 and r.json == {'status': 'ok'}
out = io.StringIO()
handler = logging.StreamHandler(out)
app.app.logger.addHandler(handler)
app.app.log_exception((ValueError, ValueError('sensitive-test-marker'), None))
assert 'sensitive-test-marker' not in out.getvalue()
''', self.production_env())
        self.assertFalse((self.cwd / "database").exists())
        self.assertFalse((self.cwd / "uploads").exists())

    def test_development_dotenv_and_override_false(self):
        (self.cwd / '.env').write_text('SECRET_KEY=synthetic-local-test-only\nDATABASE_URL=sqlite:///must-not-use.db\n')
        env = dict(self.env)
        env.pop('SECRET_KEY')
        self.run_code('''
import app
assert not app.PRODUCTION
assert app.app.config['SECRET_KEY'] == 'synthetic-local-test-only'
assert app.app.config['SQLALCHEMY_DATABASE_URI'].endswith('/database/cv_market.db')
assert app.app.test_client().get('/health').status_code == 200
''', env)

    def test_sqlite_login_users_nfe_conference_and_archive(self):
        self.run_code('''
import io, os
from pathlib import Path
import app as m
from models import db, Usuario, NFe, Conferencia
os.environ.update(BOOTSTRAP_ADMIN_NAME='Teste', BOOTSTRAP_ADMIN_EMAIL='admin@example.invalid',
                  BOOTSTRAP_ADMIN_PASSWORD=os.environ['SECRET_KEY'])
runner = m.app.test_cli_runner()
assert runner.invoke(args=['bootstrap-admin']).exit_code == 0
with m.app.app_context():
    assert Usuario.query.count() == 1
    before = Usuario.query.first().senha_hash
assert runner.invoke(args=['bootstrap-admin']).exit_code == 0
with m.app.app_context():
    assert Usuario.query.count() == 1 and Usuario.query.first().senha_hash == before
c = m.app.test_client()
assert c.get('/health').json == {'status': 'ok'}
assert c.get('/nfes-recebidas').status_code == 302
assert c.post('/login', data={'email':'admin@example.invalid','senha':'wrong'}).status_code == 200
assert c.get('/usuarios').status_code == 302
assert c.post('/login', data={'email':'admin@example.invalid','senha':os.environ['SECRET_KEY']}).status_code == 302
assert c.post('/usuarios', data={'nome':'Operador','email':'operator@example.invalid',
    'senha':os.environ['SECRET_KEY'],'perfil':'operador','ativo':'on'}).status_code == 302
with m.app.app_context():
    assert Usuario.query.count() == 2
    assert Usuario.query.filter_by(email='operator@example.invalid').first().verificar_senha(os.environ['SECRET_KEY'])
xml = b'<NFe><infNFe><ide><nNF>123</nNF><dhEmi>2026-09-08T10:00:00</dhEmi></ide><emit><CNPJ>00000000000000</CNPJ><xNome>Fornecedor Teste</xNome></emit><dest><CNPJ>00000000000000</CNPJ><xNome>Destino Teste</xNome></dest><det nItem="1"><prod><cProd>1</cProd><xProd>Produto Teste</xProd><qCom>2</qCom><vUnCom>3</vUnCom><vProd>6</vProd></prod></det></infNFe></NFe>'
assert c.post('/importar', data={'xml':(io.BytesIO(xml),'fixture.xml')}).status_code == 302
with m.app.app_context():
    nota = NFe.query.one()
    nid = nota.id
    assert nota.xml_original_path
assert c.get(f'/nfes-recebidas/{nid}/xml').data == xml
for route in ('/dashboard','/nfes-recebidas',f'/importar/{nid}','/conferencias','/usuarios'):
    assert c.get(route).status_code == 200
assert c.post(f'/nfes-recebidas/{nid}/iniciar-conferencia').status_code == 302
with m.app.app_context():
    conf = Conferencia.query.one()
    cid, iid = conf.id, conf.itens[0].id
assert c.get(f'/conferencias/{cid}').status_code == 200
assert c.post(f'/conferencias/{cid}/salvar', data={f'quantidade_{iid}':'2'}).status_code == 302
assert c.post(f'/conferencias/{cid}/finalizar', data={f'quantidade_{iid}':'2'}).status_code == 302
with m.app.app_context():
    assert Conferencia.query.one().status == 'Conferida'
    assert db.session.get(NFe, nid).status == 'Conferida'
# Exercita o modo sem arquivamento de produção em uma base SQLite isolada.
m.app.config['XML_ARCHIVE_ENABLED'] = False
files_before = list(m.app.config['XML_STORAGE_DIR'].iterdir())
xml2 = xml.replace(b'<nNF>123</nNF>', b'<nNF>124</nNF>')
assert c.post('/importar', data={'xml':(io.BytesIO(xml2),'fixture.xml')}).status_code == 302
with m.app.app_context():
    assert NFe.query.filter_by(numero='124').one().xml_original_path is None
assert list(m.app.config['XML_STORAGE_DIR'].iterdir()) == files_before
assert c.get(f'/nfes-recebidas/{nid}/xml').status_code == 302
assert b'Baixar XML original' not in c.get(f'/importar/{nid}').data
assert b'Consultar XML' not in c.get('/nfes-recebidas').data
assert 'não será armazenado' in c.get('/importar').get_data(as_text=True)
c.get('/sair')
c.post('/login', data={'email':'operator@example.invalid','senha':os.environ['SECRET_KEY']})
assert c.get('/usuarios').status_code == 403
''')

    def check_server(self, gunicorn=False):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = self.production_env() if gunicorn else dict(self.env)
        env['PORT'] = str(port)
        command = ([sys.executable, '-m', 'gunicorn', '--bind', f'0.0.0.0:{port}', 'app:app']
                   if gunicorn else [sys.executable, 'app.py'])
        proc = subprocess.Popen(command, cwd=self.cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    self.fail('Servidor encerrou antes de responder ao health check.')
                try:
                    with urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn(b'"status":"ok"', response.read())
                    return
                except OSError:
                    time.sleep(0.1)
            self.fail('Servidor não respondeu ao health check.')
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_python_app_sqlite_server(self):
        self.check_server()

    def test_gunicorn_production_server(self):
        self.check_server(gunicorn=True)


if __name__ == '__main__':
    unittest.main()
