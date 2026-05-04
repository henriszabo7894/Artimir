from flask import Flask, render_template, request, redirect, url_for, abort, jsonify, session
import smtplib
import os
import re
import time
import uuid
import requests
from email.message import EmailMessage

try:
    from gpiozero import PWMOutputDevice, DigitalOutputDevice
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "artimir_secret_key_2026"

# =========================
# 🔧 MODE DEV (AJOUT)
# =========================
ADMIN_CODE = "1234"

@app.route("/admin-login", methods=["POST"])
def admin_login():
    data = request.get_json()
    if data.get("code") == ADMIN_CODE:
        session["admin"] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 403

@app.route("/admin-logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/")

# =====================================================
# SERVEUR MAPPING PC IA
# =====================================================

MAPPING_SERVER = "https://medicaid-copies-dude-dramatic.trycloudflare.com"


def mapping_command(command, artist=None):
    try:
        if artist:
            url = f"{MAPPING_SERVER}/command/{command}/{artist}"
        else:
            url = f"{MAPPING_SERVER}/command/{command}"

        response = requests.post(url, timeout=4)
        return response.ok

    except Exception as e:
        print("Erreur mapping :", e)
        return False


def mapping_start(artist):
    return mapping_command("start", artist)


def mapping_freeze():
    return mapping_command("freeze")


def mapping_resume():
    return mapping_command("resume")


def mapping_capture():
    return mapping_command("capture")


def mapping_narration_start():
    age_group = session.get("age_group", "adulte")
    return mapping_command(f"narration/start/{age_group}")


def mapping_narration_pause():
    return mapping_command("narration/pause")


def mapping_narration_resume():
    return mapping_command("narration/resume")


def mapping_narration_stop():
    return mapping_command("narration/stop")


# =====================================================
# FILE D’ATTENTE + SESSION
# =====================================================

queue = []
current_user = None
session_start = 0
blocked_users = {}
last_seen = {}
narration_active = False

SESSION_TIME = 300
BLOCK_TIME = 600
HEARTBEAT_TIMEOUT = 15


def get_user():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    return session["user_id"]


def cleanup_users():
    global current_user, session_start
    now = time.time()

    inactive = [u for u, seen in last_seen.items() if now - seen > HEARTBEAT_TIMEOUT]

    for user in inactive:
        if user in queue:
            queue.remove(user)

        if current_user == user:
            current_user = None
            session_start = 0
            motor_stop()
            mapping_narration_stop()
            mapping_freeze()

        last_seen.pop(user, None)


def expire_current_session():
    global current_user, session_start
    now = time.time()

    if current_user and now - session_start > SESSION_TIME:
        blocked_users[current_user] = now + BLOCK_TIME

        if current_user in queue:
            queue.remove(current_user)

        last_seen.pop(current_user, None)
        current_user = None
        session_start = 0

        motor_stop()
        mapping_narration_stop()
        mapping_freeze()


@app.route("/")
def index():
    global current_user, session_start

    user_id = get_user()
    now = time.time()

    cleanup_users()
    expire_current_session()

    # 🔥 MODE DEV → bypass total
    if session.get("admin"):
        return render_template("index.html")

    block_expiry = session.get("blocked_until") or blocked_users.get(user_id, 0)
    if block_expiry and now < block_expiry:
        remaining_seconds = int(block_expiry - now)
        return render_template("blocked.html", remaining_seconds=remaining_seconds)
    elif block_expiry:
        blocked_users.pop(user_id, None)
        session.pop("blocked_until", None)

    last_seen[user_id] = now

    if user_id not in queue:
        queue.append(user_id)

    position = queue.index(user_id)

    if current_user is None and position == 0:
        current_user = user_id
        session_start = now
        return render_template("index.html")

    estimated_wait = position * 5
    return render_template("busy.html", position=position + 1, estimated_wait=estimated_wait)


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    user_id = get_user()
    last_seen[user_id] = time.time()
    cleanup_users()
    expire_current_session()
    return jsonify({"status": "alive"})


