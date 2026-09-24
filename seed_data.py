import random
import uuid
from datetime import datetime, timezone

MOIS = {"janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12}


def fr_to_iso(s: str) -> str:
    j, m, a = s.split(" ")
    return f"{int(a):04d}-{MOIS[m.lower()]:02d}-{int(j):02d}"


ETAPES = [
    ("Déposé", "Dossier reçu par le Guichet Unique de Création d'Entreprise."),
    ("Contrôle", "Pièces justificatives vérifiées et déclarées conformes."),
    ("En traitement", "Immatriculation en cours d'examen au greffe du tribunal de commerce."),
    ("Clôturé", "Délivrance du numéro RCCM et notification par e-mail."),
]

_E = [
    ("ent.lsh.act.560118", "VIE NOUVELLE TK", "SARL", "Société à responsabilité limitée unipersonnelle (SARL)", "CD/LSH/RCCM/26-B-02738", "24 septembre 2026", "Lubumbashi", "14, avenue Kasa-Vubu, Lubumbashi", "Commerce général, import-export et prestations de services", "10 000 000 CDF", "99 ans", "Tshiala Kabongo Vie", "Actif", "Société commerciale", "Femme", True),
    ("ent.lsh.act.560116", "VICTOIRE LOGISTIQUE", "SARL", "Société à responsabilité limitée unipersonnelle (SARL)", "CD/LSH/RCCM/26-B-02727", "24 septembre 2026", "Lubumbashi", "780, avenue Mobutu, Lubumbashi", "Transport, transit et logistique", "25 000 000 CDF", "99 ans", "Mwanza Ilunga Patrick", "Actif", "Société commerciale", "Homme", True),
    ("ent.lsh.act.560117", "SOCIETE MODERN TRADING", "SARL", "Société à responsabilité limitée pluripersonnelle (SARL)", "CD/LSH/RCCM/26-B-02732", "24 septembre 2026", "Lubumbashi", "3, avenue Lumumba, Lubumbashi", "Négoce de produits manufacturés", "50 000 000 CDF", "99 ans", "Kabeya Ntumba Grâce", "Actif", "Société commerciale", "Femme", True),
    ("ent.knm.act.527056", "SARHEB", "SARL", "Société à responsabilité limitée pluripersonnelle (SARL)", "CD/KNM/RCCM/26-B-02782", "22 septembre 2026", "Kisangani", "27, avenue de la Tshopo, Kisangani", "BTP, travaux publics et fournitures", "40 000 000 CDF", "99 ans", "Botuli Saramba Hervé", "Actif", "Société commerciale", "Homme", True),
    ("ent.kng.act.559672", "CONGO TRADE SOLUTIONS", "SARL", "Société à responsabilité limitée pluripersonnelle (SARL)", "CD/KNG/RCCM/26-B-03844", "22 septembre 2026", "Kinshasa", "12, boulevard du 30 Juin, Kinshasa/Gombe", "Conseil, représentation commerciale et courtage", "30 000 000 CDF", "99 ans", "Mbuyi Kalonji Sarah", "Actif", "Société commerciale", "Femme", True),
    ("ent.kng.act.559671", "ASILI COMM", "SAS", "Société par actions simplifiée pluripersonnelle (SAS)", "CD/KNG/RCCM/26-B-03839", "22 septembre 2026", "Kinshasa", "88, avenue de la Justice, Kinshasa/Gombe", "Communication, marketing digital et production audiovisuelle", "15 000 000 CDF", "99 ans", "Lokwa Asili Divine", "Actif", "Société commerciale", "Femme", True),
    ("ent.gom.act.553201", "KIVU AGRO BUSINESS", "SARL", "Société à responsabilité limitée pluripersonnelle (SARL)", "CD/GOM/RCCM/26-B-01190", "19 septembre 2026", "Goma", "45, avenue du Lac, Goma", "Production agricole, transformation et distribution", "60 000 000 CDF", "99 ans", "Bishoge Muhindo Jean", "Actif", "Société commerciale", "Homme", True),
    ("ent.mba.act.540877", "EQUATEUR PÊCHE", "GIE", "Groupement d'intérêt économique (GIE)", "CD/MBA/RCCM/26-C-00042", "18 septembre 2026", "Mbandaka", "9, avenue du Fleuve, Mbandaka", "Pêche, pisciculture et commercialisation", "5 000 000 CDF", "30 ans", "Ekofa Bongonda Moïse", "Actif", "Groupement (GIE)", "Homme", True),
    ("ent.kan.act.538902", "LULUA BTP", "SARL", "Société à responsabilité limitée unipersonnelle (SARL)", "CD/KAN/RCCM/26-B-00315", "16 septembre 2026", "Kananga", "31, avenue Luiza, Kananga", "Construction et réhabilitation de bâtiments", "20 000 000 CDF", "99 ans", "Tshibangu Mukendi Alain", "Actif", "Société commerciale", "Homme", True),
    ("ent.kin.act.552344", "MAENDELEO DIGITAL", "SAS", "Société par actions simplifiée unipersonnelle (SAS)", "CD/KIN/RCCM/26-B-05102", "15 septembre 2026", "Kinshasa", "6, avenue Wagenia, Kinshasa/Lingwala", "Développement logiciel et services numériques", "8 000 000 CDF", "99 ans", "Nzuzi Makiesse Gloria", "Actif", "Société commerciale", "Femme", True),
    ("ent.kng.act.410017", "TSHILOMBO & FILS", "SARL", "Société à responsabilité limitée pluripersonnelle (SARL)", "CD/KNG/RCCM/24-B-00017", "8 janvier 2024", "Kinshasa", "102, avenue du Commerce, Kinshasa/Gombe", "Commerce général", "100 000 000 CDF", "99 ans", "Tshilombo Kabasele Martin", "Actif", "Société commerciale", "Homme", False),
    ("ent.kin.act.210452", "MOKILI MARKET", "Ets", "Établissement (personne physique)", "CD/KIN/RCCM/21-A-10452", "3 mars 2021", "Kinshasa", "Marché Central, Kinshasa", "Vente de denrées alimentaires", "—", "—", "Mokili Nsimba Jeanette", "Actif", "Personne physique", "Femme", False),
    ("ent.ken.act.190231", "CONGO BRASSERIE DU KWANGO", "SA", "Société anonyme (SA)", "CD/KEN/RCCM/19-B-00231", "17 juin 2019", "Kenge", "1, avenue de l'Industrie, Kenge", "Brasserie et distribution de boissons", "500 000 000 CDF", "99 ans", "—", "Radié", "Société commerciale", "—", False),
    ("ent.kis.act.220877", "EBALE TRANSPORT", "SARL", "Société à responsabilité limitée pluripersonnelle (SARL)", "CD/KIS/RCCM/22-B-00877", "22 novembre 2022", "Kisangani", "4, avenue Mobutu, Kisangani", "Transport fluvial et terrestre", "35 000 000 CDF", "99 ans", "Likulia Asani Prosper", "Actif", "Société commerciale", "Homme", False),
    ("ent.lsh.act.230412", "HAUT-KATANGA MINES SERVICES", "SARL", "Société à responsabilité limitée pluripersonnelle (SARL)", "CD/LSH/RCCM/23-B-01412", "5 mai 2023", "Lubumbashi", "210, avenue Kipushi, Lubumbashi", "Sous-traitance minière", "80 000 000 CDF", "99 ans", "Ilunga Kazadi Dieudonné", "Actif", "Société commerciale", "Homme", False),
    ("ent.bkv.act.250930", "MAMA FURAHA ENTREPRENANT", "Entr.", "Entreprenant", "CD/BKV/RCCM/25-E-00930", "11 février 2025", "Bukavu", "Marché de Kadutu, Bukavu", "Petit commerce", "—", "—", "Furaha Nabintu", "Actif", "Entreprenant", "Femme", False),
]

KEYS = ["id", "denomination", "forme", "formeLongue", "rccm", "dateImmatriculation", "ressort", "siege", "objet",
        "capital", "duree", "gerant", "statut", "type", "genre", "annonce"]


def entreprises_seed():
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for row in _E:
        d = dict(zip(KEYS, row))
        d["dateImmatriculation"] = fr_to_iso(d["dateImmatriculation"])
        d["created_at"] = now
        out.append(d)
    return out


def _dossier(numero, denomination, forme, ressort, dirigeant, etape_courante, cloture, dates):
    return {
        "id": str(uuid.uuid4()),
        "numero": numero,
        "denomination": denomination,
        "forme": forme,
        "ressort": ressort,
        "dirigeant": dirigeant,
        "etape_courante": etape_courante,
        "cloture": cloture,
        "etapes": [{"label": l, "detail": det, "date": dates[i]} for i, (l, det) in enumerate(ETAPES)],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def dossiers_seed():
    return [
        _dossier("GUCE-2026-045821", "KIVU AGRO BUSINESS", "SARL", "Goma", "Bishoge Muhindo Jean", 2, False,
                 ["2026-09-12", "2026-09-14", "2026-09-18", None]),
        _dossier("GUCE-2026-044102", "MAENDELEO DIGITAL", "SAS", "Kinshasa", "Nzuzi Makiesse Gloria", 3, True,
                 ["2026-09-08", "2026-09-09", "2026-09-11", "2026-09-15"]),
        _dossier("GUCE-2026-046310", "SARHEB", "SARL", "Kisangani", "Botuli Saramba Hervé", 0, False,
                 ["2026-09-20", None, None, None]),
    ]


def new_entreprise_id(ressort: str) -> str:
    code = "".join(c for c in ressort.lower() if c.isalpha())[:3] or "rdc"
    return f"ent.{code}.act.{random.randint(100000, 999999)}"
