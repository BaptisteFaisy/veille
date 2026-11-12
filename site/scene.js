/* Veille — scène « Rejeu réel » (site/scene.js).
 *
 * Anime un extrait dérivé de données réelles (window.VEILLE_REEL, produit par
 * tools/genere-scene.py) : le signal ECG défile, la cadence bpm traverse le
 * seuil d'alarme (120 bpm, filtre 8), la décision est rendue avec son code de
 * verdict, et la latence mesurée (chaîne C réelle) est affichée face à la
 * borne prouvée (200 ms). Aucune dépendance : un seul canvas à la fois dessiné
 * en boucle requestAnimationFrame, zéro CDN, zéro fetch.
 */
(function () {
  "use strict";
  var D = window.VEILLE_REEL;
  var VIS_S = 6;                 // durée ECG visible (secondes)
  var BPM_HAUT = 200;            // plage verticale du tracé bpm
  var COUL = { grille: "#2a3040", courbe: "#7fd1c1", brut: "#9aa3b2",
               seuil: "#e58fb0", curseur: "#7fd1c1", alarme: "#e58fb0",
               tech: "#f0c674" };

  var DECISION = {
    OK:     { label: "Sous le seuil", cls: "ok", verdict: "VEILLE_OK",
              desc: "échantillon traité — seuil non franchi" },
    ALARME: { label: "Alarme haute — seuil franchi", cls: "alarme",
              verdict: "VEILLE_OK",
              desc: "alarme haute priorité · latence pire cas ≤ borne 200 ms" },
    STUCK:  { label: "Alarme technique — capteur figé", cls: "tech",
              verdict: "VEILLE_TECHNICAL_ALARM",
              desc: "deux bpm consécutifs identiques (faux positif en FA, cf. limites)" },
    DEAD:   { label: "Alarme technique — capteur mort", cls: "tech",
              verdict: "VEILLE_TECHNICAL_ALARM", desc: "capteur mort" }
  };

  function byId(id) { return document.getElementById(id); }
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }

  // Paramètre d'URL : ?t=12.5 (seconde dans l'épisode) et ?pause=1.
  function param(nom) {
    var m = new RegExp("[?&]" + nom + "=([^&]*)").exec(window.location.search);
    return m ? decodeURIComponent(m[1]) : null;
  }

  // ---------- état de lecture ----------
  var tNow = D.source.t0, duree = D.source.duree, t0 = D.source.t0;
  // ecg[j] = échantillon au temps tEcg0 + j/fs (le pré-roll precede t0)
  var tEcg0 = D.source.ecg_t0 !== undefined ? D.source.ecg_t0 : t0;
  var playing = true, speed = 1, last = null;
  var fs = D.ecg_fs, ecg = D.ecg, beats = D.beats, anns = D.annotations;
  var seuil = D.chaine.seuil_bpm, borne = D.chaine.borne_alarme_ms;
  var latMax = D.latence_us_max;

  // plage verticale ECG stable (calculée une fois sur toute la fenêtre)
  var yMin = Math.min.apply(null, ecg), yMax = Math.max.apply(null, ecg);
  var marge = (yMax - yMin) * 0.08 || 1;
  yMin -= marge; yMax += marge;

  var ecgC = byId("scene-ecg"), bpmC = byId("scene-bpm");

  function taille(c) {
    var dpr = window.devicePixelRatio || 1;
    var rect = c.getBoundingClientRect();
    var w = Math.max(320, rect.width);
    c.width = w * dpr; c.height = c.dataset.h * dpr;
    var ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: +c.dataset.h };
  }

  // ---------- décision / latence ----------
  function courant() {
    var b = null;
    for (var i = 0; i < beats.length; i++) {
      if (beats[i].t <= tNow) b = beats[i]; else break;
    }
    return b;
  }

  function majPanels() {
    var b = courant();
    if (!b) return;
    var d = DECISION[b.decision] || DECISION.OK;
    var pan = byId("scene-decision");
    pan.className = "panel " + d.cls;
    byId("scene-decision-valeur").textContent = d.label;
    byId("scene-decision-valeur").className = "valeur etat " + d.cls;
    byId("scene-decision-verdict").textContent =
      "code " + d.verdict + " — " + d.desc;
    byId("scene-decision-seuil").textContent =
      "seuil " + seuil + " bpm · bpm lu " + b.bpm + " · filtré " + b.filtre;

    var f = (latMax / 1000) / borne;   // fraction de la borne utilisée (ms)
    var lat_ms = latMax / 1000;
    byId("scene-lat-mesuree").textContent =
      "latence mesurée (hôte) : max " + (latMax < 1 ? "< 1 µs" : latMax + " µs") +
      " (" + lat_ms.toFixed(3) + " ms)";
    byId("scene-lat-borne").textContent =
      "borne prouvée : " + borne + " ms — marge ≈ " +
      Math.max(0, borne - lat_ms).toFixed(3) + " ms";
    byId("scene-lat-fill").style.width = clamp(f * 100, 0.6, 100) + "%";
  }

  function majHoro() {
    byId("scene-horo").textContent =
      "t = " + (tNow - t0).toFixed(2) + " s / " + duree.toFixed(1) + " s";
  }

  // ---------- dessin ECG (bande défilante, VIS_S dernières secondes) ----------
  function dessineEcg(S) {
    var g = S.ctx, w = S.w, h = S.h;
    g.clearRect(0, 0, w, h);
    // au démarrage, la bande se remplit depuis le début de la fenêtre
    var tDebut = Math.max(tEcg0, tNow - VIS_S);
    // grille : verticales toutes les 1 s, horizontales toutes les 500 µV
    g.strokeStyle = COUL.grille; g.lineWidth = 1; g.beginPath();
    for (var tt = Math.ceil(tDebut); tt <= tNow; tt++) {
      var gx = (tt - tDebut) / VIS_S * w;
      g.moveTo(gx, 0); g.lineTo(gx, h);
    }
    for (var u = Math.ceil(yMin / 500) * 500; u <= yMax; u += 500) {
      var gy = h - (u - yMin) / (yMax - yMin) * h;
      g.moveTo(0, gy); g.lineTo(w, gy);
    }
    g.stroke();

    // ecg[j] = échantillon au temps tEcg0 + j/fs (index relatif à la fenêtre)
    var j0 = Math.max(0, Math.floor((tDebut - tEcg0) * fs));
    var j1 = Math.min(ecg.length - 1, Math.ceil((tNow - tEcg0) * fs));
    var xOf = function (j) { return (tEcg0 + j / fs - tDebut) / VIS_S * w; };
    var yOf = function (v) { return h - (v - yMin) / (yMax - yMin) * h; };

    g.strokeStyle = COUL.courbe; g.lineWidth = 1.4; g.lineJoin = "round";
    g.beginPath();
    for (var j = j0; j <= j1; j++) {
      var x = xOf(j), y = yOf(ecg[j]);
      if (j === j0) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.stroke();

    // annotation franchies → étiquette discrète en haut du tracé
    g.fillStyle = COUL.seuil; g.font = "11px ui-monospace, Menlo, monospace";
    for (var k = 0; k < anns.length; k++) {
      var a = anns[k];
      if (a.t > tDebut && a.t <= tNow) {
        g.fillText("(" + a.libelle, xOf((a.t - tEcg0) * fs) + 3, 12);
      }
    }
    // curseur « maintenant » à droite
    g.strokeStyle = COUL.curseur; g.beginPath();
    g.moveTo(w - 1, 0); g.lineTo(w - 1, h); g.stroke();
  }

  // ---------- dessin bpm (timeline complète sur la fenêtre) ----------
  function dessineBpm(S) {
    var g = S.ctx, w = S.w, h = S.h;
    g.clearRect(0, 0, w, h);
    var xOf = function (t) { return (t - t0) / duree * w; };
    var yOf = function (b) { return h - (b / BPM_HAUT) * h; };

    // grille horizontale (palier 50 bpm) + seuil
    g.strokeStyle = COUL.grille; g.lineWidth = 1; g.beginPath();
    for (var b = 0; b <= BPM_HAUT; b += 50) {
      var gy = yOf(b); g.moveTo(0, gy); g.lineTo(w, gy);
    }
    g.stroke();
    g.strokeStyle = COUL.seuil; g.lineWidth = 1.4; g.setLineDash([5, 4]);
    g.beginPath(); g.moveTo(0, yOf(seuil)); g.lineTo(w, yOf(seuil)); g.stroke();
    g.setLineDash([]);
    g.fillStyle = COUL.seuil;
    g.font = "11px ui-monospace, Menlo, monospace";
    g.fillText("seuil " + seuil + " bpm", 4, yOf(seuil) - 4);

    // zones d'alarme (filtre > seuil) en fond — sur la fenêtre rejouée
    for (var i = 0; i < beats.length; i++) {
      if (beats[i].t < t0) continue;
      if (beats[i].filtre > seuil) {
        var xg = xOf(beats[i].t);
        var xd = i + 1 < beats.length ? xOf(beats[i + 1].t) : xg + 6;
        g.fillStyle = "rgba(229,143,176,0.12)";
        g.fillRect(xg, 0, clamp(xd - xg, 3, 60), h);
      }
    }

    // tracé filtré (accent) + points bruts
    g.strokeStyle = COUL.courbe; g.lineWidth = 1.6; g.beginPath();
    for (var j = 0; j < beats.length; j++) {
      if (beats[j].t < t0) continue;
      var x = xOf(beats[j].t), y = yOf(beats[j].filtre);
      if (j === 0 || beats[j - 1].t < t0) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.stroke();
    g.fillStyle = COUL.brut;
    for (var m = 0; m < beats.length; m++) {
      if (beats[m].t < t0) continue;
      g.beginPath();
      g.arc(xOf(beats[m].t), yOf(beats[m].bpm), 2, 0, 6.2832);
      g.fill();
    }

    // annotations de rythme (libellés MIT-BIH)
    g.fillStyle = COUL.tech; g.font = "10px ui-monospace, Menlo, monospace";
    for (var k = 0; k < anns.length; k++) {
      var ax = xOf(anns[k].t);
      g.strokeStyle = "rgba(240,198,116,0.4)";
      g.beginPath(); g.moveTo(ax, yOf(200)); g.lineTo(ax, yOf(0)); g.stroke();
      g.fillText("(" + anns[k].libelle, ax + 3, 12);
    }

    // curseur synchronisé
    var cx = xOf(tNow);
    g.strokeStyle = COUL.curseur; g.lineWidth = 1.4;
    g.beginPath(); g.moveTo(cx, 0); g.lineTo(cx, h); g.stroke();
  }

  function render() {
    dessineEcg(taille(ecgC));
    dessineBpm(taille(bpmC));
    majPanels();
    majHoro();
  }

  function frame(now) {
    if (last == null) last = now;
    var dt = (now - last) / 1000; last = now;
    if (playing) {
      tNow += dt * speed;
      if (tNow >= t0 + duree) tNow = t0;   // boucle
    }
    render();
    requestAnimationFrame(frame);
  }

  // ---------- contrôles ----------
  function bascule() {
    playing = !playing;
    var b = byId("scene-play");
    b.textContent = playing ? "Pause" : "Lecture";
    b.classList.toggle("actif", playing);
  }

  function reset() {
    tNow = t0; last = null; render();
  }

  function branche() {
    byId("scene-play").addEventListener("click", bascule);
    byId("scene-restart").addEventListener("click", reset);
    byId("scene-speed").addEventListener("change", function (e) {
      speed = parseFloat(e.target.value || "1");
    });
  }

  function init() {
    if (!D) {
      byId("scene-decision-valeur").textContent =
        "données absentes (lancer tools/genere-scene.py)";
      return;
    }
    branche();
    var t = parseFloat(param("t"));
    if (!isNaN(t)) tNow = t0 + t;
    if (param("pause") === "1") {
      playing = false;
      byId("scene-play").textContent = "Lecture";
      byId("scene-play").classList.remove("actif");
    }
    last = null;
    render();
    requestAnimationFrame(frame);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();