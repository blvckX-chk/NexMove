@echo off
REM Lanceur Windows de l'outil d'audit NexMove.
REM Double-clique ce fichier : la fenetre graphique s'ouvre.
REM (Si rien ne se passe, installe Python depuis python.org en cochant "Add to PATH".)
cd /d "%~dp0"
pythonw audit-gui.pyw 2>nul || python audit-gui.pyw
