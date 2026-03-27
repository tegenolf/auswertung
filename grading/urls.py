from django.urls import path

from . import views

app_name = 'grading'
urlpatterns = [
    ### Seiten: ###
    # ex: /grading/ -> Übersicht aller Athleten
    path("", views.IndexView.as_view(), name="index"),
    # ex:  /grading/5/ -> Detailansicht eines Athleten mit id=5
    path("<int:pk>/", views.DetailView.as_view(), name="detail"),
    # ex:  /grading/5/results/ -> Ergebnisse eines Athleten mit id=5
    path("<int:pk>/results/", views.ResultsView.as_view(), name="results"),
    # ex:  /grading/5/grate/ -> Seite zum Bewerten eines Athleten mit id=5
    path('<int:pk>/grade/', views.GradeView.as_view(), name='grade'),
    # ex:  /grading/results/ -> Seite zum Anzeigen aller Ergebnisse
    path('all_results/', views.AllResultsView.as_view(), name='all_results'),
    # ex:  /grading/logs/ -> Seite zum Anzeigen der Logs
    path('logs/', views.LogsView.as_view(), name='logs'),
    # ex: /grading/judges/ -> Seite zum Anzeigen der aktuellen Wertungsrichter
    path("judges/", views.JudgesView.as_view(), name="judges"),
    # ex: /grading/judges_form -> Seite zum Bearbeiten der Wertungsrichter
    path("judges_form/", views.JudgesFormView.as_view(), name="judges_form"),
    # ex: /grading/database/ -> Seite zum Anzeigen der Datenbankeinstellungen
    path("database/", views.DatabaseView.as_view(), name="database"),
    # ex: /grading/change_wk_settings/ -> Seite zum Bearbeiten der Wettkampfsettings
    path("change_wk_settings/", views.change_wk_settings, name="change_wk_settings"),
    # ex: /grading/change_database_settings/ -> Seite zum Bearbeiten der Datenbanksettings
    path("change_database_settings/", views.change_database_settings, name="change_database_settings"),
    # ex: /grading/database_backup_complete/ -> Seite zum Anzeigen der abgeschlossenen Datenbanksicherung
    path("database_backup_complete/", views.database_backup_complete, name="database_backup_complete"),
    
    ### Funktionen: ###
    # ex:  /grading/5/save_grade/ -> Funktion zum Speichern der Bewertung eines Athleten mit id=5
    path('<int:athlete_id>/save_grade/', views.save_grade, name='save_grade'),
    # ex: /grading/save_judges/ -> Funktion zum Speichern der Wertungsrichter
    path("save_judges/", views.save_judges, name="save_judges"),
    # ex: /grading/database_backup/ -> Funktion zum Erstellen einer Datenbanksicherung
    path("database_backup/", views.database_backup, name="database_backup"),
    # ex: /grading/database_restore/ -> Funktion zum Wiederherstellen einer Datenbanksicherung
    path("database_restore/", views.database_restore, name="database_restore"),
    # ex: /grading/database_delete/ -> Funktion zum Löschen der Datenbank
    path("database_delete/", views.database_delete, name="database_delete"),
    # ex: /grading/database_import/ -> Funktion zum Importieren von Daten in die Datenbank
    path("database_import/", views.database_import, name="database_import"),
    # ex: /grading/download_file/ -> Funktion zum Herunterladen einer Datei (z.B. Datenbanksicherung oder Exportdatei)
    path("download_file/", views.download_file, name="download_file"),
    # ex: /grading/database_clean_duplicates/ -> Funktion zum Bereinigen der Datenbank von Duplikaten
    path("clean_duplicates/", views.database_clean_duplicates, name="database_clean_duplicates"),

]