@app.route("/reset")
def reset():
    global current_user, session_start

    user_id = get_user()
    now = time.time()

    # 🔥 ADMIN PAS BLOQUÉ
    if not session.get("admin"):
        blocked_users[user_id] = now + BLOCK_TIME
        session["blocked_until"] = now + BLOCK_TIME

    if user_id in queue:
        queue.remove(user_id)

    if current_user == user_id:
        current_user = None
        session_start = 0

    last_seen.pop(user_id, None)

    motor_stop()
    mapping_narration_stop()
    mapping_freeze()

    return render_template("finish.html")


# =====================================================
# EMAIL
# =====================================================

MAIL_SENDER = "artimir.project@gmail.com"
MAIL_PASSWORD = "iseadvhlktgzxrdw"


def is_valid_email(email):
    return re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$', email)


def download_captured_portrait():
    url = f"{MAPPING_SERVER}/capture/file"

    response = requests.get(url, timeout=10)

    if response.status_code != 200:
        raise Exception("Impossible de récupérer le portrait depuis le serveur IA.")

    os.makedirs("static/captures", exist_ok=True)

    image_path = os.path.join("static", "captures", "portrait_artimir.jpg")

    with open(image_path, "wb") as f:
        f.write(response.content)

    return image_path


def send_artimir_email(receiver_email):
    msg = EmailMessage()
    msg["Subject"] = "🎨 Merci d'avoir utilisé Artimir !"
    msg["From"] = MAIL_SENDER
    msg["To"] = receiver_email

    msg.set_content("""
Bonjour,

Merci d'avoir utilisé Artimir 🎨

Voici votre portrait transformé.
Vous êtes sublime ✨

L'équipe Artimir
""")

    image_path = download_captured_portrait()

    with open(image_path, "rb") as img:
        msg.add_attachment(
            img.read(),
            maintype="image",
            subtype="jpeg",
            filename="portrait_artimir.jpg"
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(MAIL_SENDER, MAIL_PASSWORD)
        smtp.send_message(msg)


@app.route("/api/send-email", methods=["POST"])
def api_send_email():
    data = request.get_json()
    email = data.get("email")

    if not email or not is_valid_email(email):
        return jsonify({"status": "error", "message": "Email invalide"}), 400

    try:
        mapping_capture()
        time.sleep(2)
        send_artimir_email(email)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =====================================================
# API MAPPING (appelée depuis le navigateur)
# =====================================================

@app.route("/api/mapping/status", methods=["GET"])
def api_mapping_status():
    return jsonify({"status": "success", "data": {"narration_active": narration_active}})


@app.route("/api/mapping/<path:command>", methods=["POST"])
def api_mapping(command):
    global narration_active

    if command == "narration/start":
        narration_active = True
        mapping_narration_start()
    elif command == "narration/pause":
        mapping_narration_pause()
    elif command == "narration/resume":
        narration_active = True
        mapping_narration_resume()
    elif command == "narration/stop":
        narration_active = False
        mapping_narration_stop()
    elif command == "freeze":
        mapping_freeze()
    elif command == "resume":
        mapping_resume()

    return jsonify({"status": "success"})


# =====================================================
# MOTEUR RASPBERRY
# =====================================================

SPEED = 0.8

if GPIO_AVAILABLE:
    R_EN = DigitalOutputDevice(23)
    L_EN = DigitalOutputDevice(24)
    RPWM = PWMOutputDevice(18)
    LPWM = PWMOutputDevice(19)

    R_EN.on()
    L_EN.on()

    def motor_stop():
        RPWM.value = 0
        LPWM.value = 0

    def motor_up():
        LPWM.value = 0
        RPWM.value = SPEED

    def motor_down():
        RPWM.value = 0
        LPWM.value = SPEED

else:
    def motor_stop():
        print("STOP moteur simulé")

    def motor_up():
        print("MONTER moteur simulé")

    def motor_down():
        print("DESCENDRE moteur simulé")


@app.route("/api/motor/up", methods=["POST"])
def api_motor_up():
    motor_up()
    return jsonify({"status": "success", "action": "up"})


@app.route("/api/motor/down", methods=["POST"])
def api_motor_down():
    motor_down()
    return jsonify({"status": "success", "action": "down"})


@app.route("/api/motor/stop", methods=["POST"])
def api_motor_stop():
    motor_stop()
    return jsonify({"status": "success", "action": "stop"})


# =====================================================
# DONNÉES ARTISTES
# =====================================================

ARTWORKS = {
    "joconde": {
        "artist_name": "Léonard de Vinci",
        "image_file": "joconde.jpg"
    },
    "vangogh": {
        "artist_name": "Vincent Van Gogh",
        "image_file": "vangogh.jpg"
    },
    "courbet": {
        "artist_name": "Gustave Courbet",
        "image_file": "courbet.jpg"
    }
}


BIOGRAPHIES = {
    "joconde": {
        "enfant": "Léonard de Vinci était un génie curieux qui aimait tout observer : les oiseaux, l’eau, les visages. Il a peint la Joconde avec un sourire mystérieux que personne n’a encore réussi à expliquer !",
        "ado": "Léonard de Vinci était à la fois peintre, scientifique et inventeur. La Joconde, peinte entre 1503 et 1519, est célèbre pour son regard énigmatique et la technique du sfumato, qui donne une impression de brume et de profondeur.",
        "adulte": "La Joconde de Léonard de Vinci, peinte entre 1503 et 1519, est le portrait le plus célèbre de l’histoire de l’art. La technique du sfumato — fondus de tons sans contours nets — confère à l’œuvre sa profondeur et son mystère. Son sourire ambigu et son regard omnidirectionnel continuent de fasciner les chercheurs.",
    },
    "vangogh": {
        "enfant": "Vincent Van Gogh aimait les couleurs vives et les tourbillons. Il a peint plus de 900 tableaux dans sa vie, dont beaucoup d’autoportraits pour se regarder lui-même !",
        "ado": "Van Gogh a peint plus de 35 autoportraits entre 1886 et 1889. Son style unique, fait de coups de pinceau tourbillonnants et de couleurs intenses, exprimait ses émotions profondes. Il n’a vendu qu’un seul tableau de son vivant.",
        "adulte": "Les autoportraits de Van Gogh, peints principalement entre 1886 et 1889, témoignent d’une quête identitaire intense. Sa technique post-impressionniste, aux coups de pinceau expressifs et aux couleurs saturées, influencera profondément l’expressionnisme du XXe siècle. Incompris de son vivant, il n’a vendu qu’une seule toile.",
    },
    "courbet": {
        "enfant": "Gustave Courbet a peint son propre visage avec une expression de grande surprise. Ce tableau s’appelle Le Désespéré — c’est comme un selfie, mais peint il y a plus de 170 ans !",
        "ado": "Le Désespéré est un autoportrait de Gustave Courbet peint vers 1843. Avec son regard écarquillé et ses mains dans les cheveux, Courbet se met en scène comme un personnage romantique tourmenté. C’est une œuvre très expressive, presque théâtrale.",
        "adulte": "Le Désespéré (vers 1843) est l’un des autoportraits les plus dramatiques de Courbet. Chef de file du réalisme français, il y met en scène sa propre image avec une intensité romantique — regard écarquillé, mains crispées dans les cheveux. Cette œuvre préfigure la manière dont il construira tout au long de sa vie son image publique d’artiste rebelle.",
    },
}


def get_biography(artist, age_group):
    return BIOGRAPHIES[artist][age_group]


@app.route("/select/<artist>")
def select_artist(artist):
    if artist not in ARTWORKS:
        abort(404)

    mapping_narration_stop()
    mapping_start(artist)
    mapping_resume()

    return render_template("age.html", artist=artist)


@app.route("/artwork/<artist>", methods=["POST"])
def artwork(artist):
    if artist not in ARTWORKS:
        abort(404)

    age = request.form.get("age")

    if not age:
        return redirect(url_for("select_artist", artist=artist))

    age = int(age)

    if age < 6:
        return render_template("age.html", artist=artist, error="Artimir n'est autorisé qu'à partir de l'âge de 6 ans.")

    if age <= 11:
        age_group = "enfant"
    elif age <= 17:
        age_group = "ado"
    else:
        age_group = "adulte"

    session["age"] = age
    session["age_group"] = age_group
    session["artist"] = artist

    data = ARTWORKS[artist]

    return render_template(
        "artwork.html",
        artist_name=data["artist_name"],
        image_file=data["image_file"],
        biography_text=get_biography(artist, age_group)
    )


# =====================================================
# LANCEMENT
# =====================================================

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    finally:
        motor_stop()
        mapping_narration_stop()
        mapping_freeze()