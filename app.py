from functools import wraps
from datetime import datetime, timedelta
import os
from pathlib import Path
from decimal import Decimal, InvalidOperation
from uuid import uuid4
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from models import Conferencia, ItemConferencia, ItemNFe, NFe, Usuario, db

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")


def uri_banco_de_dados():
    """Normaliza URLs PostgreSQL comuns para o driver psycopg instalado."""
    if not DATABASE_URL:
        return f"sqlite:///{BASE_DIR / 'database' / 'cv_market.db'}"
    if DATABASE_URL.startswith("postgres://"):
        return f"postgresql+psycopg://{DATABASE_URL.removeprefix('postgres://')}"
    if DATABASE_URL.startswith("postgresql://"):
        return f"postgresql+psycopg://{DATABASE_URL.removeprefix('postgresql://')}"
    return DATABASE_URL


def caminho_armazenamento_xml():
    """Retorna o diretório configurável dos XMLs originais.

    Sem configuração, preserva o comportamento local atual. Em produção, o
    diretório deve apontar para um armazenamento persistente quando ele estiver
    disponível.
    """
    diretorio_configurado = os.getenv("XML_STORAGE_DIR")
    return Path(diretorio_configurado) if diretorio_configurado else BASE_DIR / "uploads" / "nfes"


def configurar_secret_key():
    secret_key = os.getenv("SECRET_KEY")
    if secret_key:
        return secret_key
    raise RuntimeError("SECRET_KEY deve ser configurada por variável de ambiente.")

app = Flask(__name__)
app.config["SECRET_KEY"] = configurar_secret_key()
app.config["SQLALCHEMY_DATABASE_URI"] = uri_banco_de_dados()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["XML_STORAGE_DIR"] = caminho_armazenamento_xml()

STATUS_NFE = ("Importada", "Em conferência", "Conferida", "Com divergência")

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Entre para acessar o C&V MARKET."
login_manager.login_message_category = "info"


@login_manager.user_loader
def carregar_usuario(usuario_id):
    return db.session.get(Usuario, int(usuario_id))


def somente_admin(view):
    @wraps(view)
    def funcao_protegida(*args, **kwargs):
        if current_user.perfil != "admin":
            abort(403)
        return view(*args, **kwargs)

    return funcao_protegida


def criar_estrutura_inicial():
    if not DATABASE_URL:
        (BASE_DIR / "database").mkdir(exist_ok=True)
    app.config["XML_STORAGE_DIR"].mkdir(parents=True, exist_ok=True)
    db.create_all()
    migrar_banco_existente()

    if Usuario.query.first():
        return

    nome = os.getenv("BOOTSTRAP_ADMIN_NAME")
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    senha = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if all((nome, email, senha)):
        admin = Usuario(nome=nome.strip(), email=email.strip().lower(), perfil="admin")
        admin.definir_senha(senha)
        db.session.add(admin)
        db.session.commit()


def migrar_banco_existente():
    """Inclui somente as colunas novas, preservando o SQLite já existente."""
    if db.engine.dialect.name != "sqlite":
        return
    colunas = {linha[1] for linha in db.session.connection().exec_driver_sql("PRAGMA table_info(nfes)")}
    alteracoes = {
        "usuario_importacao_id": "INTEGER REFERENCES usuarios(id)",
        "status": "VARCHAR(30) NOT NULL DEFAULT 'Importada'",
        "xml_original_path": "VARCHAR(255)",
    }
    for coluna, definicao in alteracoes.items():
        if coluna not in colunas:
            db.session.connection().exec_driver_sql(f"ALTER TABLE nfes ADD COLUMN {coluna} {definicao}")
    db.session.connection().exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_nfes_usuario_importacao_id ON nfes (usuario_importacao_id)"
    )
    db.session.connection().exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_nfes_status ON nfes (status)")
    db.session.commit()


def texto(elemento, nome, padrao=None):
    """Obtém o texto de uma tag sem depender do namespace da NF-e."""
    if elemento is None:
        return padrao
    for filho_xml in elemento.iter():
        if filho_xml.tag.rsplit("}", 1)[-1] == nome and filho_xml.text:
            return filho_xml.text.strip()
    return padrao


def filho(elemento, nome):
    if elemento is None:
        return None
    return next((item for item in elemento if item.tag.rsplit("}", 1)[-1] == nome), None)


