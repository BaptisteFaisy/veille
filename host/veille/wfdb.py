"""Lecteur WFDB minimal — stdlib uniquement (formats 212 et 16).

Lit les enregistrements PhysioNet réels de ``data/records/`` :

- en-tête ``.hea`` : ligne de record, puis une ligne par signal, puis
  commentaires ``#`` ;
- données ``.dat`` entrelacées : format **212** (deux valeurs 12 bits par
  groupe de 3 octets, little-endian, complément à deux) et format **16**
  (int16 little-endian) ;
- CSV numériques BIDMC (SpO2, HR, …) horodatés en secondes.

Conversion physique WFDB : ``brut = physique * gain + baseline``, donc
``physique = (brut - baseline) / gain``. ``baseline`` est la valeur entre
parenthèses du champ gain si elle est présente, sinon ``adc_zero``.
Décodage vérifié sur données réelles : mitdb/100 (init 995/1011, checksums
-22131/20052 sur 650 000 échantillons) et bidmc01 (5 signaux, checksums
conformes). Voir ``docs/REAL-DATA.md``.

Aucune dépendance : ni numpy, ni le paquet ``wfdb``.
"""
import os
import struct

FORMAT_212 = 212
FORMAT_16 = 16
FORMATS_SUPPORTES = (FORMAT_212, FORMAT_16)


class Signal:
    """Spécification d'un signal telle que décrite dans l'en-tête WFDB."""

    __slots__ = ("fichier", "nom", "format", "gain", "baseline", "adc_res",
                 "adc_zero", "init", "checksum", "block_size", "unites")

    def __init__(self, fichier, nom, format, gain, baseline, adc_res, adc_zero,
                 init, checksum, block_size, unites):
        self.fichier = fichier
        self.nom = nom
        self.format = format
        self.gain = gain
        self.baseline = baseline
        self.adc_res = adc_res
        self.adc_zero = adc_zero
        self.init = init
        self.checksum = checksum
        self.block_size = block_size
        self.unites = unites

    def physique(self, brut):
        """Valeur physique d'un entier brut (gain nul → brut en flottant)."""
        if not self.gain:
            return float(brut)
        return (brut - self.baseline) / self.gain

    def __repr__(self):
        return "<Signal %s fmt=%d gain=%g baseline=%g %s>" % (
            self.nom, self.format, self.gain, self.baseline, self.unites)


class EnTete:
    """En-tête WFDB complet : record + liste de signaux + commentaires."""

    __slots__ = ("nom", "nb_signaux", "fs", "nb_echantillons", "base_time",
                 "base_date", "signaux", "commentaires", "chemin")

    def __init__(self, nom, nb_signaux, fs, nb_echantillons, signaux,
                 base_time="", base_date="", commentaires=(), chemin=""):
        self.nom = nom
        self.nb_signaux = nb_signaux
        self.fs = fs
        self.nb_echantillons = nb_echantillons
        self.signaux = list(signaux)
        self.base_time = base_time
        self.base_date = base_date
        self.commentaires = list(commentaires)
        self.chemin = chemin

    def duree_s(self):
        """Durée de l'enregistrement en secondes (fs nul → 0.0)."""
        return self.nb_echantillons / self.fs if self.fs else 0.0

    def signal(self, nom):
        """Retrouve un signal par son nom (insensible à la casse)."""
        cherche = nom.strip().lower()
        for s in self.signaux:
            if s.nom.strip().lower() == cherche:
                return s
        return None

    def noms(self):
        return [s.nom for s in self.signaux]

    def __repr__(self):
        return "<EnTete %s %d signaux fs=%g n=%d>" % (
            self.nom, self.nb_signaux, self.fs, self.nb_echantillons)


class SignalLu:
    """Signal décodé : entiers bruts puis valeurs physiques."""

    __slots__ = ("signal", "bruts", "physiques", "fs")

    def __init__(self, signal, bruts, fs):
        self.signal = signal
        self.bruts = bruts
        self.fs = fs
        self.physiques = [signal.physique(v) for v in bruts]

    def __len__(self):
        return len(self.bruts)

    def __repr__(self):
        return "<SignalLu %s n=%d>" % (self.signal.nom, len(self.bruts))


def _decoupe_gain(champ):
    """Analyse un champ gain WFDB : ``200``, ``-8300/mV``, ``65534(-32767)/pm``.

    Retourne ``(gain, baseline_ou_None, unités)``.
    """
    reste = champ.strip()
    unites = ""
    if "/" in reste:
        reste, unites = reste.split("/", 1)
    baseline = None
    if "(" in reste and reste.endswith(")"):
        reste, paren = reste.split("(", 1)
        baseline = int(paren[:-1])
    return float(reste), baseline, unites.strip()


