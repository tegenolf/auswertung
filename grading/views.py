from django.db.models import F, Sum
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import generic
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.core.management import call_command
from django.http import Http404

from .models import *

import xml.etree.ElementTree as ET
import os

import MySQLdb


## Hilfsfunktionen ##

## Funktion zum Abrufen der Client-IP-Adresse für Logging-Zwecke ##
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

## Funktion zum Aktualisieren der Einstellungen in der settings.xml ##
def update_settings_xml(setting_dict, parent_element='root'):
    filename = os.path.join(os.path.dirname(__file__), 'settings.xml')
    tree = ET.parse(filename)
    root = tree.getroot()
    if parent_element != 'root':
        root = root.find(parent_element)
    for setting_name, setting_value in setting_dict.items():
        setting_element = root.find(setting_name)
        if setting_element is not None:
            setting_element.text = setting_value
        else:
            new_element = ET.SubElement(root, setting_name)
            new_element.text = setting_value
    tree.write(filename)

## Funktion zum Einlesen der Einstellungen aus der settings.xml und Rückgabe als Dictionary ##
def read_settings_xml():
    settings_dict = {}
    filename = os.path.join(os.path.dirname(__file__), 'settings.xml')
    tree = ET.parse(filename)
    root = tree.getroot()
    for child in root:
        if child is not None and child.text is not None:
            if child.tag == 'database1':
                for db_child in child:
                    settings_dict["db1_"+db_child.tag] = db_child.text
            elif child.tag == 'database2':
                for db_child in child:
                    settings_dict["db2_"+db_child.tag] = db_child.text
            else:
                settings_dict[child.tag] = child.text
    return settings_dict


##  View Klassen für die verschiedenen Seiten der Anwendung ##

## Die Index-Seite zeigt eine Liste aller Athleten an, für die der angemeldete Benutzer Wertungen 
# eingeben darf. Es werden auch die Athleten angezeigt, für die der Benutzer keine Berechtigung hat, 
# um eine Übersicht zu geben. ##
class IndexView(LoginRequiredMixin, generic.ListView):
    template_name = "grading/index.html"
    context_object_name = "athletes_list"

    def get_queryset(self):
        """Return a list of athletes."""
        return Athlete.objects.order_by("sid")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        athlete_list = context['athletes_list']
        allowed_athletes = []
        not_allowed_athletes = []
        for athlete in athlete_list:
            if athlete.allowed_to_grade(self.request.user.id):
                allowed_athletes.append(athlete)
            else:
                not_allowed_athletes.append(athlete)
        context['athletes_list'] = allowed_athletes
        context['not_allowed_athletes'] = not_allowed_athletes
        context['settings_dict'] = read_settings_xml()
        return context

## Die Detail-Seite zeigt die Details eines Athleten an, einschließlich der Wettkämpfe, an denen er 
# teilnimmt, und der Disziplinen, für die der angemeldete Benutzer Wertungen eingeben darf. ##
class DetailView(LoginRequiredMixin, UserPassesTestMixin, generic.DetailView):
    model = Athlete
    template_name = "grading/athlete.html"

    def get_queryset(self):
        return Athlete.objects

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_list = self.object.athlete_comp_set.all()
        context['competition_list'] = competition_list
        disciplines_dict = {}
        for comp in competition_list:
            disciplines_allowed = comp.competition.comp_dis_set.all()
            disciplines_not_allowed = comp.competition.comp_dis_set.all()
            for dis in disciplines_allowed:
                comp_dis = Comp_Dis.objects.get(competition_id=comp.competition.cid, discipline_id=dis.discipline.did)
                if not comp_dis.allowed_to_grade(self.request.user.id):
                    disciplines_allowed = disciplines_allowed.exclude(discipline__did=dis.discipline.did)
                else:
                    disciplines_not_allowed = disciplines_not_allowed.exclude(discipline__did=dis.discipline.did)
            disciplines_dict[comp.competition.cid]=(disciplines_allowed, disciplines_not_allowed)
        context['disciplines_dict'] = disciplines_dict
        context['settings_dict'] = read_settings_xml()
        return context
    
    def test_func(self):     
        athlete = self.get_object()
        return athlete.allowed_to_grade(self.request.user.id)

