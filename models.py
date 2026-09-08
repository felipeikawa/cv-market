from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    perfil = db.Column(db.String(20), nullable=False, default="operador")
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    nfes_importadas = db.relationship("NFe", back_populates="usuario_importacao")
    conferencias = db.relationship("Conferencia", back_populates="usuario")

    def definir_senha(self, senha):
        # PBKDF2 is broadly supported by the Python 3.9 builds used in development.
        self.senha_hash = generate_password_hash(senha, method="pbkdf2:sha256")

    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


class NFe(db.Model):
    __tablename__ = "nfes"

    id = db.Column(db.Integer, primary_key=True)
    chave_acesso = db.Column(db.String(44), unique=True, nullable=True, index=True)
    numero = db.Column(db.String(20), nullable=False)
    data_emissao = db.Column(db.DateTime, nullable=False)
    cnpj_emitente = db.Column(db.String(14), nullable=False)
    nome_emitente = db.Column(db.String(255), nullable=False)
    cnpj_destinatario = db.Column(db.String(14), nullable=True)
    nome_destinatario = db.Column(db.String(255), nullable=True)
    data_importacao = db.Column(db.DateTime, nullable=False)
    usuario_importacao_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="Importada", index=True)
    xml_original_path = db.Column(db.String(255), nullable=True)

    usuario_importacao = db.relationship("Usuario", back_populates="nfes_importadas")

    itens = db.relationship(
        "ItemNFe", back_populates="nfe", cascade="all, delete-orphan", order_by="ItemNFe.numero_item"
    )
    conferencia = db.relationship(
        "Conferencia", back_populates="nfe", uselist=False, cascade="all, delete-orphan"
    )


class ItemNFe(db.Model):
    __tablename__ = "itens_nfe"

    id = db.Column(db.Integer, primary_key=True)
    nfe_id = db.Column(db.Integer, db.ForeignKey("nfes.id"), nullable=False, index=True)
    numero_item = db.Column(db.Integer, nullable=False)
    codigo_produto = db.Column(db.String(60), nullable=True)
    ean = db.Column(db.String(30), nullable=True)
    descricao = db.Column(db.String(255), nullable=False)
    ncm = db.Column(db.String(20), nullable=True)
    unidade = db.Column(db.String(20), nullable=True)
    quantidade = db.Column(db.Numeric(15, 4), nullable=False)
    valor_unitario = db.Column(db.Numeric(15, 4), nullable=False)
    valor_total = db.Column(db.Numeric(15, 2), nullable=False)
    lote = db.Column(db.String(60), nullable=True)
    data_fabricacao = db.Column(db.Date, nullable=True)
    data_validade = db.Column(db.Date, nullable=True)

    nfe = db.relationship("NFe", back_populates="itens")


class Conferencia(db.Model):
    __tablename__ = "conferencias"

    id = db.Column(db.Integer, primary_key=True)
    nfe_id = db.Column(db.Integer, db.ForeignKey("nfes.id"), nullable=False, unique=True, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    data_inicio = db.Column(db.DateTime, nullable=False)
    data_finalizacao = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Em andamento", index=True)
    observacoes = db.Column(db.Text, nullable=True)

    nfe = db.relationship("NFe", back_populates="conferencia")
    usuario = db.relationship("Usuario", back_populates="conferencias")
    itens = db.relationship(
        "ItemConferencia", back_populates="conferencia", cascade="all, delete-orphan",
        order_by="ItemConferencia.id"
    )


class ItemConferencia(db.Model):
    __tablename__ = "itens_conferencia"

    id = db.Column(db.Integer, primary_key=True)
    conferencia_id = db.Column(db.Integer, db.ForeignKey("conferencias.id"), nullable=False, index=True)
    item_nfe_id = db.Column(db.Integer, db.ForeignKey("itens_nfe.id"), nullable=False, unique=True, index=True)
    quantidade_esperada = db.Column(db.Numeric(15, 4), nullable=False)
    quantidade_recebida = db.Column(db.Numeric(15, 4), nullable=True)
    lote = db.Column(db.String(60), nullable=True)
    data_fabricacao = db.Column(db.Date, nullable=True)
    data_validade = db.Column(db.Date, nullable=True)
    observacao = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Pendente", index=True)

    conferencia = db.relationship("Conferencia", back_populates="itens")
    item_nfe = db.relationship("ItemNFe")