def _decoupe_format(champ):
    """Analyse un champ format (``212``, ``16``, ``212:1``, ``16+8``)."""
    detail = ""
    for sep in (":", "+"):
        if sep in champ:
            champ, detail = champ.split(sep, 1)
            break
    return int(champ), detail


def _entier(champ):
    """True si le champ est un entier relatif lisible."""
    try:
        int(champ)
        return True
    except ValueError:
        return False


def _analyser_ligne_record(champs):
    """Ligne de record : ``nom nb_signaux fs [nb_éch [heure date]]``.

    ``fs`` peut porter une fréquence de compteur (``250/0.033333333(216)``) :
    seule la fréquence d'échantillonnage (avant le ``/``) est retenue.
    """
    nom = champs[0]
    nb_signaux = int(champs[1])
    fs = float(champs[2].split("/")[0])
    nb_ech = int(champs[3]) if len(champs) > 3 and _entier(champs[3]) else 0
    base_time = champs[4] if len(champs) > 4 else ""
    base_date = champs[5] if len(champs) > 5 else ""
    return nom, nb_signaux, fs, nb_ech, base_time, base_date


def _analyser_ligne_signal(champs):
    """Ligne signal WFDB :
    ``fichier format gain adc_res adc_zero init checksum block description…``.

    Ordre réel des champs (vérifié sur mitdb/100 : gain 200 ADU/mV, adc_res 11
    bits, adc_zero 1024). La description peut contenir des espaces.
    """
    if len(champs) < 8:
        raise ValueError("ligne de signal trop courte : %r" % (" ".join(champs),))
    fichier = champs[0]
    fmt, _detail = _decoupe_format(champs[1])
    if fmt not in FORMATS_SUPPORTES:
        raise ValueError("format %d non supporté (attendu 212 ou 16) : %s"
                         % (fmt, fichier))
    gain, baseline, unites = _decoupe_gain(champs[2])
    adc_res = int(champs[3])
    adc_zero = int(champs[4])
    init = int(champs[5])
    checksum = int(champs[6])
    block_size = int(champs[7])
    nom = " ".join(champs[8:]).strip().rstrip(",").strip()
    return Signal(fichier, nom, fmt, gain, adc_zero if baseline is None else baseline,
                  adc_res, adc_zero, init, checksum, block_size, unites)


def lire_en_tete(chemin_sans_extension):
    """Lit un en-tête WFDB et retourne un :class:`EnTete`.

    ``chemin_sans_extension`` accepte aussi un chemin se terminant par ``.hea``.
    """
    chemin = chemin_sans_extension
    if chemin.endswith(".hea"):
        chemin = chemin[:-4]
    with open(chemin + ".hea", "r", encoding="utf-8") as f:
        lignes = f.read().splitlines()
    record, signaux, commentaires = None, [], []
    for ligne in lignes:
        nette = ligne.strip()
        if not nette:
            continue
        if nette.startswith("#"):
            commentaires.append(nette[1:].strip())
            continue
        champs = nette.split()
        if record is None:
            record = champs
        else:
            signaux.append(_analyser_ligne_signal(champs))
    if record is None:
        raise ValueError("en-tête WFDB vide : %s.hea" % chemin)
    nom, nb, fs, nb_ech, base_time, base_date = _analyser_ligne_record(record)
    if len(signaux) != nb:
        raise ValueError("%s : %d signaux annoncés, %d lignes lues"
                         % (nom, nb, len(signaux)))
    return EnTete(nom, nb, fs, nb_ech, signaux, base_time, base_date,
                  commentaires, chemin)


def decoder_212(tampon):
    """Décode un format 212 : deux valeurs 12 bits par groupe de 3 octets.

    Petit boutisme, complément à deux sur 12 bits (≥ 2048 → valeur négative).
    Un tampon tronqué (reste ≠ multiple de 3) ignore les octets finaux.
    """
    valeurs = []
    for i in range(0, len(tampon) - len(tampon) % 3, 3):
        b0, b1, b2 = tampon[i], tampon[i + 1], tampon[i + 2]
        v1 = b0 | ((b1 & 0x0F) << 8)
        v2 = b2 | ((b1 & 0xF0) << 4)
        valeurs.append(v1 - 4096 if v1 >= 2048 else v1)
        valeurs.append(v2 - 4096 if v2 >= 2048 else v2)
    return valeurs


def decoder_16(tampon):
    """Décode un format 16 : int16 little-endian (octet final impair ignoré)."""
    n = len(tampon) // 2
    return list(struct.unpack("<%dh" % n, tampon[:2 * n])) if n else []


def octets_par_trame(fmt, nb_signaux):
    """Nombre d'octets d'une trame (un instant, tous les signaux entrelacés)."""
    if fmt == FORMAT_16:
        return 2 * nb_signaux
    if nb_signaux % 2:
        raise ValueError("format 212 avec %d signaux (impair) : non supporté"
                         % nb_signaux)
    return 3 * nb_signaux // 2