## Die Grade-Seite zeigt die Bewertungsseite für einen Athleten, einen Wettkampf und eine Disziplin an. 
# Es werden die aktuellen Wertungen angezeigt, falls vorhanden, und es gibt ein Formular zum Eingeben 
# oder Ändern der Wertungen. ##
class GradeView(LoginRequiredMixin, UserPassesTestMixin, generic.DetailView):
    model = Athlete
    template_name = "grading/grade.html"

    #def get(self, request, *args, **kwargs):
    #    try:
    #        return super(GradeView, self).get(request, *args, **kwargs)
    #    except Http404:
    #        return render(
    #            request,
    #            "grading/index.html",
    #            {
    #                "error_message": "Kein Sportler mit dieser Startnummer vorhanden.",
    #            },
    #        )
        
    #def get_object(self, queryset=None):
    #    print("Test")
    #    return get_object_or_404(Athlete, **self.kwargs)
        
    def get_queryset(self):
        return Athlete.objects
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.GET.get('sid_search') is not None or (self.request.GET.get('cid') is None or self.request.GET.get('did') is None):
            competitions = self.object.athlete_comp_set.all()
            for comp in competitions:
                comp_dis_list = Comp_Dis.objects.filter(competition_id=comp.competition.cid)
                for comp_dis in comp_dis_list:
                    if comp_dis.allowed_to_grade(self.request.user.id):
                        cid = comp.competition.cid
                        did = comp_dis.discipline.did
                        break
        else:
            cid = self.request.GET.get('cid')
            did = self.request.GET.get('did')
        competition = Competition.objects.get(cid=cid)
        context['competition'] = competition
        discipline = Discipline.objects.get(did=did)
        context['discipline'] = discipline
        initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did).first()
        
        # Auf Änderungen in Didis Datenbank checken
        settings_dict = read_settings_xml()
        try:
            # Datenbankverbindung basierend auf dbid herstellen
            if self.object.dbid == 1:
                db = MySQLdb.connect(host=settings_dict['db1_host'], user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'], port=int(settings_dict['db1_port']))
            elif self.object.dbid == 2:
                db = MySQLdb.connect(host=settings_dict['db2_host'], user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'], port=int(settings_dict['db2_port']))        
            cursor = db.cursor()
            cursor.execute("SELECT Punktzahl FROM ergebnisse WHERE Startnummer=%s AND DisziplinID=%s", (self.object.sid,did))
            didi_grading = cursor.fetchone()
            db.commit()
            cursor.close()
            if didi_grading is not None:
                if initial_grading is not None:
                    if didi_grading[0] != initial_grading.score:
                        initial_grading.score = didi_grading[0]
                        initial_grading.kari1 = 0
                        initial_grading.kari2 = 0
                        initial_grading.kari3 = 0
                        initial_grading.kari4 = 0
                        initial_grading.kari5 = 0
                        initial_grading.awert = -1*initial_grading.score
                        initial_grading.ewert = 0
                        initial_grading.dwert = 0
                        initial_grading.save()
                        initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did).first()
                        context['error_message'] = "Die gespeicherte Wertung stimmte nicht mit der Wertung in Didis Datenbank überein. Sie wurde aktualisiert."
                else:
                    grading = Grading(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did, score=didi_grading[0], kari1=0, kari2=0, kari3=0, kari4=0, kari5=0, awert=-1*didi_grading[0], ewert=0, dwert=0)
                    grading.save()
                    initial_grading = grading
                    context['error_message'] = "In Didis Datenbank war bereits eine Wertung gespeichert. Sie wurde nun übernommen."
        except MySQLdb.Error:
            pass

        context['initial_grading'] = initial_grading
        context['settings_dict'] = settings_dict
        context['not_changeable'] = False
        return context
    
    def test_func(self):
        athlete = self.get_object()
        if self.request.GET.get('sid_search') is not None or (self.request.GET.get('cid') is None or self.request.GET.get('did') is None):
            return athlete.allowed_to_grade(self.request.user.id)
        comp_dis = Comp_Dis.objects.get(competition_id=self.request.GET.get('cid'), discipline_id=self.request.GET.get('did'))
        return comp_dis.allowed_to_grade(self.request.user.id) and athlete.allowed_to_grade(self.request.user.id)

## Die Results-Seite zeigt die Ergebnisse für einen Athleten, einen Wettkampf und eine Disziplin an. 
# Es werden die aktuellen Wertungen und die Gesamtpunktzahl angezeigt. ##
class ResultsView(LoginRequiredMixin, UserPassesTestMixin, generic.DetailView):
    model = Athlete
    template_name = "grading/grade.html"

    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Athlete.objects
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = Competition.objects.get(cid=self.request.GET.get('cid'))
        context['competition'] = competition
        discipline = Discipline.objects.get(did=self.request.GET.get('did'))
        context['discipline'] = discipline
        initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did).first()
        context['initial_grading'] = initial_grading
        context['settings_dict'] = read_settings_xml()
        context['not_changeable'] = True
        return context

    def test_func(self):
        athlete = self.get_object()
        comp_dis = Comp_Dis.objects.get(competition_id=self.request.GET.get('cid'), discipline_id=self.request.GET.get('did'))
        return comp_dis.allowed_to_grade(self.request.user.id) and athlete.allowed_to_grade(self.request.user.id)

## Die AllResults-Seite zeigt eine Liste aller Ergebnisse für alle Athleten, Wettkämpfe und Disziplinen an.
# Nur Benutzer mit Administrator- oder Mitarbeiterrechten können diese Seite sehen. ##
class AllResultsView(LoginRequiredMixin, UserPassesTestMixin, generic.ListView):
    template_name = "grading/results.html"
    context_object_name = "ranking_list"

    def get_queryset(self):
        """Return a list of scores."""
        if self.request.GET.get('cid'):
            return Athlete_Comp.objects.filter(competition_id=self.request.GET.get('cid')).order_by("ranking").select_related("athlete", "competition")
        else:
            id = Competition.objects.first().cid if Competition.objects.first() else None
            return Athlete_Comp.objects.filter(competition_id=id).order_by("ranking").select_related("athlete", "competition")
    
    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.is_staff
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for entry in context['ranking_list']:
            entry.disciplines = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid).select_related("discipline")
        context['competitions'] = Competition.objects.all().order_by("cid")
        if self.request.GET.get('cid'):
            context['selected_competition_id'] = self.request.GET.get('cid')
        else:
            context['selected_competition_id'] = context['competitions'].first().cid if context['competitions'] else None
        context['selected_competition_name'] = Competition.objects.get(cid=context['selected_competition_id']).name
        context['settings_dict'] = read_settings_xml()
        return context
    
    def get_template_names(self):
        if self.request.htmx:
            return ["grading/results_list.html"]
        else:
            return ["grading/results.html"]

