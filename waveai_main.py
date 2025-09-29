# WaveAI - Platform Multi-Utilisateurs
# Version Finale Stable - Nouveau Repository
# Toutes fonctionnalités optimisées

import os
import logging
import secrets
import smtplib
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Flask Core
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

# Configuration Application
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Database Configuration avec fix PostgreSQL
database_url = os.environ.get('DATABASE_URL', 'sqlite:///waveai.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Initialisation
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# MODÈLES DE BASE DE DONNÉES
# =============================================================================

class User(db.Model):
    """Utilisateurs WaveAI"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relations
    ai_settings = db.relationship('AISettings', backref='user', lazy=True, cascade='all, delete-orphan')
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class AISettings(db.Model):
    """Paramètres IA utilisateur"""
    __tablename__ = 'ai_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # API Keys
    openai_api_key = db.Column(db.String(200))
    anthropic_api_key = db.Column(db.String(200))
    huggingface_token = db.Column(db.String(200))
    
    # Préférences
    default_model = db.Column(db.String(100), default='huggingface')
    use_ollama = db.Column(db.Boolean, default=True)
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=1000)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Conversation(db.Model):
    """Conversations utilisateur"""
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AppVersion(db.Model):
    """Versions application"""
    __tablename__ = 'app_versions'
    
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)
    release_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_current = db.Column(db.Boolean, default=False)

# =============================================================================
# SYSTÈME IA WAVEAI
# =============================================================================

class WaveAISystem:
    """Système IA WaveAI avec 5 agents spécialisés"""
    
    def __init__(self):
        self.agents = {
            'alex': {
                'name': 'Alex',
                'emoji': '🏢',
                'speciality': 'Agent Productivité',
                'description': 'Expert en emails, tâches et organisation professionnelle',
                'color': '#1e40af',
                'prompt': 'Tu es Alex, assistant IA spécialisé en productivité et organisation professionnelle. Tu aides avec les emails, la gestion des tâches, l\'optimisation du workflow et l\'organisation du travail.'
            },
            'lina': {
                'name': 'Lina',
                'emoji': '💼',
                'speciality': 'Agent LinkedIn',
                'description': 'Spécialiste du réseautage professionnel et LinkedIn',
                'color': '#0077b5',
                'prompt': 'Tu es Lina, experte en réseautage professionnel et LinkedIn. Tu aides à créer du contenu LinkedIn, développer son réseau professionnel, optimiser son profil et créer des posts engageants.'
            },
            'marco': {
                'name': 'Marco',
                'emoji': '📱',
                'speciality': 'Agent Social',
                'description': 'Expert réseaux sociaux et contenu viral',
                'color': '#f97316',
                'prompt': 'Tu es Marco, spécialiste des réseaux sociaux et du contenu viral. Tu aides à créer du contenu engageant, développer sa présence sociale, comprendre les tendances et optimiser sa stratégie sociale.'
            },
            'sofia': {
                'name': 'Sofia',
                'emoji': '📅',
                'speciality': 'Agent Planning',
                'description': 'Experte en calendriers et gestion du temps',
                'color': '#7c3aed',
                'prompt': 'Tu es Sofia, assistante spécialisée en gestion du temps et planification. Tu aides avec les calendriers, la programmation de rendez-vous, l\'organisation du temps et la gestion des priorités.'
            },
            'kai': {
                'name': 'Kai',
                'emoji': '💬',
                'speciality': 'Agent Conversationnel',
                'description': 'Compagnon IA pour discussions libres',
                'color': '#059669',
                'prompt': 'Tu es Kai, assistant IA conversationnel polyvalent. Tu peux discuter de tout, répondre aux questions générales, aider avec diverses tâches et être un compagnon IA amical et utile.'
            }
        }

    def check_ollama_availability(self):
        """Vérifie la disponibilité d'Ollama"""
        try:
            import requests
            response = requests.get('http://localhost:11434/api/tags', timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def get_huggingface_response(self, message, agent_type, settings=None):
        """Génère une réponse via Hugging Face (gratuit)"""
        try:
            import requests
            
            agent = self.agents.get(agent_type, self.agents['kai'])
            
            # Configuration headers
            headers = {'Content-Type': 'application/json'}
            if settings and settings.huggingface_token:
                headers['Authorization'] = f'Bearer {settings.huggingface_token}'

            # API Hugging Face
            url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
            
            payload = {
                "inputs": message,
                "parameters": {
                    "max_length": min(settings.max_tokens if settings else 1000, 1500),
                    "temperature": settings.temperature if settings else 0.7,
                    "return_full_text": False
                }
            }

            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    generated = result[0].get('generated_text', '').strip()
                    if generated and generated != message:
                        clean_response = generated.replace(message, '').strip()
                        if clean_response:
                            return {
                                'success': True,
                                'response': clean_response,
                                'agent': agent_type,
                                'model': 'huggingface',
                                'timestamp': datetime.utcnow().isoformat()
                            }
                            
        except Exception as e:
            logger.error(f"Erreur Hugging Face: {e}")
        
        return None

    def get_openai_response(self, message, agent_type, settings):
        """Génère une réponse via OpenAI"""
        try:
            if not settings or not settings.openai_api_key:
                return None

            import openai
            openai.api_key = settings.openai_api_key
            
            agent = self.agents.get(agent_type, self.agents['kai'])

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": agent['prompt']},
                    {"role": "user", "content": message}
                ],
                max_tokens=min(settings.max_tokens or 1000, 2000),
                temperature=settings.temperature or 0.7
            )

            return {
                'success': True,
                'response': response.choices[0].message.content.strip(),
                'model': 'openai',
                'agent': agent_type,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur OpenAI: {e}")
            return None

    def get_anthropic_response(self, message, agent_type, settings):
        """Génère une réponse via Anthropic Claude"""
        try:
            if not settings or not settings.anthropic_api_key:
                return None

            import anthropic
            client = anthropic.Client(api_key=settings.anthropic_api_key)
            
            agent = self.agents.get(agent_type, self.agents['kai'])

            response = client.completions.create(
                model="claude-instant-1.2",
                max_tokens_to_sample=min(settings.max_tokens or 1000, 1500),
                temperature=settings.temperature or 0.7,
                prompt=f"\n\nHuman: {agent['prompt']}\n\n{message}\n\nAssistant:"
            )

            return {
                'success': True,
                'response': response.completion.strip(),
                'model': 'anthropic',
                'agent': agent_type,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur Anthropic: {e}")
            return None

    def get_response(self, message, agent_type='kai', user_settings=None):
        """Génère une réponse avec système de fallback"""
        if not message or not message.strip():
            agent = self.agents.get(agent_type, self.agents['kai'])
            return {
                'success': True,
                'response': f"Bonjour ! Je suis {agent['name']}, {agent['speciality'].lower()}. Comment puis-je vous aider aujourd'hui ?",
                'agent': agent_type,
                'model': 'default',
                'timestamp': datetime.utcnow().isoformat()
            }

        # Ordre des tentatives selon les préférences utilisateur
        methods = []
        
        if user_settings:
            if user_settings.default_model == 'openai' and user_settings.openai_api_key:
                methods.append(self.get_openai_response)
            elif user_settings.default_model == 'anthropic' and user_settings.anthropic_api_key:
                methods.append(self.get_anthropic_response)

            # Ajouter les autres APIs disponibles
            if user_settings.openai_api_key and self.get_openai_response not in methods:
                methods.append(self.get_openai_response)
            if user_settings.anthropic_api_key and self.get_anthropic_response not in methods:
                methods.append(self.get_anthropic_response)

        # Hugging Face comme fallback gratuit
        methods.append(self.get_huggingface_response)

        # Essayer chaque méthode
        for method in methods:
            try:
                result = method(message, agent_type, user_settings)
                if result and result.get('success'):
                    return result
            except Exception as e:
                logger.error(f"Erreur méthode {method.__name__}: {e}")
                continue

        # Réponse de fallback si tout échoue
        agent = self.agents.get(agent_type, self.agents['kai'])
        return {
            'success': True,
            'response': f"Désolé, je rencontre des difficultés techniques. Je suis {agent['name']}, {agent['speciality'].lower()}. Pouvez-vous reformuler votre question ?",
            'agent': agent_type,
            'model': 'fallback',
            'timestamp': datetime.utcnow().isoformat()
        }

# Instance globale du système IA
ai_system = WaveAISystem()

# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def validate_email(email):
    """Validation robuste des emails"""
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None and len(email) <= 120

def get_user_settings(user_id):
    """Récupère les paramètres IA d'un utilisateur"""
    try:
        settings = AISettings.query.filter_by(user_id=user_id).first()
        if not settings:
            settings = AISettings(user_id=user_id)
            db.session.add(settings)
            db.session.commit()
        return settings
    except Exception as e:
        logger.error(f"Erreur get_user_settings: {e}")
        return None

# =============================================================================
# ROUTES PRINCIPALES
# =============================================================================

@app.route('/')
def landing():
    """Page d'accueil WaveAI"""
    try:
        return render_template('landing.html')
    except Exception as e:
        logger.error(f"Erreur landing: {e}")
        return "Erreur de chargement", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Connexion utilisateur"""
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower()
            
            if not validate_email(email):
                flash('Adresse email invalide', 'error')
                return render_template('login.html')

            # Recherche ou création utilisateur
            user = User.query.filter_by(email=email).first()

            if not user:
                # Créer nouvel utilisateur
                name = email.split('@')[0].capitalize()
                user = User(email=email, name=name)
                db.session.add(user)
                db.session.flush()

                # Créer paramètres par défaut
                settings = AISettings(user_id=user.id)
                db.session.add(settings)
                db.session.commit()

                logger.info(f"Nouvel utilisateur créé: {email}")

            # Connexion
            user.last_login = datetime.utcnow()
            db.session.commit()

            session['user_id'] = user.id
            session['user_email'] = user.email
            session['user_name'] = user.name
            session.permanent = True

            flash(f'Connexion réussie ! Bienvenue {user.name}', 'success')
            return redirect(url_for('dashboard'))

        except Exception as e:
            logger.error(f"Erreur connexion: {e}")
            flash('Erreur de connexion', 'error')
            return render_template('login.html')

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Déconnexion utilisateur"""
    session.clear()
    flash('Déconnexion réussie', 'info')
    return redirect(url_for('landing'))

@app.route('/dashboard')
def dashboard():
    """Tableau de bord principal"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            return redirect(url_for('login'))

        # Statistiques utilisateur
        stats = {
            'total_conversations': Conversation.query.filter_by(user_id=user.id).count(),
            'agents_used': db.session.query(Conversation.agent_type).filter_by(user_id=user.id).distinct().count(),
            'last_activity': user.last_login.strftime('%d/%m/%Y') if user.last_login else 'Jamais',
            'member_since': user.created_at.strftime('%d/%m/%Y') if user.created_at else 'Inconnu'
        }

        return render_template('dashboard.html', 
                             user=user, 
                             stats=stats, 
                             agents=ai_system.agents,
                             ollama_available=ai_system.check_ollama_availability())
                             
    except Exception as e:
        logger.error(f"Erreur dashboard: {e}")
        flash('Erreur de chargement du dashboard', 'error')
        return redirect(url_for('login'))

@app.route('/ai-settings', methods=['GET', 'POST'])
def ai_settings():
    """Configuration des paramètres IA"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.get(session['user_id'])
        if not user:
            return redirect(url_for('login'))

        settings = get_user_settings(user.id)

        if request.method == 'POST':
            if settings:
                # Mise à jour des paramètres
                settings.openai_api_key = request.form.get('openai_key', '').strip()
                settings.anthropic_api_key = request.form.get('anthropic_key', '').strip()
                settings.huggingface_token = request.form.get('huggingface_token', '').strip()
                settings.default_model = request.form.get('default_model', 'huggingface')
                settings.use_ollama = 'use_ollama' in request.form

                # Validation des paramètres numériques
                try:
                    temp = float(request.form.get('temperature', 0.7))
                    settings.temperature = max(0.0, min(1.0, temp))
                except (ValueError, TypeError):
                    settings.temperature = 0.7

                try:
                    tokens = int(request.form.get('max_tokens', 1000))
                    settings.max_tokens = max(100, min(4000, tokens))
                except (ValueError, TypeError):
                    settings.max_tokens = 1000

                settings.updated_at = datetime.utcnow()
                db.session.commit()

                flash('Paramètres IA mis à jour avec succès !', 'success')
                return redirect(url_for('ai_settings'))

        return render_template('ai_settings.html', user=user, settings=settings)

    except Exception as e:
        logger.error(f"Erreur ai_settings: {e}")
        flash('Erreur de configuration IA', 'error')
        return redirect(url_for('dashboard'))

@app.route('/chat/<agent_type>')
def chat(agent_type):
    """Interface de chat avec un agent"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if agent_type not in ai_system.agents:
        flash('Agent non trouvé', 'error')
        return redirect(url_for('dashboard'))

    user = User.query.get(session['user_id'])
    agent = ai_system.agents[agent_type]
    
    return render_template('chat.html', user=user, agent=agent, agent_type=agent_type)

# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API de chat avec les agents"""
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données manquantes'}), 400

        message = data.get('message', '').strip()
        agent_type = data.get('agent_type', 'kai')

        if not message:
            return jsonify({'error': 'Message vide'}), 400

        if len(message) > 5000:
            return jsonify({'error': 'Message trop long'}), 400

        if agent_type not in ai_system.agents:
            return jsonify({'error': 'Agent invalide'}), 400

        # Récupérer utilisateur et paramètres
        user_id = session['user_id']
        settings = get_user_settings(user_id)

        # Générer réponse IA
        response = ai_system.get_response(message, agent_type, settings)

        # Sauvegarder conversation
        try:
            conversation_data = {
                'user_message': message,
                'ai_response': response.get('response', ''),
                'agent_type': agent_type,
                'model_used': response.get('model', 'unknown')
            }
            
            conversation = Conversation(
                user_id=user_id,
                agent_type=agent_type,
                message=message,
                response=response.get('response', '')
            )
            db.session.add(conversation)
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde conversation: {e}")

        return jsonify({
            'success': True,
            'response': response.get('response', ''),
            'agent': agent_type,
            'model': response.get('model', 'unknown'),
            'timestamp': response.get('timestamp', datetime.utcnow().isoformat())
        })

    except Exception as e:
        logger.error(f"Erreur API chat: {e}")
        return jsonify({'error': 'Erreur serveur'}), 500

@app.route('/api/status')
def api_status():
    """Status de l'application"""
    try:
        return jsonify({
            'status': 'ok',
            'version': '1.0.0',
            'timestamp': datetime.utcnow().isoformat(),
            'agents_available': len(ai_system.agents),
            'ollama_available': ai_system.check_ollama_availability()
        })
    except Exception as e:
        logger.error(f"Erreur status: {e}")
        return jsonify({'error': 'Erreur status'}), 500

# =============================================================================
# PWA ET MANIFEST
# =============================================================================

@app.route('/manifest.json')
def manifest():
    """Manifest PWA"""
    try:
        manifest_data = {
            "name": "WaveAI - Agents IA Intelligents",
            "short_name": "WaveAI",
            "description": "Plateforme d'agents IA spécialisés pour la productivité",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0f172a",
            "theme_color": "#0ea5e9",
            "icons": [
                {
                    "src": "/static/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png"
                },
                {
                    "src": "/static/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png"
                }
            ]
        }
        
        response = make_response(jsonify(manifest_data))
        response.headers['Content-Type'] = 'application/manifest+json'
        return response
        
    except Exception as e:
        logger.error(f"Erreur manifest: {e}")
        return jsonify({"error": "Erreur manifest"}), 500

# =============================================================================
# GESTIONNAIRES D'ERREURS
# =============================================================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error='Page non trouvée'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('error.html', error='Erreur interne du serveur'), 500

# =============================================================================
# INITIALISATION
# =============================================================================

def init_database():
    """Initialise la base de données"""
    try:
        with app.app_context():
            db.create_all()

            # Version par défaut
            if not AppVersion.query.filter_by(is_current=True).first():
                version = AppVersion(
                    version='1.0.0',
                    description='Version initiale de WaveAI',
                    is_current=True
                )
                db.session.add(version)
                db.session.commit()

            logger.info("✅ Base de données WaveAI initialisée")
            return True
            
    except Exception as e:
        logger.error(f"❌ Erreur initialisation DB: {e}")
        return False

# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == '__main__':
    if init_database():
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('FLASK_ENV') == 'development'
        app.run(host='0.0.0.0', port=port, debug=debug)
    else:
        logger.error("❌ Échec initialisation")
else:
    # Mode production
    init_database()
