#!/usr/bin/env python3
"""audit-gui.pyw — lanceur CLIQUABLE de l'outil d'audit (fenetre graphique).

Double-clique ce fichier (ou lance audit.bat sous Windows). Une fenetre s'ouvre :
remplis l'URL, choisis les options, clique "Lancer l'audit".
Le rapport .md (ou .json) est ecrit DANS LE MEME DOSSIER que ce fichier.

Aucune dependance externe : tkinter est inclus avec Python. Reutilise la logique
de audit-site.py (une seule source de verite).
"""
import os
import sys
import threading
import importlib.util
import webbrowser
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

import tkinter as tk
from tkinter import ttk, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_auditsite():
    """Charge audit-site.py (nom avec tiret -> import via importlib)."""
    path = os.path.join(HERE, "audit-site.py")
    if not os.path.exists(path):
        raise FileNotFoundError(
            "audit-site.py est introuvable a cote de ce lanceur.\n"
            "Garde audit-gui.pyw et audit-site.py dans le meme dossier."
        )
    spec = importlib.util.spec_from_file_location("auditsite", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class App:
    def __init__(self, root):
        self.root = root
        self.mod = None
        self.last_out = None
        root.title("NexMove — Audit de site")
        root.geometry("560x430")
        root.minsize(520, 400)

        pad = {"padx": 14, "pady": 6}
        frm = ttk.Frame(root)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Audit de site", font=("Segoe UI", 15, "bold")).pack(anchor="w", **pad)
        ttk.Label(
            frm,
            text="Entre une adresse, lance l'audit : le rapport est enregistre\ndans ce dossier.",
            foreground="#555",
        ).pack(anchor="w", padx=14)

        # URL
        ttk.Label(frm, text="Adresse du site").pack(anchor="w", padx=14, pady=(12, 2))
        self.url = tk.StringVar(value="https://kaizenjob.cv")
        e = ttk.Entry(frm, textvariable=self.url)
        e.pack(fill="x", padx=14)
        e.focus()

        # Options
        opt = ttk.Frame(frm)
        opt.pack(fill="x", padx=14, pady=(12, 4))

        ttk.Label(opt, text="Pages max").grid(row=0, column=0, sticky="w")
        self.maxp = tk.IntVar(value=12)
        ttk.Spinbox(opt, from_=1, to=80, textvariable=self.maxp, width=6).grid(row=0, column=1, sticky="w", padx=(8, 24))

        ttk.Label(opt, text="Format").grid(row=0, column=2, sticky="w")
        self.fmt = tk.StringVar(value="md")
        ttk.Radiobutton(opt, text="Markdown", variable=self.fmt, value="md").grid(row=0, column=3, sticky="w", padx=(8, 4))
        ttk.Radiobutton(opt, text="JSON", variable=self.fmt, value="json").grid(row=0, column=4, sticky="w")

        self.same = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="Rester sur le meme domaine (recommande)", variable=self.same).pack(anchor="w", padx=14, pady=(2, 2))

        # Bouton
        self.btn = ttk.Button(frm, text="  Lancer l'audit  ", command=self.run)
        self.btn.pack(anchor="w", padx=14, pady=(10, 4))

        # Status + log
        self.status = tk.StringVar(value="Pret.")
        ttk.Label(frm, textvariable=self.status, foreground="#2F5BFF").pack(anchor="w", padx=14)

        self.log = tk.Text(frm, height=6, wrap="word", state="disabled", bg="#f6f7fb", relief="flat")
        self.log.pack(fill="both", expand=True, padx=14, pady=(6, 6))

        self.openbtn = ttk.Button(frm, text="Ouvrir le dossier", command=self.open_folder, state="disabled")
        self.openbtn.pack(anchor="w", padx=14, pady=(0, 10))

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self):
        raw = self.url.get().strip()
        if not raw:
            messagebox.showwarning("Adresse manquante", "Entre l'adresse du site a auditer.")
            return
        self.btn.configure(state="disabled")
        self.openbtn.configure(state="disabled")
        self.status.set("Audit en cours…")
        self._log("Demarrage de l'audit de " + raw)
        threading.Thread(target=self._work, args=(raw,), daemon=True).start()

    def _work(self, raw):
        try:
            if self.mod is None:
                self.mod = _load_auditsite()
            url = raw if "://" in raw else "https://" + raw
            fmt = self.fmt.get()
            pages = self.mod.crawl(
                url,
                max(1, int(self.maxp.get())),
                bool(self.same.get()),
                0.4,     # delay (politesse)
                25,      # timeout
            )
            host = urlparse(url).netloc.replace(".", "_")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
            ext = "json" if fmt == "json" else "md"
            out = os.path.join(HERE, f"{host}-audit-{stamp}.{ext}")
            if fmt == "json":
                import json
                data = json.dumps(pages, ensure_ascii=False, indent=2)
            else:
                data = self.mod.to_md(url, pages)
            with open(out, "w", encoding="utf-8") as f:
                f.write(data)
            self.last_out = out
            ok = sum(1 for p in pages if not p.get("error"))
            self.root.after(0, self._done, out, len(pages), ok)
        except Exception as e:
            self.root.after(0, self._fail, str(e))

    def _done(self, out, total, ok):
        self.status.set("Termine !")
        self._log(f"OK — {ok}/{total} page(s) analysees.")
        self._log("Fichier : " + out)
        self.openbtn.configure(state="normal")
        self.btn.configure(state="normal")

    def _fail(self, err):
        self.status.set("Echec.")
        self._log("Erreur : " + err)
        self.btn.configure(state="normal")
        messagebox.showerror("Audit echoue", err)

    def open_folder(self):
        folder = HERE
        try:
            if sys.platform.startswith("win"):
                if self.last_out:
                    subprocess.run(["explorer", "/select,", self.last_out])
                else:
                    os.startfile(folder)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception:
            messagebox.showinfo("Dossier", folder)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
