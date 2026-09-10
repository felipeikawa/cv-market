import unittest
import test_production


FIXTURE = '''
import app as m
from models import db, Usuario, NFe, Conferencia
with m.app.app_context():
    db.create_all()
    admin = Usuario(nome='Admin', email='admin@test.invalid', perfil='admin')
    admin.definir_senha('admin-password')
    operator = Usuario(nome='Operador', email='operator@test.invalid', perfil='operador')
    operator.definir_senha('operator-password')
    db.session.add_all([admin, operator]); db.session.commit()
c = m.app.test_client()
assert c.post('/login', data={'email':'admin@test.invalid','senha':'admin-password'}).status_code == 302
'''


class UserManagementTests(unittest.TestCase):
    setUp = test_production.ProductionTests.setUp
    run_code = test_production.ProductionTests.run_code

    def test_management_rules(self):
        self.run_code(FIXTURE + '''
assert c.get('/usuarios').status_code == 200
assert b'Editar' in c.get('/usuarios').data and b'Excluir' in c.get('/usuarios').data
old_hash = None
with m.app.app_context(): old_hash = db.session.get(Usuario, 2).senha_hash
r = c.post('/usuarios/2/editar', data={'nome':'Operador Novo','email':'new@test.invalid','perfil':'operador','ativo':'on','senha':''})
assert r.status_code == 302 and 'Usuário atualizado com sucesso.' in c.get('/usuarios').get_data(as_text=True)
with m.app.app_context():
    u = db.session.get(Usuario, 2); assert u.nome == 'Operador Novo' and u.senha_hash == old_hash
assert c.post('/usuarios/2/editar', data={'nome':'Operador Novo','email':'admin@test.invalid','perfil':'operador','ativo':'on'}).status_code == 200
with m.app.app_context(): assert db.session.get(Usuario, 2).email == 'new@test.invalid'
assert c.post('/usuarios/2/editar', data={'nome':'Operador Novo','email':'new@test.invalid','perfil':'operador','ativo':'on','senha':'new-password'}).status_code == 302
c.get('/sair'); assert c.post('/login', data={'email':'new@test.invalid','senha':'operator-password'}).status_code == 200
c.get('/sair'); assert c.post('/login', data={'email':'new@test.invalid','senha':'new-password'}).status_code == 302
c.get('/sair'); assert c.post('/login', data={'email':'admin@test.invalid','senha':'admin-password'}).status_code == 302
assert c.post('/usuarios/2/alternar-status').status_code == 302
c.get('/sair'); assert c.post('/login', data={'email':'new@test.invalid','senha':'new-password'}).status_code == 200
c.post('/login', data={'email':'admin@test.invalid','senha':'admin-password'})
assert b'Reativar' in c.get('/usuarios').data
assert c.post('/usuarios/2/alternar-status').status_code == 302
c.get('/sair'); assert c.post('/login', data={'email':'new@test.invalid','senha':'new-password'}).status_code == 302
c.get('/sair'); assert c.post('/login', data={'email':'admin@test.invalid','senha':'admin-password'}).status_code == 302
assert c.post('/usuarios/2/excluir').status_code == 302
with m.app.app_context(): assert db.session.get(Usuario, 2) is None
c.get('/sair'); c.post('/login', data={'email':'admin@test.invalid','senha':'admin-password'})
assert c.post('/usuarios/1/alternar-status').status_code == 302
assert 'própria conta' in c.get('/usuarios').get_data(as_text=True)
assert c.post('/usuarios/1/excluir').status_code == 302
assert 'própria conta' in c.get('/usuarios').get_data(as_text=True)
with m.app.app_context():
    history = Usuario(nome='Com Histórico', email='history@test.invalid', perfil='operador'); history.definir_senha('history-pass')
    db.session.add(history); db.session.commit(); hid=history.id
    nfe=NFe(numero='1', nome_emitente='Teste', cnpj_emitente='0'*14, data_emissao=__import__('datetime').datetime.now(), data_importacao=__import__('datetime').datetime.now(), usuario_importacao_id=hid)
    db.session.add(nfe); db.session.commit()
assert c.post(f'/usuarios/{hid}/excluir').status_code == 302
assert 'possui histórico' in c.get('/usuarios').get_data(as_text=True)
with m.app.app_context(): assert db.session.get(Usuario, hid) is not None
''')

    def test_only_admin_and_last_admin(self):
        self.run_code(FIXTURE + '''
c.get('/sair'); c.post('/login', data={'email':'operator@test.invalid','senha':'operator-password'})
assert c.get('/usuarios').status_code == 403
assert c.post('/usuarios/1/alternar-status').status_code == 403
assert c.post('/usuarios/1/excluir').status_code == 403
c.get('/sair'); c.post('/login', data={'email':'admin@test.invalid','senha':'admin-password'})
r = c.post('/usuarios/1/editar', data={'nome':'Admin','email':'admin@test.invalid','perfil':'operador','ativo':'on'})
assert r.status_code == 200 and 'último administrador ativo' in r.get_data(as_text=True)
''')


if __name__ == '__main__':
    unittest.main()