## Die Logs-Seite zeigt eine Liste aller Änderungen an Wertungen an, einschließlich des Benutzers, 
# der die Änderung vorgenommen hat, der IP-Adresse, des Athleten, des Wettkampfs, der Disziplin, 
# der Art der Änderung und des Datums. Nur Benutzer mit Administrator- oder Mitarbeiterrechten können 
# diese Seite sehen. ##
class LogsView(LoginRequiredMixin, UserPassesTestMixin, generic.ListView):
    template_name = "grading/logs.html"
    context_object_name = "logs_list"
    paginate_by = 20

    def get_queryset(self):
        """Return a list of logs."""
        return Logs.objects.order_by("-log_date")
    
    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.is_staff
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['settings_dict'] = read_settings_xml()
        return context

##  Die Judges-Seite zeigt eine Liste aller Benutzer an, die als Wertungsrichter fungieren, und die 
# Wettkämpfe und Disziplinen, für die sie berechtigt sind, Wertungen einzugeben. Nur Benutzer mit 
# Administrator- oder Mitarbeiterrechten können diese Seite sehen. ##    
class JudgesView(LoginRequiredMixin, UserPassesTestMixin, generic.ListView):
    template_name = "grading/judges.html"
    context_object_name = "judges_dict"

    def get_queryset(self):

        judges_list = User.objects.filter(is_staff=False, is_superuser=False).order_by("username")
        judges_dict = {}
        for judge in judges_list:
            comp_dis = judge.permission_set.all()
            judges_dict[judge.username]=(comp_dis)
        return judges_dict

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.is_staff
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['settings_dict'] = read_settings_xml()
        return context
    
## Die Judges_Form-Seite zeigt ein Formular zum Bearbeiten der Berechtigungen der Wertungsrichter an. 
# Es werden alle Benutzer angezeigt, die als Wertungsrichter fungieren, und die Wettkämpfe und Disziplinen, 
# für die sie berechtigt sind, Wertungen einzugeben. Es gibt auch Kontrollkästchen, um die Berechtigungen zu ändern. 
# Nur Benutzer mit Administrator- oder Mitarbeiterrechten können diese Seite sehen. ##   
class JudgesFormView(LoginRequiredMixin, UserPassesTestMixin, generic.ListView):
    template_name = "grading/judges_form.html"
    context_object_name = "judges_dict"

    def get_queryset(self):

        judges_list = User.objects.filter(is_staff=False, is_superuser=False).order_by("username")
        judges_dict = {}
        for judge in judges_list:
            comp_dis = judge.permission_set.all()
            judges_dict[judge.username]=(comp_dis)
        return judges_dict
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = Competition.objects.all().order_by("cid")
        comp_dis_dict = {}
        for comp in competition:
            comp_dis_list = Comp_Dis.objects.filter(competition_id=comp.cid)
            comp_dis_dict[comp.cid]=(comp_dis_list)
        context['comp_dis_dict'] = comp_dis_dict
        permission_list = []
        for judge, perm in context['judges_dict'].items():
            for p in perm:  
                permission_list.append((str(p.comp_dis.id)+"_"+judge))
        context['permission_list'] = permission_list
        context['settings_dict'] = read_settings_xml()
        return context

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.is_staff

## Die Database-Seite zeigt die aktuellen Datenbankeinstellungen an und bietet die Möglichkeit, sie zu ändern. 
# Nur Benutzer mit Administrator- oder Mitarbeiterrechten können diese Seite sehen. ##    
class DatabaseView(LoginRequiredMixin, UserPassesTestMixin, generic.TemplateView):
    template_name = "grading/database.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings_dict = read_settings_xml()
        context.update(settings_dict)
        return context

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.is_staff