def elementos(elemento, nome):
    return [item for item in elemento.iter() if item.tag.rsplit("}", 1)[-1] == nome]


def data_xml(valor, obrigatoria=False):
    if not valor:
        if obrigatoria:
            raise ValueError("A NF-e não possui data de emissão.")
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(valor, "%Y-%m-%d")
        except ValueError:
            if obrigatoria:
                raise ValueError("A data de emissão da NF-e é inválida.")
            return None


def decimal_xml(valor, campo):
    try:
        return Decimal(valor)
    except (InvalidOperation, TypeError):
        raise ValueError(f"O campo {campo} de um item da NF-e é inválido.")


def ler_nfe_xml(conteudo):
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError:
        raise ValueError("O arquivo XML está inválido ou corrompido.")

    inf_nfe = next((item for item in raiz.iter() if item.tag.rsplit("}", 1)[-1] == "infNFe"), None)
    if inf_nfe is None:
        raise ValueError("O XML enviado não é uma NF-e válida.")
    ide, emitente, destinatario = (filho(inf_nfe, tag) for tag in ("ide", "emit", "dest"))
    itens_xml = [item for item in inf_nfe if item.tag.rsplit("}", 1)[-1] == "det"]
    numero = texto(ide, "nNF")
    emissao = texto(ide, "dhEmi") or texto(ide, "dEmi")
    nome_emitente = texto(emitente, "xNome")
    if not all((ide, emitente, destinatario, numero, emissao, nome_emitente, itens_xml)):
        raise ValueError("O XML enviado não contém os dados obrigatórios de uma NF-e.")

    chave = (inf_nfe.attrib.get("Id") or "").removeprefix("NFe")
    if not chave:
        protocolo = next((item for item in raiz.iter() if item.tag.rsplit("}", 1)[-1] == "infProt"), None)
        chave = texto(protocolo, "chNFe")
    if chave and (not chave.isdigit() or len(chave) != 44):
        chave = None

    dados_itens = []
    for det in itens_xml:
        prod = filho(det, "prod")
        if prod is None:
            raise ValueError("A NF-e possui um item sem dados de produto.")
        rastro = next(iter(elementos(prod, "rastro")), None)
        numero_item = det.attrib.get("nItem")
        if not numero_item or not texto(prod, "xProd"):
            raise ValueError("A NF-e possui um item com dados obrigatórios ausentes.")
        try:
            numero_item = int(numero_item)
        except ValueError:
            raise ValueError("O número de um item da NF-e é inválido.")
        dados_itens.append({
            "numero_item": numero_item,
            "codigo_produto": texto(prod, "cProd"),
            "ean": texto(prod, "cEAN") or texto(prod, "cEANTrib"),
            "descricao": texto(prod, "xProd"),
            "ncm": texto(prod, "NCM"),
            "unidade": texto(prod, "uCom"),
            "quantidade": decimal_xml(texto(prod, "qCom"), "qCom"),
            "valor_unitario": decimal_xml(texto(prod, "vUnCom"), "vUnCom"),
            "valor_total": decimal_xml(texto(prod, "vProd"), "vProd"),
            "lote": texto(rastro, "nLote"),
            "data_fabricacao": data_xml(texto(rastro, "dFab")).date() if texto(rastro, "dFab") else None,
            "data_validade": data_xml(texto(rastro, "dVal")).date() if texto(rastro, "dVal") else None,
        })
    return {
        "chave_acesso": chave, "numero": numero, "data_emissao": data_xml(emissao, obrigatoria=True),
        "cnpj_emitente": texto(emitente, "CNPJ") or texto(emitente, "CPF"), "nome_emitente": nome_emitente,
        "cnpj_destinatario": texto(destinatario, "CNPJ") or texto(destinatario, "CPF"),
        "nome_destinatario": texto(destinatario, "xNome"), "itens": dados_itens,
    }


