from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import re
import secrets
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import httpx
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from seed_data import ETAPES, dossiers_seed, entreprises_seed, new_entreprise_id

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
UPLOAD_DIR = ROOT_DIR / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)
STATUTS_DIR = UPLOAD_DIR / 'statuts'
STATUTS_DIR.mkdir(exist_ok=True)
MAX_FILE_SIZE = 15 * 1024 * 1024
ALLOWED_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

app = FastAPI()
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AdminLogin(BaseModel):
    password: str


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: str
    titre: str
    acteur: str
    rccm: str
    date_immatriculation: str
    ressort: str
    date_impression: str
    numero_procedure: str
    reference: str
    fichier_nom: Optional[str] = None
    fichier_type: Optional[str] = None
    created_at: str
    scans: int = 0
    dernier_scan: Optional[str] = None


class EntrepriseIn(BaseModel):
    denomination: str
    forme: str
    formeLongue: str
    rccm: str
    dateImmatriculation: str
    ressort: str
    siege: str = "—"
    objet: str = "—"
    capital: str = "—"
    duree: str = "—"
    gerant: str = "—"
    statut: str = "Actif"
    type: str = "Société commerciale"
    genre: str = "—"
    annonce: bool = True


class Etape(BaseModel):
    label: str
    detail: str
    date: Optional[str] = None


class DossierIn(BaseModel):
    numero: str
    denomination: str
    forme: str = "SARL"
    ressort: str
    dirigeant: str = "—"
    etape_courante: int = Field(0, ge=0, le=3)
    cloture: bool = False
    etapes: List[Etape] = Field(default_factory=lambda: [Etape(label=l, detail=d) for l, d in ETAPES])


def create_admin_token() -> str:
    payload = {"sub": "admin", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def require_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")
    return payload


async def check_lockout(ip: str):
    rec = await db.login_attempts.find_one({"identifier": ip})
    if rec and rec.get("count", 0) >= 5:
        locked_until = datetime.fromisoformat(rec["locked_until"])
        if datetime.now(timezone.utc) < locked_until:
            raise HTTPException(status_code=429, detail="Trop de tentatives. Réessayez dans 15 minutes.")
        await db.login_attempts.delete_one({"identifier": ip})


@api_router.get("/")
async def root():
    return {"message": "RCCM National API"}


@api_router.post("/admin/login")
async def admin_login(body: AdminLogin, request: Request):
    ip = request.client.host if request.client else "unknown"
    await check_lockout(ip)
    if not secrets.compare_digest(body.password, ADMIN_PASSWORD):
        await db.login_attempts.update_one(
            {"identifier": ip},
            {"$inc": {"count": 1}, "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    await db.login_attempts.delete_one({"identifier": ip})
    return {"token": create_admin_token()}


@api_router.get("/admin/me")
async def admin_me(_=Depends(require_admin)):
    return {"role": "admin"}


@api_router.post("/documents", response_model=Document)
async def create_document(
    titre: str = Form(...),
    acteur: str = Form(...),
    rccm: str = Form(...),
    date_immatriculation: str = Form(...),
    ressort: str = Form(...),
    date_impression: str = Form(...),
    numero_procedure: str = Form(...),
    reference: str = Form(...),
    fichier: Optional[UploadFile] = File(None),
    _=Depends(require_admin),
):
    doc_id = str(uuid.uuid4())
    code = secrets.token_urlsafe(8)
    while await db.documents.find_one({"code": code}):
        code = secrets.token_urlsafe(8)

    fichier_nom = fichier_type = None
    if fichier is not None and fichier.filename:
        if fichier.content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="Format de fichier non pris en charge (PDF, PNG, JPG, WEBP)")
        content = await fichier.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 15 Mo)")
        fichier_type = fichier.content_type
        fichier_nom = re.sub(r"[^A-Za-z0-9._-]", "_", fichier.filename)[:120]
        (UPLOAD_DIR / f"{doc_id}{ALLOWED_TYPES[fichier_type]}").write_bytes(content)

    doc = {
        "id": doc_id,
        "code": code,
        "titre": titre.strip(),
        "acteur": acteur.strip(),
        "rccm": rccm.strip(),
        "date_immatriculation": date_immatriculation,
        "ressort": ressort.strip(),
        "date_impression": date_impression,
        "numero_procedure": numero_procedure.strip(),
        "reference": reference.strip(),
        "fichier_nom": fichier_nom,
        "fichier_type": fichier_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(doc)
    return Document(**doc)


@api_router.get("/documents", response_model=List[Document])
async def list_documents(_=Depends(require_admin)):
    docs = await db.documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Document(**d) for d in docs]


@api_router.get("/documents/id/{doc_id}", response_model=Document)
async def get_document_admin(doc_id: str, _=Depends(require_admin)):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return Document(**doc)


@api_router.put("/documents/{doc_id}", response_model=Document)
async def update_document(
    doc_id: str,
    titre: str = Form(...),
    acteur: str = Form(...),
    rccm: str = Form(...),
    date_immatriculation: str = Form(...),
    ressort: str = Form(...),
    date_impression: str = Form(...),
    numero_procedure: str = Form(...),
    reference: str = Form(...),
    fichier: Optional[UploadFile] = File(None),
    _=Depends(require_admin),
):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    update = {
        "titre": titre.strip(), "acteur": acteur.strip(), "rccm": rccm.strip(),
        "date_immatriculation": date_immatriculation, "ressort": ressort.strip(),
        "date_impression": date_impression, "numero_procedure": numero_procedure.strip(),
        "reference": reference.strip(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if fichier is not None and fichier.filename:
        if fichier.content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="Format de fichier non pris en charge (PDF, PNG, JPG, WEBP)")
        content = await fichier.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 15 Mo)")
        if doc.get("fichier_type"):
            old = UPLOAD_DIR / f"{doc_id}{ALLOWED_TYPES[doc['fichier_type']]}"
            if old.exists():
                old.unlink()
        (UPLOAD_DIR / f"{doc_id}{ALLOWED_TYPES[fichier.content_type]}").write_bytes(content)
        update["fichier_type"] = fichier.content_type
        update["fichier_nom"] = re.sub(r"[^A-Za-z0-9._-]", "_", fichier.filename)[:120]
    await db.documents.update_one({"id": doc_id}, {"$set": update})
    return Document(**{**doc, **update})


@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, _=Depends(require_admin)):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    if doc.get("fichier_type"):
        path = UPLOAD_DIR / f"{doc_id}{ALLOWED_TYPES[doc['fichier_type']]}"
        if path.exists():
            path.unlink()
    await db.documents.delete_one({"id": doc_id})
    await db.scans.delete_many({"document_id": doc_id})
    return {"ok": True}