## Die Funktion save_grade verarbeitet die POST-Anfrage zum Speichern einer Wertung. Sie überprüft, ob der Benutzer 
# berechtigt ist, die Wertung zu ändern, und ob die Eingaben gültig sind. Wenn alles in Ordnung ist, wird die Wertung 
# gespeichert, die Gesamtpunktzahl aktualisiert, das Ranking neu berechnet und die Änderungen in Didis Datenbank übernommen. 
# Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def save_grade(request, athlete_id):
    try:
        comp_dis = Comp_Dis.objects.get(competition_id=request.POST["cid"], discipline_id=request.POST["did"])
        if not comp_dis.allowed_to_grade(request.user.id):
            return render(
                request,
                "grading/grade.html",
                {
                    "athlete": get_object_or_404(Athlete, pk=athlete_id),
                    "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                    "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                    "error_message": "Sie haben keine Berechtigung, diese Wertung zu ändern.",
                },
            )
        grading = Grading.objects.get(athlete_id=athlete_id, competition_id=request.POST["cid"], discipline_id=request.POST["did"])
        grading.kari1 = request.POST["kari1"]
        grading.kari2 = request.POST["kari2"]
        grading.kari3 = request.POST["kari3"]
        grading.kari4 = request.POST["kari4"]
        grading.kari5 = request.POST["kari5"]
        grading.awert = request.POST["awert"]
        grading.dwert = request.POST["dwert"]
        grading.ewert = request.POST["ewert"]
        grading.score = request.POST["score"]
        log_text = f"Wertung geändert";
    except Grading.DoesNotExist:
        grading = Grading(athlete_id=athlete_id, competition_id=request.POST["cid"], discipline_id=request.POST["did"], kari1=request.POST["kari1"], kari2=request.POST["kari2"], kari3=request.POST["kari3"], kari4=request.POST["kari4"], kari5=request.POST["kari5"], ewert=request.POST["ewert"], awert=request.POST["awert"], dwert=request.POST["dwert"], score=request.POST["score"])
        log_text = f"Wertung hinzugefügt";
    except (KeyError, ValueError):
        return render(
            request,
            "grading/grade.html",
            {
                "athlete": get_object_or_404(Athlete, pk=athlete_id),
                "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                "settings_dict": read_settings_xml(),
                "error_message": "Fehlende oder ungültige Eingabe.",
            },
        )
    try:
        max_score = Comp_Dis.objects.get(competition_id=request.POST["cid"], discipline_id=request.POST["did"]).max_score
        if float(grading.score) < 0 or float(grading.score) > float(max_score):
            return render(
                request,
                "grading/grade.html",
                {
                    "athlete": get_object_or_404(Athlete, pk=athlete_id),
                    "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                    "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                    "initial_grading": grading,
                    "settings_dict": read_settings_xml(),
                    "error_message": f"Punktzahl muss zwischen 0 und {max_score} liegen.",
                },
            )
        grading.save()

        # Gesamtpunktzahl in Athlete_Comp aktualisieren
        athlete_comp = Athlete_Comp.objects.get(athlete_id=athlete_id, competition_id=request.POST["cid"])
        totalscore = Grading.objects.filter(athlete_id=athlete_id, competition_id=request.POST["cid"]).aggregate(Sum('score'))['score__sum']
        athlete_comp.score = totalscore
        athlete_comp.save()

        # Ranking aktualisieren
        athlete_comps = Athlete_Comp.objects.filter(competition_id=request.POST["cid"],athlete__dbid=request.POST["dbid"]).order_by('-score')
        ranking = 1
        i = 1
        for ac in athlete_comps:
            if i == 1:
                ac.ranking = ranking
                previous_score = ac.score
            else:
                if previous_score != ac.score:
                    ranking = i
                    previous_score = ac.score
                ac.ranking = ranking
            ac.save()
            i += 1

        # Didis Datenbank aktualisieren
        settings_dict = read_settings_xml()
        try:
            # Datenbankverbindung basierend auf dbid herstellen
            if request.POST["dbid"] == "1":
                db = MySQLdb.connect(host=settings_dict['db1_host'], user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'], port=int(settings_dict['db1_port']))
            elif request.POST["dbid"] == "2":
                db = MySQLdb.connect(host=settings_dict['db2_host'], user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'], port=int(settings_dict['db2_port']))        
            cursor = db.cursor()
            # Update Punktzahl
            cursor.execute("UPDATE ergebnisse SET Leistung=%s, Punktzahl=%s WHERE Startnummer=%s AND DisziplinID=%s", (grading.score, grading.score, athlete_id, request.POST["did"]))
            db.commit()
            affectec_rows = cursor.rowcount
            if affectec_rows is None or affectec_rows == 0:
                cursor.execute("INSERT INTO ergebnisse(Leistung,Punktzahl,Startnummer,DisziplinID) VALUES(%s,%s,%s,%s)",(grading.score, grading.score, athlete_id, request.POST["did"]))
            # Update Gesamtpunktzahl
            cursor.execute("UPDATE teilnehmer SET Gesamtpunktzahl=%s WHERE Startnummer=%s", (totalscore, athlete_id))
            # Update Ranking aller Teilnehmer im gleichen Wettkampf und der gleichen Datenbank
            athlete_comps = Athlete_Comp.objects.filter(competition_id=request.POST["cid"],athlete__dbid=request.POST["dbid"])
            for ac in athlete_comps:
                cursor.execute("UPDATE teilnehmer SET Rang=%s WHERE Startnummer=%s", (ac.ranking, ac.athlete_id))
            db.commit()
            cursor.close()
        except MySQLdb.Error as e:
            return render(
                request,
                "grading/grade.html",
                {
                    "athlete": get_object_or_404(Athlete, pk=athlete_id),
                    "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                    "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                    "settings_dict": read_settings_xml(),
                    "error_message": f"Fehler beim Speichern der Wertung in Didis Datenbank: {e}",
                },
            )

        logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=athlete_id, competition_id=request.POST["cid"], discipline_id=request.POST["did"], log_text=log_text, log_date=timezone.now())
        logs.save()
    except (KeyError, ValueError):
        return render(
            request,
            "grading/grade.html",
            {
                "athlete": get_object_or_404(Athlete, pk=athlete_id),
                "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                "settings_dict": read_settings_xml(),
                "error_message": "Fehlende oder ungültige Eingabe.",
            },
        )    
    return render(
            request,
            "grading/grade.html",
            {
                "athlete": get_object_or_404(Athlete, pk=athlete_id),
                "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                "initial_grading": grading,
                "settings_dict": read_settings_xml(),
                "success_message": "Eingabe gespeichert.",
                "not_changeable": True,
            },
        )   

## Die Funktion save_judges verarbeitet die POST-Anfrage zum Speichern der Berechtigungen der Wertungsrichter. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Berechtigungen zu ändern, und aktualisiert dann die 
# Berechtigungen für alle Wertungsrichter basierend auf den Kontrollkästchen im Formular. Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def save_judges(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:judges"))
    judges_list = User.objects.filter(is_staff=False, is_superuser=False).order_by("username")
    for judge in judges_list:
        judge.permission_set.all().delete()
        for key, value in request.POST.items():
            print(key + " : " + str(value))
            if value == "1":
                key_split = key.split("_")
                if len(key_split) == 2:
                    if key_split[1] == judge.username:
                        comp_dis = get_object_or_404(Comp_Dis, id=key_split[0])
                        permission = judge.permission_set.create(comp_dis=comp_dis)
                        permission.save()
    
    judges_list = User.objects.filter(is_staff=False, is_superuser=False).order_by("username")
    judges_dict = {}
    for judge in judges_list:
        comp_dis = judge.permission_set.all()
        judges_dict[judge.username]=(comp_dis)
    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Berechtigungen geändert", log_date=timezone.now())
    logs.save()
    context = {}
    context['judges_dict'] = judges_dict
    context['success_message'] = "Berechtigungen gespeichert."
    context['settings_dict'] = read_settings_xml()
    return render(
            request,
            "grading/judges.html",
            context,
        ) 

## Die Funktion change_wk_settings verarbeitet die POST-Anfrage zum Speichern der Wettkampf-Einstellungen. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Einstellungen zu ändern, und aktualisiert dann die 
# Einstellungen basierend auf den Eingaben im Formular. Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def change_wk_settings(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    update_settings_xml({'wk_title':request.POST.get('wk_title', ''), 'wk_type':request.POST.get('wk_type', '')})
    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Wettkampf-Einstellungen geändert", log_date=timezone.now())
    logs.save()
    context = read_settings_xml()
    context['success_message'] = "Wettkampf-Einstellungen gespeichert."
    context['settings_dict'] = read_settings_xml()
    return render(
            request,
            "grading/database.html",
            context,
        ) 

##  Die Funktion change_database_settings verarbeitet die POST-Anfrage zum Speichern der Datenbank-Einstellungen. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Einstellungen zu ändern, und aktualisiert dann die Einstellungen 
# basierend auf den Eingaben im Formular. Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def change_database_settings(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    update_settings_xml({'name':request.POST.get('db1_name', ''), 'user':request.POST.get('db1_user', ''), 'password':request.POST.get('db1_password', ''), 'host':request.POST.get('db1_host', ''), 'port':request.POST.get('db1_port', '')}, parent_element='database1')
    update_settings_xml({'name':request.POST.get('db2_name', ''), 'user':request.POST.get('db2_user', ''), 'password':request.POST.get('db2_password', ''), 'host':request.POST.get('db2_host', ''), 'port':request.POST.get('db2_port', '')}, parent_element='database2')
    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Datenbank-Einstellungen geändert", log_date=timezone.now())
    logs.save()
    context = read_settings_xml()
    context['success_message'] = "Datenbank-Einstellungen gespeichert."
    return render(
            request,
            "grading/database.html",
            context,
        ) 

## Die Funktion database_backup_complete verarbeitet die POST-Anfrage zum vollständigen Export der Datenbank. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Datenbank zu exportieren, und exportiert dann alle Daten 
# in eine JSON-Datei. Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def database_backup_complete(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    filename = os.path.join(os.path.dirname(__file__), 'database_backup_complete.json')
    output = open(filename, 'w')
    call_command('dumpdata',indent=4, stdout=output)
    output.close()
    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Datenbank exportiert", log_date=timezone.now())
    logs.save()
    context = read_settings_xml()
    context['success_message'] = "Datenbank exportiert."
    context['backup_file'] = 'database_backup_complete.json'
    return render(
            request,
            "grading/database.html",
            context,
        )

## Die Funktion database_backup_partial verarbeitet die POST-Anfrage zum teilweisen Export der Datenbank. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Datenbank zu exportieren, und exportiert dann nur die 
# Daten der Bewertungsanwendung in eine JSON-Datei. Es wird auch ein Log-Eintrag erstellt. ##  
@login_required
def database_backup(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    filename = os.path.join(os.path.dirname(__file__), 'database_backup_partial.json')
    output = open(filename, 'w')
    call_command('dumpdata', 'grading.Athlete', 'grading.Competition', 'grading.Discipline', 'grading.Comp_Dis', 'grading.Athlete_Comp', 'grading.Grading', 'grading.Permission', 'grading.Logs', indent=4, stdout=output)
    output.close()
    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Daten exportiert", log_date=timezone.now())
    logs.save()
    context = read_settings_xml()
    context['success_message'] = "Daten exportiert."
    context['backup_file'] = "database_backup_partial.json"
    return render(
            request,
            "grading/database.html",
            context,
        )

## Die Funktion database_restore verarbeitet die POST-Anfrage zum Wiederherstellen der Datenbank aus einer JSON-Datei. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Datenbank zu importieren, und importiert dann die Daten aus der 
# hochgeladenen JSON-Datei. Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def database_restore(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    try:
        restore_file = request.FILES['restore_file']
        filename = os.path.join(os.path.dirname(__file__), 'grading/restore_temp.json')
        with open(filename, 'wb+') as destination:
            for chunk in restore_file.chunks():
                destination.write(chunk)
        call_command('loaddata', 'grading/restore_temp.json')
        os.remove(filename)
    except (KeyError, ValueError):
        context = read_settings_xml()
        context['error_message'] = "Fehler beim Hochladen der Datei."
        return render(
           request,
            "grading/database.html",
            context,
        )
    
    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Datenbank wiederhergestellt", log_date=timezone.now())
    logs.save()
    context = read_settings_xml()
    context['success_message'] = "Datenbank wiederhergestellt."
    return render(
            request,
            "grading/database.html",
            context,
        ) 

## Die Funktion database_delete verarbeitet die POST-Anfrage zum vollständigen Löschen aller Daten in der Datenbank. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Datenbank zu löschen, und löscht dann alle Daten aus allen Tabellen. 
# Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def database_delete(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    Grading.objects.all().delete()
    Athlete_Comp.objects.all().delete()
    Athlete.objects.all().delete()
    Permission.objects.all().delete()
    Logs.objects.all().delete()
    Comp_Dis.objects.all().delete()
    Competition.objects.all().delete()
    Discipline.objects.all().delete()
    
    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Datenbank zurückgesetzt", log_date=timezone.now())
    logs.save()
    context = read_settings_xml()
    context['success_message'] = "Datenbank zurückgesetzt."
    return render(
            request,
            "grading/database.html",
            context,
        ) 

## Die Funktion database_import verarbeitet die POST-Anfrage zum Importieren von Daten aus Didi's Datenbank. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Datenbank zu importieren, und importiert dann die Daten 
# aus der angegebenen Datenbankverbindung. Es werden die Veranstaltungsdetails, die Wettbewerbe, die Athleten, 
# die Disziplinen und die Wertungen importiert. Es wird auch ein Log-Eintrag erstellt. ##
@login_required
def database_import(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    settings_dict = read_settings_xml()

    # Datenbank 1
    try:
        # Datenbankverbindung herstellen
        db = MySQLdb.connect(host=settings_dict['db1_host'], port=int(settings_dict['db1_port']), user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'])
        c = db.cursor()
    except:
        context = read_settings_xml()
        context['error_message'] = "Fehler beim Verbinden mit Datenbank 1. Bitte überprüfen Sie die Einstellungen."
        return render(
            request,
            "grading/database.html",
            context,
        )
    try:
        # Wettkampftitel und -typ importieren
        c.execute("SELECT Name, Art FROM veranstaltung")
        row = c.fetchone()
        if row is not None:
            if row[1] == 0:
                row = (row[0], "einzel")
            elif row[1] == 1:
                row = (row[0], "mannschaft")
            update_settings_xml({'wk_title':row[0], 'wk_type':row[1]})
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Veranstaltungsdetails ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        ) 
    
    try:
        # Wettbewerbe importieren
        c.execute("SELECT WettkampfID, Wettkampfname FROM wettkämpfe")
        for row in c.fetchall():
            competition = Competition(cid=row[0], name=row[1])
            competition.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Wettkämpfe aus Datenbank 1 ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        ) 
    
    try:
        # Athleten und Athleten-Wettbewerbe-Zuordnung importieren
        c.execute("SELECT t.Startnummer, t.Vorname, t.Name, t.Jahrgang, v.VereinsName, t.WettkampfId, t.Gesamtpunktzahl, t.Rang FROM teilnehmer as t INNER JOIN vereine as v ON t.Verein=v.VereinsNummer ORDER BY t.Startnummer")
        for row in c.fetchall():
            athlete = Athlete(sid=row[0], vorname=row[1], nachname=row[2], geburtsjahr=row[3], verein=row[4], dbid=1)
            athlete.save()
            athlete_comp = Athlete_Comp(athlete_id=row[0], competition_id=row[5], score=row[6], ranking=row[7])
            athlete_comp.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Teilnehmer aus Datenbank 1 ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        ) 
    
    try:
        # Disziplinen importieren
        c.execute("SELECT DisziplinID, DisziplinName, Wertungsverfahren, Sekunden FROM disziplinen")
        for row in c.fetchall():
            if row[2] == 'L':
                gewichtung = 1.0
            else:
                gewichtung = 0.0
            if row[3] == 0:
                einheit = "Pkt."
            else:
                einheit = "Sek."
            discipline = Discipline(did=row[0], bezeichnung=row[1], einheit=einheit, gewichtung=gewichtung)
            discipline.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Disziplinen aus Datenbank 1 ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        ) 
    
    try:
        # Wettbewerbe-Disziplinen importieren
        c.execute("SELECT dz.WettkampfID, dz.DisziplinID, d.MaxPunktzahl FROM disziplinzuordnung as dz INNER JOIN disziplinen as d ON dz.DisziplinID=d.DisziplinID")
        for row in c.fetchall():
            comp_dis = Comp_Dis(competition_id=row[0], discipline_id=row[1], max_score=row[2])
            comp_dis.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Disziplinen-Zuordnung aus Datenbank 1 ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        ) 
    
    try:
        # Wertungen importieren
        c.execute("SELECT e.Startnummer, e.DisziplinID, e.Punktzahl, t.WettkampfID FROM ergebnisse as e INNER JOIN teilnehmer as t ON e.Startnummer = t.Startnummer")
        for row in c.fetchall():
            # Überprüfen, ob Athlet bereits existiert, um Fehler zu vermeiden
            if Athlete.objects.filter(sid=row[0]).exists():
                grading = Grading(athlete_id=row[0], competition_id=row[3], discipline_id=row[1], score=row[2], kari1=0, awert=-1*row[2], ewert=0, dwert=0)
                grading.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Wertungen aus Datenbank 1 ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        )
    
    c.close()

    # Datenbank 2
    if settings_dict['db2_name'] is not None and settings_dict['db2_name'] != '' and settings_dict['db2_user'] is not None and settings_dict['db2_user'] != '' and settings_dict['db2_password'] is not None and settings_dict['db2_password'] != '' and settings_dict['db2_host'] is not None and settings_dict['db2_host'] != '' and settings_dict['db2_port'] is not None and settings_dict['db2_port'] != '':
        try:
            # Datenbankverbindung herstellen
            db = MySQLdb.connect(host=settings_dict['db2_host'], port=int(settings_dict['db2_port']), user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'])
            c = db.cursor()
        except:
            context = read_settings_xml()
            context['error_message'] = "Fehler beim Verbinden mit Datenbank 2. Bitte überprüfen Sie die Einstellungen."
            return render(
                request,
                "grading/database.html",
                context,
            )
        try:
            # Wettbewerbe importieren
            c.execute("SELECT WettkampfID, Wettkampfname FROM wettkämpfe")
            db12_competitions = []
            db1_competitions = list(Competition.objects.values_list('cid', flat=True))
            for row in c.fetchall():
                # Überprüfen, ob Wettkampf bereits existiert und ggf. vergleichen, um Duplikate zu vermeiden
                existing_competition = Competition.objects.filter(cid=row[0]).first()
                if existing_competition:
                    if existing_competition.name != row[1]:
                        context = read_settings_xml()
                        context['error_message'] = f"Wettkampf mit ID {row[0]} existiert bereits mit einem anderen Namen. Bitte überprüfen Sie die Datenbank 2 auf Duplikate oder Inkonsistenzen."
                        return render(
                            request,
                            "grading/database.html",
                            context,
                        )
                    db12_competitions.append(row[0])              
                else:
                    competition = Competition(cid=row[0], name=row[1])
                    competition.save()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der Wettkämpfe aus Datenbank 2 ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            )

        try:
            # Athleten und Athleten-Wettbewerbe-Zuordnung importieren
            c.execute("SELECT t.Startnummer, t.Vorname, t.Name, t.Jahrgang, v.VereinsName, t.WettkampfId, t.Gesamtpunktzahl, t.Rang FROM teilnehmer as t INNER JOIN vereine as v ON t.Verein=v.VereinsNummer ORDER BY t.Startnummer")
            for row in c.fetchall():
                # Überprüfen, ob Athlet bereits existiert
                if Athlete.objects.filter(sid=row[0]).exists():
                    context = read_settings_xml()
                    context['error_message'] = f"Teilnehmer mit ID {row[0]} existiert bereits. Bitte überprüfen Sie die Datenbank 2 auf Duplikate oder Inkonsistenzen."
                    return render(
                        request,
                        "grading/database.html",
                        context,
                    )
                else:   
                    athlete = Athlete(sid=row[0], vorname=row[1], nachname=row[2], geburtsjahr=row[3], verein=row[4], dbid=2)
                    athlete.save()
                    athlete_comp = Athlete_Comp(athlete_id=row[0], competition_id=row[5], score=row[6], ranking=row[7])
                    athlete_comp.save()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der Teilnehmer aus Datenbank 2 ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            ) 
        
        try:
            # Disziplinen importieren
            c.execute("SELECT DisziplinID, DisziplinName, Wertungsverfahren, Sekunden FROM disziplinen")
            for row in c.fetchall():
                # Überprüfen, ob Disziplin bereits existiert und ggf. vergleichen, um Duplikate zu vermeiden
                existing_discipline = Discipline.objects.filter(did=row[0]).first()
                if existing_discipline:
                    if existing_discipline.bezeichnung != row[1] or existing_discipline.einheit != ("Sek." if row[3] != 0 else "Pkt.") or existing_discipline.gewichtung != (1.0 if row[2] == 'L' else 0.0):
                        context = read_settings_xml()
                        context['error_message'] = f"Disziplin mit ID {row[0]} existiert bereits mit anderen Details. Bitte überprüfen Sie die Datenbank 2 auf Duplikate oder Inkonsistenzen."
                        return render(
                            request,
                            "grading/database.html",
                            context,
                        )                
                else:
                    if row[2] == 'L':
                        gewichtung = 1.0
                    else:
                        gewichtung = 0.0
                    if row[3] == 0:
                        einheit = "Pkt."
                    else:
                        einheit = "Sek."
                    discipline = Discipline(did=row[0], bezeichnung=row[1], einheit=einheit, gewichtung=gewichtung)
                    discipline.save()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der Disziplinen aus Datenbank 1 ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            ) 
        
        try:
            # Wettbewerbe-Disziplinen importieren
            c.execute("SELECT dz.WettkampfID, dz.DisziplinID, d.MaxPunktzahl FROM disziplinzuordnung as dz INNER JOIN disziplinen as d ON dz.DisziplinID=d.DisziplinID")
            for row in c.fetchall():
                # Überprüfen, ob Wettbewerb-Disziplin-Kombination bereits existiert und ggf. vergleichen, um Duplikate zu vermeiden
                existing_comp_dis = Comp_Dis.objects.filter(competition_id=row[0], discipline_id=row[1]).first()
                if existing_comp_dis:
                    if existing_comp_dis.max_score != row[2]:
                        context = read_settings_xml()
                        context['error_message'] = f"Wettkampf-Disziplin-Kombination mit WettkampfID {row[0]} und Disziplin ID {row[1]} existiert bereits mit einem anderen Maximalwert. Bitte überprüfen Sie die Datenbank 2 auf Duplikate oder Inkonsistenzen."
                        return render(
                            request,
                            "grading/database.html",
                            context,
                        )
                #Überprüfen, ob Wettkampf in Datenbank 1 importiert wurde, um Duplikate zu vermeiden
                elif row[0] in db1_competitions:
                    context = read_settings_xml()
                    context['error_message'] = f"Wettkampf mit ID {row[0]} existiert bereits in Datenbank 1, Wettkampf-Disziplin-Kombination mit Disziplin ID {row[1]} allerdings nicht. Bitte überprüfen Sie die Datenbank 2 auf Duplikate oder Inkonsistenzen."
                    return render(
                        request,
                        "grading/database.html",
                        context,
                    )
                else:
                    comp_dis = Comp_Dis(competition_id=row[0], discipline_id=row[1], max_score=row[2])
                    comp_dis.save()

            #Überprüfen, ob Wettbewerb-Disziplin-Kombination in Datenbank 1 importiert wurde, die in Datenbank 2 nicht vorhanden ist, obwohl der Wettbewerb auch in Datenbank 2 vorhanden ist
            for wkid in db12_competitions:
                comp_dis = Comp_Dis.objects.filter(competition_id=wkid)
                for cd in comp_dis:
                    c.execute("SELECT COUNT(*) FROM disziplinzuordnung WHERE WettkampfID=%s AND DisziplinID=%s", (wkid, cd.discipline_id))
                    if c.fetchone()[0] == 0:
                        context = read_settings_xml()
                        context['error_message'] = f"Wettkampf mit ID {wkid} existiert in Datenbank 1 und 2, Wettkampf-Disziplin-Kombination mit Disziplin ID {cd.discipline_id} allerdings nur in Datenbank 1. Bitte überprüfen Sie die Datenbank 2 auf Duplikate oder Inkonsistenzen."
                        return render(
                            request,
                            "grading/database.html",
                            context,
                        )
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der Disziplinen-Zuordnung aus Datenbank 2 ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            )
        
        try:
            # Wertungen importieren
            c.execute("SELECT e.Startnummer, e.DisziplinID, e.Punktzahl, t.WettkampfID FROM ergebnisse as e INNER JOIN teilnehmer as t ON e.Startnummer = t.Startnummer")
            for row in c.fetchall():
                # Überprüfen, ob Athlet bereits existiert, um Fehler zu vermeiden
                if Athlete.objects.filter(sid=row[0]).exists():
                    grading = Grading(athlete_id=row[0], competition_id=row[3], discipline_id=row[1], score=row[2], kari1=0, awert=-1*row[2])
                    grading.save()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der Wertungen aus Datenbank 2 ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            )
    
    c.close()

    logs = Logs(user=request.user, ip=get_client_ip(request) ,athlete_id=None, competition_id=None, discipline_id=None, log_text="Daten importiert", log_date=timezone.now())
    logs.save()
    context = read_settings_xml()
    context['success_message'] = "Daten von Didis Software importiert."
    return render(
            request,
            "grading/database.html",
            context,
        ) 

## Die Funktion download_file verarbeitet die GET-Anfrage zum Herunterladen einer Datei. 
# Sie überprüft, ob der Benutzer berechtigt ist, die Datei herunterzuladen, und sendet 
# dann die angeforderte Datei als HTTP-Antwort zurück, wenn sie existiert. ##
@login_required
def download_file(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    file_path = 'grading/'+request.GET.get('file_name')
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/json")
            response['Content-Disposition'] = 'inline; filename=' + os.path.basename(file_path)
            return response
    return HttpResponseRedirect(reverse("grading:database"))