def lire_bruts(entete, nom_signal, limite=None):
    """Entiers bruts désentrelacés d'un signal, à partir d'un en-tête déjà lu.

    ``limite`` borne le nombre d'échantillons lus (None → tout
    l'enregistrement) ; seul le prefixe utile du ``.dat`` est alors chargé.
    """
    indice = None
    for i, s in enumerate(entete.signaux):
        if s.nom.strip().lower() == nom_signal.strip().lower():
            indice = i
            break
    if indice is None:
        raise KeyError("signal %r absent de %s (disponibles : %s)"
                       % (nom_signal, entete.nom, ", ".join(entete.noms())))
    sig = entete.signaux[indice]
    trames = entete.nb_echantillons if limite is None else max(0, min(
        limite, entete.nb_echantillons or limite))
    chemin_dat = os.path.join(os.path.dirname(entete.chemin), sig.fichier)
    with open(chemin_dat, "rb") as f:
        tampon = f.read(trames * octets_par_trame(sig.format, entete.nb_signaux))
    plat = decoder_212(tampon) if sig.format == FORMAT_212 else decoder_16(tampon)
    return plat[indice::entete.nb_signaux]


def lire_signal(chemin, nom_signal, limite=None):
    """Lit un signal réel : entiers bruts puis valeurs physiques.

    Retourne un :class:`SignalLu` (``.bruts``, ``.physiques``, ``.fs``).
    """
    entete = lire_en_tete(chemin)
    bruts = lire_bruts(entete, nom_signal, limite)
    return SignalLu(entete.signal(nom_signal), bruts, entete.fs)


def somme_16_signee(valeurs):
    """Checksum WFDB : somme 16 bits des bruts, rendue signée.

    Sert à vérifier un décodage complet contre le champ ``checksum`` de
    l'en-tête (contrôle d'intégrité indépendant du contenu).
    """
    s = sum(valeurs) & 0xFFFF
    return s - 65536 if s >= 32768 else s


class Numeriques:
    """Séries numériques BIDMC horodatées (une ligne par seconde)."""

    __slots__ = ("temps", "colonnes", "chemin")

    def __init__(self, temps, colonnes, chemin=""):
        self.temps = temps
        self.colonnes = colonnes
        self.chemin = chemin

    def __len__(self):
        return len(self.temps)

    def cles(self):
        return list(self.colonnes)

    def serie(self, nom):
        """Retourne la colonne ``nom`` (insensible à la casse et aux espaces)."""
        cherche = nom.strip().lower()
        for cle, valeurs in self.colonnes.items():
            if cle.strip().lower() == cherche:
                return valeurs
        raise KeyError("colonne %r absente (disponibles : %s)"
                       % (nom, ", ".join(self.cles())))


def _nombre(champ):
    """Convertit un champ CSV en int, float ou None.

    ``None`` marque une valeur manquante : case vide ou ``NaN`` (le CSV
    numérique BIDMC publie réellement des ``NaN`` pour SpO2/PULSE quand le
    moniteur ne rapportait pas la valeur à cette seconde).
    """
    champ = champ.strip()
    if not champ or champ.lower() == "nan":
        return None
    try:
        return int(champ)
    except ValueError:
        pass
    try:
        return float(champ)
    except ValueError:
        return None


def lire_numeriques_bidmc(chemin_csv):
    """Lit un CSV ``*_Numerics.csv`` BIDMC → :class:`Numeriques`.

    Colonnes réelles de ``bidmc_01_Numerics.csv`` : ``Time [s], HR, PULSE,
    RESP, SpO2`` (une ligne par seconde, valeurs entières réelles relevées au
    lit du patient).
    """
    with open(chemin_csv, "r", encoding="utf-8") as f:
        lignes = f.read().splitlines()
    if not lignes:
        raise ValueError("CSV BIDMC vide : %s" % chemin_csv)
    entetes = [c.strip() for c in lignes[0].split(",")]
    if len(entetes) < 2:
        raise ValueError("en-tête CSV BIDMC invalide : %r" % lignes[0])
    temps = []
    colonnes = {cle: [] for cle in entetes[1:]}
    for ligne in lignes[1:]:
        if not ligne.strip():
            continue
        champs = [c.strip() for c in ligne.split(",")]
        temps.append(_nombre(champs[0]) or 0)
        for cle, valeur in zip(entetes[1:], champs[1:]):
            colonnes[cle].append(_nombre(valeur))
    return Numeriques(temps, colonnes, chemin_csv)


def sha256_fichier(chemin):
    """Empreinte SHA-256 hexadécimale d'un fichier (par blocs de 1 Mio)."""
    import hashlib
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()