@app.route("/")
def inicio():
    return redirect(url_for("dashboard" if current_user.is_authenticated else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and usuario.ativo and usuario.verificar_senha(senha):
            login_user(usuario)
            return redirect(url_for("dashboard"))
        flash("E-mail ou senha inválidos.", "error")
    return render_template("login.html")


@app.route("/sair")
@login_required
def sair():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html", titulo="Dashboard", total_nfes=NFe.query.count(),
        conferencias_pendentes=NFe.query.filter_by(status="Em conferência").count(),
        produtos_conferidos=ItemConferencia.query.filter_by(status="OK").count(),
    )


@app.route("/importar", methods=["GET", "POST"])
@login_required
def importar():
    if request.method == "POST":
        arquivo = request.files.get("xml")
        nome_arquivo = secure_filename(arquivo.filename or "") if arquivo else ""
        if not arquivo or not nome_arquivo:
            flash("Selecione um arquivo XML da NF-e para importar.", "error")
            return redirect(url_for("importar"))
        if Path(nome_arquivo).suffix.lower() != ".xml":
            flash("Envie somente arquivos no formato XML.", "error")
            return redirect(url_for("importar"))
        try:
            conteudo_xml = arquivo.read()
            dados = ler_nfe_xml(conteudo_xml)
            if dados["chave_acesso"] and NFe.query.filter_by(chave_acesso=dados["chave_acesso"]).first():
                flash("Esta NF-e já foi importada.", "error")
                return redirect(url_for("importar"))
            if not dados["chave_acesso"] and NFe.query.filter_by(
                numero=dados["numero"], cnpj_emitente=dados["cnpj_emitente"], data_emissao=dados["data_emissao"]
            ).first():
                flash("Esta NF-e já foi importada.", "error")
                return redirect(url_for("importar"))

            nome_interno = f"{uuid4().hex}.xml"
            caminho_xml = app.config["XML_STORAGE_DIR"] / nome_interno
            caminho_xml.write_bytes(conteudo_xml)
            nota = NFe(
                chave_acesso=dados["chave_acesso"], numero=dados["numero"], data_emissao=dados["data_emissao"],
                cnpj_emitente=dados["cnpj_emitente"], nome_emitente=dados["nome_emitente"],
                cnpj_destinatario=dados["cnpj_destinatario"], nome_destinatario=dados["nome_destinatario"],
                data_importacao=datetime.now(), usuario_importacao_id=current_user.id,
                status="Importada", xml_original_path=nome_interno,
            )
            nota.itens = [ItemNFe(**item) for item in dados["itens"]]
            db.session.add(nota)
            db.session.commit()
        except ValueError as erro:
            flash(str(erro), "error")
            return redirect(url_for("importar"))
        except IntegrityError:
            db.session.rollback()
            if 'caminho_xml' in locals() and caminho_xml.exists():
                caminho_xml.unlink()
            flash("Esta NF-e já foi importada.", "error")
            return redirect(url_for("importar"))
        flash("NF-e importada com sucesso.", "success")
        return redirect(url_for("detalhe_nfe", nfe_id=nota.id))
    return render_template("importar.html", titulo="Importar NF-e")


@app.route("/importar/<int:nfe_id>")
@login_required
def detalhe_nfe(nfe_id):
    nota = db.get_or_404(NFe, nfe_id)
    return render_template("nfe_detalhe.html", titulo=f"NF-e nº {nota.numero}", nota=nota)


def data_formulario(valor, campo):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError(f"A {campo} deve estar no formato DD/MM/AAAA.")


def atualizar_conferencia(conferencia):
    """Atualiza os itens recebidos e calcula seus status sem finalizar a conferência."""
    if conferencia.status != "Em andamento":
        raise ValueError("Esta conferência já foi finalizada e não pode ser alterada.")
    for item in conferencia.itens:
        quantidade = request.form.get(f"quantidade_{item.id}", "").strip().replace(",", ".")
        if quantidade:
            try:
                recebida = Decimal(quantidade)
            except InvalidOperation:
                raise ValueError("Informe uma quantidade recebida válida.")
            if recebida < 0:
                raise ValueError("A quantidade recebida não pode ser negativa.")
            item.quantidade_recebida = recebida
            item.status = "OK" if recebida == item.quantidade_esperada else "Divergência"
        else:
            item.quantidade_recebida = None
            item.status = "Pendente"
        item.lote = request.form.get(f"lote_{item.id}", "").strip() or None
        item.data_fabricacao = data_formulario(request.form.get(f"fabricacao_{item.id}", "").strip(), "data de fabricação")
        item.data_validade = data_formulario(request.form.get(f"validade_{item.id}", "").strip(), "data de validade")
        item.observacao = request.form.get(f"observacao_{item.id}", "").strip() or None
    conferencia.observacoes = request.form.get("observacoes", "").strip() or None


@app.route("/nfes-recebidas/<int:nfe_id>/iniciar-conferencia", methods=["POST"])
@login_required
def iniciar_conferencia(nfe_id):
    nota = db.get_or_404(NFe, nfe_id)
    if nota.conferencia:
        flash("Já existe uma conferência para esta NF-e.", "info")
        return redirect(url_for("ver_conferencia", conferencia_id=nota.conferencia.id))
    if nota.status != "Importada":
        flash("Esta NF-e não está disponível para iniciar uma nova conferência.", "error")
        return redirect(url_for("detalhe_nfe", nfe_id=nota.id))
    conferencia = Conferencia(nfe_id=nota.id, usuario_id=current_user.id, data_inicio=datetime.now(), status="Em andamento")
    db.session.add(conferencia)
    conferencia.itens = [
        ItemConferencia(
            item_nfe_id=item.id, quantidade_esperada=item.quantidade, lote=item.lote,
            data_fabricacao=item.data_fabricacao, data_validade=item.data_validade,
        ) for item in nota.itens
    ]
    nota.status = "Em conferência"
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        conferencia_existente = Conferencia.query.filter_by(nfe_id=nota.id).first()
        flash("Já existe uma conferência para esta NF-e.", "info")
        return redirect(url_for("ver_conferencia", conferencia_id=conferencia_existente.id))
    flash("Conferência iniciada. Informe os produtos recebidos.", "success")
    return redirect(url_for("ver_conferencia", conferencia_id=conferencia.id))


@app.route("/conferencias/<int:conferencia_id>")
@login_required
def ver_conferencia(conferencia_id):
    conferencia = db.get_or_404(Conferencia, conferencia_id)
    total = len(conferencia.itens)
    conferidos = sum(item.quantidade_recebida is not None for item in conferencia.itens)
    progresso = round((conferidos / total) * 100) if total else 0
    return render_template("conferencia_recebimento.html", titulo="Conferência de Recebimento", conferencia=conferencia,
                           total=total, conferidos=conferidos, progresso=progresso)


@app.route("/conferencias/<int:conferencia_id>/salvar", methods=["POST"])
@login_required
def salvar_conferencia(conferencia_id):
    conferencia = db.get_or_404(Conferencia, conferencia_id)
    try:
        atualizar_conferencia(conferencia)
        db.session.commit()
        flash("Conferência salva com sucesso.", "success")
    except ValueError as erro:
        db.session.rollback()
        flash(str(erro), "error")
    return redirect(url_for("ver_conferencia", conferencia_id=conferencia.id))


@app.route("/conferencias/<int:conferencia_id>/finalizar", methods=["POST"])
@login_required
def finalizar_conferencia(conferencia_id):
    conferencia = db.get_or_404(Conferencia, conferencia_id)
    try:
        atualizar_conferencia(conferencia)
        if any(item.quantidade_recebida is None for item in conferencia.itens):
            db.session.rollback()
            flash("Existem produtos que ainda não foram conferidos.", "error")
            return redirect(url_for("ver_conferencia", conferencia_id=conferencia.id))
        possui_divergencia = any(item.status == "Divergência" for item in conferencia.itens)
        conferencia.status = "Com divergência" if possui_divergencia else "Conferida"
        conferencia.data_finalizacao = datetime.now()
        conferencia.nfe.status = conferencia.status
        db.session.commit()
        flash("Conferência finalizada com sucesso.", "success")
    except ValueError as erro:
        db.session.rollback()
        flash(str(erro), "error")
    return redirect(url_for("ver_conferencia", conferencia_id=conferencia.id))


@app.route("/nfes-recebidas")
@login_required
def nfes_recebidas():
    busca = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim = request.args.get("data_fim", "").strip()
    consulta = NFe.query
    if busca:
        termo = f"%{busca}%"
        consulta = consulta.filter(or_(
            NFe.numero.ilike(termo), NFe.nome_emitente.ilike(termo), NFe.cnpj_emitente.ilike(termo),
            NFe.chave_acesso.ilike(termo),
        ))
    if status in STATUS_NFE:
        consulta = consulta.filter_by(status=status)
    if data_inicio:
        try:
            consulta = consulta.filter(NFe.data_emissao >= datetime.strptime(data_inicio, "%Y-%m-%d"))
        except ValueError:
            pass
    if data_fim:
        try:
            fim = datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
            consulta = consulta.filter(NFe.data_emissao < fim)
        except ValueError:
            pass
    notas = consulta.order_by(NFe.data_importacao.desc()).all()
    return render_template("nfes_recebidas.html", titulo="NF-e Recebidas", notas=notas, status_opcoes=STATUS_NFE)


@app.route("/nfes-recebidas/<int:nfe_id>/xml")
@login_required
@somente_admin
def xml_original_nfe(nfe_id):
    nota = db.get_or_404(NFe, nfe_id)
    if not nota.xml_original_path:
        flash("O XML original não foi armazenado para esta NF-e importada anteriormente.", "info")
        return redirect(url_for("detalhe_nfe", nfe_id=nota.id))
    diretorio = app.config["XML_STORAGE_DIR"]
    caminho = diretorio / Path(nota.xml_original_path).name
    if not caminho.is_file():
        abort(404)
    return send_from_directory(diretorio, caminho.name, mimetype="application/xml", as_attachment=True,
                               download_name=f"nfe-{nota.id}.xml")


@app.errorhandler(413)
def arquivo_muito_grande(_erro):
    flash("O arquivo XML é muito grande. O limite é de 5 MB.", "error")
    return redirect(url_for("importar"))


@app.route("/conferencias")
@login_required
def conferencia():
    conferencias = Conferencia.query.order_by(Conferencia.data_inicio.desc()).all()
    return render_template("conferencia.html", titulo="Conferências", conferencias=conferencias)


@app.route("/produtos")
@login_required
def produtos():
    produtos_lista = [
        ("Arroz tipo 1 - 5 kg", "7896006701517", "15/02/2027", "ARZ-2026"),
        ("Leite integral - 1 L", "7891000100103", "20/09/2026", "LT-0926"),
        ("Café torrado - 500 g", "7896089012345", "—", "—"),
    ]
    return render_template("produtos.html", titulo="Produtos", produtos=produtos_lista)


@app.route("/usuarios", methods=["GET", "POST"])
@login_required
@somente_admin
def usuarios():
    formulario = {"nome": "", "email": "", "perfil": "operador", "ativo": True}

    if request.method == "POST":
        formulario = {
            "nome": request.form.get("nome", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "perfil": request.form.get("perfil", "operador"),
            "ativo": request.form.get("ativo") == "on",
        }
        senha = request.form.get("senha", "")

        if not all((formulario["nome"], formulario["email"], senha)):
            flash("Preencha nome, e-mail e senha.", "error")
        elif "@" not in formulario["email"]:
            flash("Informe um e-mail válido.", "error")
        elif formulario["perfil"] not in ("admin", "operador"):
            flash("Selecione um perfil de usuário válido.", "error")
        elif len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
        elif Usuario.query.filter_by(email=formulario["email"]).first():
            flash("Já existe um usuário cadastrado com este e-mail.", "error")
        else:
            usuario = Usuario(
                nome=formulario["nome"], email=formulario["email"], perfil=formulario["perfil"],
                ativo=formulario["ativo"],
            )
            usuario.definir_senha(senha)
            try:
                db.session.add(usuario)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Já existe um usuário cadastrado com este e-mail.", "error")
            else:
                flash("Usuário criado com sucesso.", "success")
                return redirect(url_for("usuarios"))

    return render_template(
        "usuarios.html", titulo="Usuários", usuarios=Usuario.query.order_by(Usuario.nome).all(),
        novo=request.method == "POST" or request.args.get("novo") == "1", formulario=formulario,
    )


@app.route("/configuracoes")
@login_required
@somente_admin
def configuracoes():
    return render_template("configuracoes.html", titulo="Configurações")


@app.errorhandler(403)
def acesso_negado(_erro):
    return render_template("erro.html", titulo="Acesso restrito", mensagem="Você não possui permissão para acessar esta página."), 403


with app.app_context():
    criar_estrutura_inicial()


if __name__ == "__main__":
    app.run(debug=True)