@api_router.get("/documents/verify/{code}", response_model=Document)
async def verify_document(code: str, request: Request, background: BackgroundTasks):
    doc = await db.documents.find_one_and_update(
        {"code": code},
        {"$inc": {"scans": 1}, "$set": {"dernier_scan": datetime.now(timezone.utc).isoformat()}},
        projection={"_id": 0},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    background.add_task(enregistrer_scan, doc["id"], doc["code"], client_ip(request), request.headers.get("user-agent", ""))
    return Document(**doc)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "inconnue"


def est_ip_privee(ip: str) -> bool:
    return ip in ("127.0.0.1", "::1", "inconnue", "testclient") or ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.", "fc", "fd", "fe80"))


def appareil(ua: str) -> str:
    u = ua.lower()
    if "iphone" in u or "ipad" in u:
        return "iPhone / iPad"
    if "android" in u:
        return "Android"
    if "windows" in u:
        return "Windows"
    if "mac os" in u or "macintosh" in u:
        return "Mac"
    if "linux" in u:
        return "Linux"
    return "Inconnu"


async def geolocaliser(ip: str) -> dict:
    if est_ip_privee(ip):
        return {"ville": "Réseau local", "region": None, "pays": None}
    try:
        async with httpx.AsyncClient(timeout=4) as cli:
            r = await cli.get(f"https://ipwho.is/{ip}")
            d = r.json()
        if not d.get("success", True):
            return {"ville": None, "region": None, "pays": None}
        return {"ville": d.get("city"), "region": d.get("region"), "pays": d.get("country")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("geoloc échouée pour %s: %s", ip, exc)
        return {"ville": None, "region": None, "pays": None}


async def enregistrer_scan(doc_id: str, code: str, ip: str, ua: str):
    geo = await geolocaliser(ip)
    await db.scans.insert_one({
        "id": str(uuid.uuid4()), "document_id": doc_id, "code": code, "date": datetime.now(timezone.utc).isoformat(),
        "ip": ip, "appareil": appareil(ua), **geo,
    })


@api_router.get("/documents/{doc_id}/scans")
async def journal_scans(doc_id: str, _=Depends(require_admin)):
    return await db.scans.find({"document_id": doc_id}, {"_id": 0}).sort("date", -1).to_list(500)


@api_router.get("/documents/{code}/fichier")
async def document_file(code: str):
    doc = await db.documents.find_one({"code": code}, {"_id": 0})
    if not doc or not doc.get("fichier_type"):
        raise HTTPException(status_code=404, detail="Aucun fichier associé")
    path = UPLOAD_DIR / f"{doc['id']}{ALLOWED_TYPES[doc['fichier_type']]}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Fichier manquant")
    return FileResponse(path, media_type=doc["fichier_type"], content_disposition_type="inline", filename=doc["fichier_nom"])


# ---------- Entreprises (registre) ----------
def search_filter(q: str, fields: List[str]):
    if not q.strip():
        return {}
    rx = {"$regex": re.escape(q.strip()), "$options": "i"}
    return {"$or": [{f: rx} for f in fields]}


ENT_FIELDS = ["denomination", "rccm", "ressort", "formeLongue", "gerant"]


@api_router.get("/entreprises")
async def list_entreprises(q: str = "", limit: int = 200):
    cur = db.entreprises.find(search_filter(q, ENT_FIELDS), {"_id": 0}).sort("dateImmatriculation", -1)
    return await cur.to_list(min(limit, 500))


@api_router.get("/annonces")
async def list_annonces(q: str = "", limit: int = 100):
    flt = {"annonce": True, **search_filter(q, ENT_FIELDS)}
    cur = db.entreprises.find(flt, {"_id": 0}).sort("dateImmatriculation", -1)
    return await cur.to_list(min(limit, 500))


@api_router.get("/entreprises/{ent_id}")
async def get_entreprise(ent_id: str):
    ent = await db.entreprises.find_one({"id": ent_id}, {"_id": 0})
    if not ent:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    return ent


@api_router.post("/entreprises")
async def create_entreprise(body: EntrepriseIn, _=Depends(require_admin)):
    ent = body.model_dump()
    ent["id"] = new_entreprise_id(ent["ressort"])
    ent["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.entreprises.insert_one(ent)
    ent.pop("_id", None)
    return ent


@api_router.put("/entreprises/{ent_id}")
async def update_entreprise(ent_id: str, body: EntrepriseIn, _=Depends(require_admin)):
    res = await db.entreprises.update_one({"id": ent_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    return await db.entreprises.find_one({"id": ent_id}, {"_id": 0})


@api_router.delete("/entreprises/{ent_id}")
async def delete_entreprise(ent_id: str, _=Depends(require_admin)):
    res = await db.entreprises.delete_one({"id": ent_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    p = STATUTS_DIR / f"{ent_id}.pdf"
    if p.exists():
        p.unlink()
    return {"ok": True}


@api_router.post("/entreprises/{ent_id}/statuts")
async def upload_statuts(ent_id: str, fichier: UploadFile = File(...), _=Depends(require_admin)):
    ent = await db.entreprises.find_one({"id": ent_id}, {"_id": 0})
    if not ent:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    if fichier.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Les statuts doivent être un fichier PDF")
    content = await fichier.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 15 Mo)")
    (STATUTS_DIR / f"{ent_id}.pdf").write_bytes(content)
    nom = re.sub(r"[^A-Za-z0-9._-]", "_", fichier.filename or "statuts.pdf")[:120]
    await db.entreprises.update_one({"id": ent_id}, {"$set": {"statuts_nom": nom, "statuts_date": datetime.now(timezone.utc).isoformat()}})
    return await db.entreprises.find_one({"id": ent_id}, {"_id": 0})


@api_router.delete("/entreprises/{ent_id}/statuts")
async def delete_statuts(ent_id: str, _=Depends(require_admin)):
    p = STATUTS_DIR / f"{ent_id}.pdf"
    if p.exists():
        p.unlink()
    res = await db.entreprises.update_one({"id": ent_id}, {"$unset": {"statuts_nom": "", "statuts_date": ""}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    return await db.entreprises.find_one({"id": ent_id}, {"_id": 0})


@api_router.get("/entreprises/{ent_id}/statuts")
async def get_statuts(ent_id: str):
    ent = await db.entreprises.find_one({"id": ent_id}, {"_id": 0})
    p = STATUTS_DIR / f"{ent_id}.pdf"
    if not ent or not ent.get("statuts_nom") or not p.exists():
        raise HTTPException(status_code=404, detail="Statuts non disponibles")
    return FileResponse(p, media_type="application/pdf", content_disposition_type="inline", filename=ent["statuts_nom"])


# ---------- Dossiers (suivi) ----------
@api_router.get("/dossiers/recherche")
async def rechercher_dossiers(mode: str = "numero", q: str = ""):
    if not q.strip():
        return []
    rx = {"$regex": re.escape(q.strip()), "$options": "i"}
    field = {"numero": "numero", "denomination": "denomination", "dirigeant": "dirigeant"}.get(mode, "numero")
    return await db.dossiers.find({field: rx}, {"_id": 0}).sort("created_at", -1).to_list(20)


@api_router.get("/dossiers")
async def list_dossiers(_=Depends(require_admin)):
    return await db.dossiers.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api_router.post("/dossiers")
async def create_dossier(body: DossierIn, _=Depends(require_admin)):
    if await db.dossiers.find_one({"numero": body.numero}):
        raise HTTPException(status_code=400, detail="Ce numéro de dossier existe déjà")
    d = body.model_dump()
    d["id"] = str(uuid.uuid4())
    d["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.dossiers.insert_one(d)
    d.pop("_id", None)
    return d


@api_router.put("/dossiers/{dossier_id}")
async def update_dossier(dossier_id: str, body: DossierIn, _=Depends(require_admin)):
    res = await db.dossiers.update_one({"id": dossier_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    return await db.dossiers.find_one({"id": dossier_id}, {"_id": 0})


@api_router.delete("/dossiers/{dossier_id}")
async def delete_dossier(dossier_id: str, _=Depends(require_admin)):
    res = await db.dossiers.delete_one({"id": dossier_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    return {"ok": True}


# ---------- Statistiques (calculées) ----------
MOIS_COURT = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"]
TYPES = ["Société commerciale", "Personne physique", "Groupement (GIE)", "Entreprenant"]
TYPE_LABELS = {"Société commerciale": "Sociétés commerciales", "Personne physique": "Personnes physiques",
               "Groupement (GIE)": "Groupements (GIE)", "Entreprenant": "Entreprenants"}


def pct(n, total):
    return round(n * 100 / total) if total else 0


@api_router.get("/stats")
async def stats():
    ents = await db.entreprises.find({}, {"_id": 0, "type": 1, "forme": 1, "genre": 1, "ressort": 1, "dateImmatriculation": 1}).to_list(100000)
    today = datetime.now(timezone.utc).date()
    limite = (today - timedelta(days=30)).isoformat()
    an = (today - timedelta(days=365)).isoformat()
    deux_ans = (today - timedelta(days=730)).isoformat()

    globales = []
    for t in TYPES:
        sub = [e for e in ents if e.get("type") == t]
        recent = sum(1 for e in sub if e.get("dateImmatriculation", "") >= limite)
        base = len(sub) - recent
        d = pct(recent, base) if base else (100 if recent else 0)
        globales.append({"label": TYPE_LABELS[t], "valeur": f"{len(sub):,}".replace(",", " "), "delta": f"{'+' if d >= 0 else ''}{d} %", "tendance": "up" if d > 0 else ("flat" if d == 0 else "down")})

    formes_count = {}
    for e in ents:
        formes_count[e.get("forme", "Autre")] = formes_count.get(e.get("forme", "Autre"), 0) + 1
    formes = sorted(({"forme": k, "part": pct(v, len(ents))} for k, v in formes_count.items()), key=lambda x: -x["part"])

    phys = [e for e in ents if e.get("genre") in ("Homme", "Femme")]
    h = sum(1 for e in phys if e.get("genre") == "Homme")
    f = sum(1 for e in phys if e.get("genre") == "Femme")
    genre = [{"label": "Hommes", "part": pct(h, h + f), "n": h}, {"label": "Femmes", "part": pct(f, h + f), "n": f}]

    ant = {}
    for e in ents:
        ant[e.get("ressort", "—")] = ant.get(e.get("ressort", "—"), 0) + 1
    antennes = sorted(({"antenne": k, "valeur": v} for k, v in ant.items()), key=lambda x: -x["valeur"])[:8]

    tendance = []
    y, m = today.year, today.month
    for i in range(11, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        key = f"{yy:04d}-{mm:02d}"
        tendance.append({"mois": f"{MOIS_COURT[mm - 1]} {str(yy)[2:]}", "valeur": sum(1 for e in ents if e.get("dateImmatriculation", "").startswith(key))})

    n_an = sum(1 for e in ents if e.get("dateImmatriculation", "") >= an)
    n_prec = sum(1 for e in ents if deux_ans <= e.get("dateImmatriculation", "") < an)
    croissance = pct(n_an - n_prec, n_prec) if n_prec else (100 if n_an else 0)

    return {"total": len(ents), "globales": globales, "formes": formes, "genre": genre, "antennes": antennes,
            "tendance": tendance, "croissance": croissance, "n_an": n_an}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.documents.create_index("code", unique=True)
    await db.documents.create_index("id", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.entreprises.create_index("id", unique=True)
    await db.dossiers.create_index("id", unique=True)
    await db.scans.create_index([("document_id", 1), ("date", -1)])
    if await db.entreprises.count_documents({}) == 0:
        await db.entreprises.insert_many(entreprises_seed())
    if await db.dossiers.count_documents({}) == 0:
        await db.dossiers.insert_many(dossiers_seed())


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
