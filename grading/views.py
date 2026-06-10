from django.db.models import F, Sum, Min
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
    filename = os.path.join(os.path.dirname(__file__), '../../settings_local.xml')
    if not os.path.exists(filename):
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
    filename = os.path.join(os.path.dirname(__file__), '../../settings_local.xml')
    if not os.path.exists(filename):
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
        settings_dict = read_settings_xml()
        if settings_dict['wk_type'] == 'mannschaft':
            return Competition.objects.order_by("cid")
        else:
            return Athlete.objects.order_by("sid")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['settings_dict'] = read_settings_xml()
        if context['settings_dict']['wk_type'] == 'mannschaft':
            comp_list = context['athletes_list']
            allowed_comps = []
            not_allowed_comps = []
            for comp in comp_list:
                # alle Mannschaften des Wettkampfs
                mannschaften = Mannschaft.objects.filter(mannschaft_comp__competition_id=comp.cid).order_by("mid")
                if comp.allowed_to_grade(self.request.user.id):
                    allowed_comps.append({"competition":comp, "mannschaften": mannschaften})
                else:
                    not_allowed_comps.append({"competition":comp, "mannschaften": mannschaften})
            context['athletes_list'] = allowed_comps
            context['not_allowed_athletes'] = not_allowed_comps
        else:
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
        return context

## Die Riegen-Seite zeigt eine Liste aller Athleten an, in Tabs sortiert nach Riegen.
# Es ist gekennhzeichnet, welcher Athlete bereits an dem vom Kari berechtigten Gerät bewertet wurde. ##
class RiegenView(LoginRequiredMixin, generic.ListView):
    template_name = "grading/riegen.html"
    context_object_name = "riegen_list"

    def get_queryset(self):
        """Return a list of athletes filtered by Riege and permission to grade."""
        settings_dict = read_settings_xml()
        if self.request.GET.get('riege'):
            if settings_dict['wk_type'] == 'mannschaft':
                result = Athlete_Comp.objects.filter(athlete__mannschaft__mid=self.request.GET.get('riege')).order_by("athlete_id","competition_id").select_related("athlete", "competition")
            else:
                result = Athlete_Comp.objects.filter(athlete__riege=self.request.GET.get('riege')).order_by("athlete_id","competition_id").select_related("athlete", "competition")
        else:
            if settings_dict['wk_type'] == 'mannschaft':
                allowed_mids = [mannschaft.mid for mannschaft in Mannschaft.objects.order_by("mid").all() if mannschaft.allowed_to_grade(self.request.user.id)]
                if len(allowed_mids) > 0:
                    result = Athlete_Comp.objects.filter(athlete__mannschaft__mid=allowed_mids[0]).order_by("athlete_id","competition_id").select_related("athlete", "competition")
                else:
                    return None
            else:
                id = Athlete.objects.filter(riege__isnull=False).all().aggregate(Min('riege'))['riege__min'] if Athlete.objects.filter(riege__isnull=False).exists() else None
                result = Athlete_Comp.objects.filter(athlete__riege=id).order_by("athlete_id","competition_id").select_related("athlete", "competition")
        return result
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['settings_dict'] = read_settings_xml()
        if context['riegen_list'] is not None:
            for entry in context['riegen_list']:
                # alle Disziplinen des Wettkampfs
                entry.disciplines = Comp_Dis.objects.filter(competition_id=entry.competition.cid).order_by("discipline_id").select_related("discipline")
                # bereits vorhandene Wertungen
                entry.grading = []
                for d in entry.disciplines:
                    d.score = None
                    d.allowed_to_grade = d.allowed_to_grade(self.request.user.id)
                    if int(context['settings_dict']['runde']) > 0:
                        grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did, day=int(context['settings_dict']['runde'])).first()
                    else:
                        grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did).first()
                    if grading is not None and grading.score > 0:
                        d.score = grading.score
            context['competitions'] = Competition.objects.all().order_by("cid")
            if context['settings_dict']['wk_type'] == 'mannschaft':
                allowed_mids = [mannschaft.mid for mannschaft in Mannschaft.objects.order_by("mid").all() if mannschaft.allowed_to_grade(self.request.user.id)]
                context['riegen'] = Mannschaft.objects.filter(mid__in=allowed_mids).values_list('mid', flat=True).distinct().order_by('mid')
            else:
                context['riegen'] = Athlete.objects.filter(riege__isnull=False).values_list('riege', flat=True).distinct().order_by('riege')
            if self.request.GET.get('riege'):
                context['selected_riege'] = self.request.GET.get('riege')
            else:
                context['selected_riege'] = context['riegen'].first() if context['riegen'] else None
            if context['settings_dict']['wk_type'] == 'mannschaft' and context['selected_riege']:
                context['selected_riege_data'] = Mannschaft_Comp.objects.filter(mannschaft_id=context['selected_riege']).select_related("mannschaft", "competition").first()
                if not context['selected_riege_data'].mannschaft.allowed_to_grade(self.request.user.id):
                    context['selected_riege_data'] = None
        else:
            context['competitions'] = None
            context['riegen'] = None
        return context
    
    def get_template_names(self):
        if self.request.htmx:
            return ["grading/riegen_list.html"]
        else:
            return ["grading/riegen.html"]

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
        settings_dict = read_settings_xml()
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
        if int(settings_dict['runde']) > 0:
            initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did, day=int(settings_dict['runde'])).first()
        else:
            initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did).first()
        
        # Auf Änderungen in Didis Datenbank checken
        try:
            # Datenbankverbindung basierend auf dbid herstellen
            if self.object.dbid == 1:
                db = MySQLdb.connect(host=settings_dict['db1_host'], user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'], port=int(settings_dict['db1_port']))
            elif self.object.dbid == 2:
                db = MySQLdb.connect(host=settings_dict['db2_host'], user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'], port=int(settings_dict['db2_port']))        
            cursor = db.cursor()
            if int(settings_dict['runde']) > 0:
                cursor.execute("SELECT Punktzahl FROM ergebnisse WHERE Startnummer=%s AND DisziplinID=%s AND Runde=%s", (self.object.sid,did, settings_dict['runde']))
            else:
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
                        if int(settings_dict['runde']) > 0:
                            initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did, day=int(settings_dict['runde'])).first()
                        else:
                            initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did).first()
                        context['error_message'] = "Die gespeicherte Wertung stimmte nicht mit der Wertung in Didis Datenbank überein. Sie wurde aktualisiert."
                elif didi_grading[0] != 0:
                    if int(settings_dict['runde']) > 0:
                        grading = Grading(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did, score=didi_grading[0], kari1=0, kari2=0, kari3=0, kari4=0, kari5=0, awert=-1*didi_grading[0], ewert=0, dwert=0, day=int(settings_dict['runde']))
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
        if settings_dict['wk_type'] == 'mannschaft':
            context['next'] = Athlete.objects.filter(sid__gt=self.object.sid,mannschaft=self.object.mannschaft).order_by("sid").first()
            context['previous'] = Athlete.objects.filter(sid__lt=self.object.sid,mannschaft=self.object.mannschaft).order_by("-sid").first()
        else:
            context['next'] = Athlete.objects.filter(sid__gt=self.object.sid,riege=self.object.riege).order_by("sid").first()
            context['previous'] = Athlete.objects.filter(sid__lt=self.object.sid,riege=self.object.riege).order_by("-sid").first()
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
        context['settings_dict'] = read_settings_xml()
        competition = Competition.objects.get(cid=self.request.GET.get('cid'))
        context['competition'] = competition
        discipline = Discipline.objects.get(did=self.request.GET.get('did'))
        context['discipline'] = discipline
        if int(context['settings_dict']['runde']) > 0:
            initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did, day=int(context['settings_dict']['runde'])).first()
        else:
            initial_grading = Grading.objects.filter(athlete_id=self.object.sid, competition_id=competition.cid, discipline_id=discipline.did).first()
        context['initial_grading'] = initial_grading
        context['not_changeable'] = True
        if context['settings_dict']['wk_type'] == 'mannschaft':
            context['next'] = Athlete.objects.filter(sid__gt=self.object.sid,mannschaft=self.object.mannschaft).order_by("sid").first()
            context['previous'] = Athlete.objects.filter(sid__lt=self.object.sid,mannschaft=self.object.mannschaft).order_by("-sid").first()
            print(context['next'], context['previous'])
        else:
            context['next'] = Athlete.objects.filter(sid__gt=self.object.sid,riege=self.object.riege).order_by("sid").first()
            context['previous'] = Athlete.objects.filter(sid__lt=self.object.sid,riege=self.object.riege).order_by("-sid").first()
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
        settings_dict = read_settings_xml()
        if settings_dict['wk_type'] == 'mannschaft':
            if self.request.GET.get('cid'):
                return Mannschaft_Comp.objects.filter(competition_id=self.request.GET.get('cid')).order_by(F("ranking").desc(nulls_last=True)).select_related("mannschaft", "competition")
            else:
                id = Competition.objects.first().cid if Competition.objects.first() else None
                return Mannschaft_Comp.objects.filter(competition_id=id).order_by(F("ranking").desc(nulls_last=True)).select_related("mannschaft", "competition")
        else:
            if self.request.GET.get('cid'):
                return Athlete_Comp.objects.filter(competition_id=self.request.GET.get('cid')).order_by(F("ranking").desc(nulls_last=True)).select_related("athlete", "competition")
            else:
                id = Competition.objects.first().cid if Competition.objects.first() else None
                return Athlete_Comp.objects.filter(competition_id=id).order_by(F("ranking").desc(nulls_last=True)).select_related("athlete", "competition")
    
    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.is_staff
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['settings_dict'] = read_settings_xml()
        for entry in context['ranking_list']:
            if context['settings_dict']['wk_type'] == 'mannschaft':
                if context['settings_dict']['runde'] and int(context['settings_dict']['runde']) > 0:
                    entry.disciplines = Discipline.objects.filter(comp_dis__competition_id=entry.competition.cid).order_by("did")
                    entry.athletes = Athlete.objects.filter(mannschaft_id=entry.mannschaft.mid).order_by("sid")
                    entry.athletes_disciplines = []
                    for athlete in entry.athletes:
                        athlete_dict = {'vorname': athlete.vorname, 'nachname': athlete.nachname, 'disciplines': []}
                        for discipline in entry.disciplines:
                            grading = Grading.objects.filter(athlete_id=athlete.sid, competition_id=entry.competition.cid, discipline_id=discipline.did, day=int(context['settings_dict']['runde'])).first()
                            if grading is not None:
                                athlete_dict['disciplines'].append({'discipline': discipline.bezeichnung, 'score': grading.score})
                            else:
                                athlete_dict['disciplines'].append({'discipline': discipline.bezeichnung, 'score': None})
                        entry.athletes_disciplines.append(athlete_dict)
                    entry.team_scores = []
                    for discipline in entry.disciplines:
                        team_score = Mannschaft_Grading.objects.filter(mannschaft_id=entry.mannschaft.mid, competition_id=entry.competition.cid, discipline_id=discipline.did, day=int(context['settings_dict']['runde'])).first()
                        if team_score is not None:
                            entry.team_scores.append({'discipline': discipline.bezeichnung, 'score': team_score.score})
                        else:
                            entry.team_scores.append({'discipline': discipline.bezeichnung, 'score': None})
                else:
                    entry.disciplines = Mannschaft_Grading.objects.filter(mannschaft_id=entry.mannschaft.mid, competition_id=entry.competition.cid).order_by("discipline_id").select_related("discipline")
            else:
                if context['settings_dict']['runde'] and int(context['settings_dict']['runde']) > 0:
                    entry.disciplines = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, day=int(context['settings_dict']['runde'])).order_by("discipline_id").select_related("discipline")
                else:
                    entry.disciplines = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid).order_by("discipline_id").select_related("discipline")
        context['competitions'] = Competition.objects.all().order_by("cid")
        if self.request.GET.get('cid'):
            context['selected_competition_id'] = self.request.GET.get('cid')
        else:
            context['selected_competition_id'] = context['competitions'].first().cid if context['competitions'] else None
        context['selected_competition_name'] = Competition.objects.get(cid=context['selected_competition_id']).name
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
        settings_dict = read_settings_xml()
        if int(settings_dict['runde']) > 0:
            grading = Grading.objects.get(athlete_id=athlete_id, competition_id=request.POST["cid"], discipline_id=request.POST["did"], day=int(settings_dict['runde']))
        else:
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
        if int(settings_dict['runde']) > 0:
            grading = Grading(athlete_id=athlete_id, competition_id=request.POST["cid"], discipline_id=request.POST["did"], kari1=request.POST["kari1"], kari2=request.POST["kari2"], kari3=request.POST["kari3"], kari4=request.POST["kari4"], kari5=request.POST["kari5"], ewert=request.POST["ewert"], awert=request.POST["awert"], dwert=request.POST["dwert"], score=request.POST["score"], day=int(settings_dict['runde']))
        else:
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
        if (settings_dict['wk_type'] == 'einzel' and athlete_comp.competition.vier_aus_sechs):
            totalscore = Grading.objects.filter(athlete_id=athlete_id, competition_id=request.POST["cid"]).order_by('-score').values_list('score', flat=True)[:4]
            totalscore = round(sum(totalscore),3)
        else:
            totalscore = Grading.objects.filter(athlete_id=athlete_id, competition_id=request.POST["cid"]).aggregate(Sum('score'))['score__sum']
        if int(settings_dict['runde']) == 2:
            athlete_comp.score2 = totalscore
        else:            
            athlete_comp.score = totalscore
        athlete_comp.save()

        # Ranking aktualisieren
        athlete_comps = Athlete_Comp.objects.filter(competition_id=request.POST["cid"],athlete__dbid=request.POST["dbid"],athlete__ak=False).annotate(total_score=F('score') + F('score2')).order_by('-total_score')
        ranking = 1
        i = 1
        for ac in athlete_comps:
            if i == 1:
                ac.ranking = ranking
                previous_score = ac.total_score
            else:
                if previous_score != ac.total_score:
                    if ac.total_score is not None:
                        ranking = i
                    else:
                        ranking = None
                    previous_score = ac.total_score
                ac.ranking = ranking
            ac.save()
            i += 1

        # Mannschaftswertung aktualisieren, falls es sich um einen Mannschaftswettkampf handelt
        if settings_dict['wk_type'] == 'mannschaft' and not athlete_comp.athlete.ak:
            # Disziplinenwertung aktualisieren
            if int(settings_dict['runde']) > 0:
                team_score = Grading.objects.filter(competition_id=request.POST["cid"], athlete__mannschaft_id=athlete_comp.athlete.mannschaft.mid, discipline_id=request.POST["did"], day=int(settings_dict['runde']), athlete__ak=False).order_by('-score').values_list('score', flat=True)[:3]
            else:
                team_score = Grading.objects.filter(competition_id=request.POST["cid"], athlete__mannschaft_id=athlete_comp.athlete.mannschaft.mid, discipline_id=request.POST["did"], athlete__ak=False).order_by('-score').values_list('score', flat=True)[:3]
            team_score = round(sum(team_score),3)
            
            try:
                if int(settings_dict['runde']) > 0:
                    mannschaft_grading = Mannschaft_Grading.objects.get(competition_id=request.POST["cid"], discipline_id=request.POST["did"], mannschaft__mid=athlete_comp.athlete.mannschaft.mid, day=int(settings_dict['runde']))
                else:                
                    mannschaft_grading = Mannschaft_Grading.objects.get(competition_id=request.POST["cid"], discipline_id=request.POST["did"], mannschaft__mid=athlete_comp.athlete.mannschaft.mid)
                mannschaft_grading.score = team_score
                
            except Mannschaft_Grading.DoesNotExist:
                if int(settings_dict['runde']) > 0:
                    mannschaft_grading = Mannschaft_Grading(competition_id=request.POST["cid"], discipline_id=request.POST["did"], mannschaft_id=athlete_comp.athlete.mannschaft.mid, score=team_score, day=int(settings_dict['runde']))
                else:
                    mannschaft_grading = Mannschaft_Grading(competition_id=request.POST["cid"], discipline_id=request.POST["did"], mannschaft_id=athlete_comp.athlete.mannschaft.mid, score=team_score)

            mannschaft_grading.save()

            # Gesamtwertung aktualisieren
            if (athlete_comp.competition.vier_aus_sechs):
                if int(settings_dict['runde']) > 0:
                    total_team_score = Mannschaft_Grading.objects.filter(competition_id=request.POST["cid"], mannschaft_id=athlete_comp.athlete.mannschaft.mid, day=int(settings_dict['runde'])).order_by('-score').values_list('score', flat=True)[:4]
                else:
                    total_team_score = Mannschaft_Grading.objects.filter(competition_id=request.POST["cid"], mannschaft_id=athlete_comp.athlete.mannschaft.mid).order_by('-score').values_list('score', flat=True)[:4]
                total_team_score = sum(total_team_score)
            else:
                if int(settings_dict['runde']) > 0:
                    total_team_score = Mannschaft_Grading.objects.filter(competition_id=request.POST["cid"], mannschaft_id=athlete_comp.athlete.mannschaft.mid, day=int(settings_dict['runde'])).aggregate(Sum('score'))['score__sum']
                else:
                    total_team_score = Mannschaft_Grading.objects.filter(competition_id=request.POST["cid"], mannschaft_id=athlete_comp.athlete.mannschaft.mid).aggregate(Sum('score'))['score__sum']
            
            try:
                mannschaft_comp = Mannschaft_Comp.objects.get(competition_id=request.POST["cid"], mannschaft_id=athlete_comp.athlete.mannschaft.mid)
                if int(settings_dict['runde']) is None or int(settings_dict['runde']) < 2:
                    mannschaft_comp.score_day1 = total_team_score
                elif int(settings_dict['runde']) == 2:
                    mannschaft_comp.score_day2 = total_team_score
                else:
                    return render(
                        request,
                        "grading/grade.html",
                        {
                            "athlete": get_object_or_404(Athlete, pk=athlete_id),
                            "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                            "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                            "initial_grading": grading,
                            "settings_dict": read_settings_xml(),
                            "error_message": f"Die Runden-Einstellung ist falsch. Die Mannschaftswertung kann nicht gespeichert werden.",
                        },
                    )
                if mannschaft_comp.score_day1 is None:
                    mannschaft_comp.score_day1 = 0
                if mannschaft_comp.score_day2 is None:
                    mannschaft_comp.score_day2 = 0
                mannschaft_comp.score = mannschaft_comp.score_day1 + mannschaft_comp.score_day2 - mannschaft_comp.abzug
            except Mannschaft_Comp.DoesNotExist:
                if int(settings_dict['runde']) is None or int(settings_dict['runde']) < 2:
                    mannschaft_comp = Mannschaft_Comp(competition_id=request.POST["cid"], mannschaft_id=athlete_comp.athlete.mannschaft.mid, score_day1=total_team_score, score_day2=0, score=total_team_score)
                elif int(settings_dict['runde']) == 2:
                    mannschaft_comp = Mannschaft_Comp(competition_id=request.POST["cid"], mannschaft_id=athlete_comp.athlete.mannschaft.mid, score_day1=0, score_day2=total_team_score, score=total_team_score)
                else:
                    return render(
                        request,
                        "grading/grade.html",
                        {
                            "athlete": get_object_or_404(Athlete, pk=athlete_id),
                            "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                            "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                            "initial_grading": grading,
                            "settings_dict": read_settings_xml(),
                            "error_message": f"Die Runden-Einstellung ist falsch. Die Mannschaftswertung kann nicht gespeichert werden.",
                        },
                    )
            mannschaft_comp.save()

            # Ranking aktualisieren
            mannschaft_comps = Mannschaft_Comp.objects.filter(competition_id=request.POST["cid"],mannschaft__dbid=request.POST["dbid"]).order_by('-score')
            ranking = 1
            i = 1
            for mc in mannschaft_comps:
                if i == 1:
                    mc.ranking = ranking
                    previous_score = mc.score
                else:
                    if previous_score != mc.score:
                        if mc.score is not None:
                            ranking = i
                        else:
                            ranking = None
                        previous_score = mc.score
                    mc.ranking = ranking
                mc.save()
                i += 1

        # Didis Datenbank aktualisieren
        try:
            # Datenbankverbindung basierend auf dbid herstellen
            if request.POST["dbid"] == "1":
                db = MySQLdb.connect(host=settings_dict['db1_host'], user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'], port=int(settings_dict['db1_port']))
            elif request.POST["dbid"] == "2":
                db = MySQLdb.connect(host=settings_dict['db2_host'], user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'], port=int(settings_dict['db2_port']))        
            cursor = db.cursor()
            
            # Update Punktzahl
            if int(settings_dict['runde']) > 0:
                cursor.execute("UPDATE ergebnisse SET Leistung=%s, Punktzahl=%s WHERE Startnummer=%s AND DisziplinID=%s AND Runde=%s", (grading.score, grading.score, athlete_id, request.POST["did"], settings_dict['runde']))
            else:
                cursor.execute("UPDATE ergebnisse SET Leistung=%s, Punktzahl=%s WHERE Startnummer=%s AND DisziplinID=%s", (grading.score, grading.score, athlete_id, request.POST["did"]))
            db.commit()
            affected_rows = cursor.rowcount
            if affected_rows is None or affected_rows == 0:
                if int(settings_dict['runde']) > 0:
                    cursor.execute("INSERT INTO ergebnisse(Leistung,Punktzahl,Startnummer,DisziplinID,Runde) VALUES(%s,%s,%s,%s,%s)",(grading.score, grading.score, athlete_id, request.POST["did"], settings_dict['runde']))
                else:
                    cursor.execute("INSERT INTO ergebnisse(Leistung,Punktzahl,Startnummer,DisziplinID) VALUES(%s,%s,%s,%s)",(grading.score, grading.score, athlete_id, request.POST["did"]))
            
            # Update Gesamtpunktzahl
            if int(settings_dict['runde']) == 2:
                cursor.execute("UPDATE teilnehmer SET Gesamtpunktzahl2=%s WHERE Startnummer=%s", (totalscore, athlete_id))
            else:
                cursor.execute("UPDATE teilnehmer SET Gesamtpunktzahl=%s WHERE Startnummer=%s", (totalscore, athlete_id))
            
            # Update Ranking aller Teilnehmer im gleichen Wettkampf und der gleichen Datenbank
            athlete_comps = Athlete_Comp.objects.filter(competition_id=request.POST["cid"],athlete__dbid=request.POST["dbid"])
            for ac in athlete_comps:
                cursor.execute("UPDATE teilnehmer SET Rang=%s WHERE Startnummer=%s", (ac.ranking, ac.athlete_id))
            db.commit()
            

            # Update Mannschaftswertung in Didis Datenbank, falls es sich um einen Mannschaftswettkampf handelt
            if settings_dict['wk_type'] == 'mannschaft' and not athlete_comp.athlete.ak:
                # Update Disziplinwertung
                if int(settings_dict['runde']) > 0:
                    cursor.execute("UPDATE ergebnissemannschaft SET Punktzahl=%s WHERE Startnummer=%s AND DisziplinID=%s AND Runde=%s", (team_score, athlete_comp.athlete.mannschaft.mid, request.POST["did"], settings_dict['runde']))
                else:
                    cursor.execute("UPDATE ergebnissemannschaft SET Punktzahl=%s WHERE Startnummer=%s AND DisziplinID=%s", (team_score, athlete_comp.athlete.mannschaft.mid, request.POST["did"]))
                db.commit()
                affected_rows = cursor.rowcount
                if affected_rows is None or affected_rows == 0:
                    if int(settings_dict['runde']) > 0:
                        cursor.execute("INSERT INTO ergebnissemannschaft(Punktzahl,Startnummer,DisziplinID,Runde) VALUES(%s,%s,%s,%s)",(team_score, athlete_comp.athlete.mannschaft.mid, request.POST["did"], settings_dict['runde']))
                    else:
                        cursor.execute("INSERT INTO ergebnissemannschaft(Punktzahl,Startnummer,DisziplinID) VALUES(%s,%s,%s)",(team_score, athlete_comp.athlete.mannschaft.mid, request.POST["did"]))

                # Update Gesamtwertung
                cursor.execute("UPDATE mannschaft SET Tagespunktzahl1=%s, Tagespunktzahl2=%s, Endpunktzahl=%s WHERE StartnummerMannschaft=%s", (mannschaft_comp.score_day1,mannschaft_comp.score_day2,mannschaft_comp.score, athlete_comp.athlete.mannschaft.mid))
                
                # Update Ranking aller Mannschaften im gleichen Wettkampf
                mannschaft_comps = Mannschaft_Comp.objects.filter(competition_id=request.POST["cid"],mannschaft__dbid=request.POST["dbid"])
                for mc in mannschaft_comps:
                    cursor.execute("UPDATE mannschaft SET Rang=%s WHERE StartnummerMannschaft=%s", (mc.ranking, mc.mannschaft_id))
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
    if settings_dict['wk_type'] == 'mannschaft':
        next = Athlete.objects.filter(sid__gt=athlete_id,mannschaft=athlete_comp.athlete.mannschaft).order_by("sid").first()
        previous = Athlete.objects.filter(sid__lt=athlete_id,mannschaft=athlete_comp.athlete.mannschaft).order_by("-sid").first()
    else:
        next = Athlete.objects.filter(sid__gt=athlete_id,riege=athlete_comp.athlete.riege).order_by("sid").first()
        previous = Athlete.objects.filter(sid__lt=athlete_id,riege=athlete_comp.athlete.riege).order_by("-sid").first()    
    return render(
            request,
            "grading/grade.html",
            {
                "athlete": get_object_or_404(Athlete, pk=athlete_id),
                "competition": get_object_or_404(Competition, pk=request.POST.get("cid")),
                "discipline": get_object_or_404(Discipline, pk=request.POST.get("did")),
                "initial_grading": grading,
                "settings_dict": settings_dict,
                "next": next,
                "previous": previous,
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
    update_settings_xml({'wk_title':request.POST.get('wk_title', ''), 'wk_type':request.POST.get('wk_type', ''), 'runde':request.POST.get('runde','')})
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
    call_command('dumpdata', 'grading.Athlete', 'grading.Competition', 'grading.Discipline', 'grading.Comp_Dis', 'grading.Athlete_Comp', 'grading.Grading', 'grading.Permission', 'grading.Logs', 'grading.Mannschaft', 'grading.Mannschaft_Grading', indent=4, stdout=output)
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
    Mannschaft_Grading.objects.all().delete()
    Mannschaft_Comp.objects.all().delete()
    Athlete_Comp.objects.all().delete()
    Athlete.objects.all().delete()
    Mannschaft.objects.all().delete()
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
        c.execute("SELECT Name, Art, Runde FROM veranstaltung")
        row = c.fetchone()
        if row is not None:
            if row[1] == 0:
                row = (row[0], "einzel", str(row[2]))
            elif row[1] == 1:
                row = (row[0], "mannschaft", str(row[2]))
            update_settings_xml({'wk_title':row[0], 'wk_type':row[1], 'runde':row[2]})
            settings_dict = read_settings_xml()
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
        c.execute("SELECT WettkampfID, Wettkampfname, 4aus6 FROM wettkämpfe")
        for row in c.fetchall():
            competition = Competition(cid=row[0], name=row[1], vier_aus_sechs=row[2])
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
        if settings_dict['wk_type'] == 'mannschaft':
            # Mannschaften importieren
            c.execute("SELECT m.StartnummerMannschaft, v.VereinsName, m.MannschaftsNr, m.Abzug, m.Endpunktzahl, m.Rang, m.Tagespunktzahl1, m.Tagespunktzahl2, m.WettkampfId FROM mannschaft as m INNER JOIN vereine as v ON m.Verein=v.VereinsNummer ORDER BY m.StartnummerMannschaft")
            for row in c.fetchall():
                mannschaft = Mannschaft(mid=row[0], verein=row[1], mannschaftsnr=row[2], dbid=1)
                mannschaft.save()
                if row[3] is None:
                    row = (row[0], row[1], row[2], 0, row[4], row[5], row[6], row[7], row[8])
                mannschaft_comp = Mannschaft_Comp(mannschaft_id=row[0], competition_id=row[8], abzug=row[3], score=row[4], ranking=row[5], score_day1=row[6], score_day2=row[7])
                mannschaft_comp.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Mannschaften aus Datenbank 1 ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        )
    
    try:
        # Athleten und Athleten-Wettbewerbe-Zuordnung importieren
        if settings_dict['wk_type'] == 'mannschaft':
            c.execute("SELECT t.Startnummer, t.Vorname, t.Name, t.Jahrgang, v.VereinsName, m.WettkampfID, t.Gesamtpunktzahl, t.Rang, t.Riege, t.MannschaftsId, t.ak, t.Gesamtpunktzahl2 FROM teilnehmer as t INNER JOIN mannschaft as m ON t.MannschaftsId=m.StartnummerMannschaft INNER JOIN vereine as v ON m.Verein=v.VereinsNummer ORDER BY t.Startnummer")
        else:
            c.execute("SELECT t.Startnummer, t.Vorname, t.Name, t.Jahrgang, v.VereinsName, t.WettkampfId, t.Gesamtpunktzahl, t.Rang, t.Riege, t.ak FROM teilnehmer as t INNER JOIN vereine as v ON t.Verein=v.VereinsNummer ORDER BY t.Startnummer")
        for row in c.fetchall():
            if settings_dict['wk_type'] == 'mannschaft':
                athlete = Athlete(sid=row[0], vorname=row[1], nachname=row[2], geburtsjahr=row[3], verein=row[4], dbid=1, riege=row[8], mannschaft_id=row[9], ak=row[10])
            else:
                athlete = Athlete(sid=row[0], vorname=row[1], nachname=row[2], geburtsjahr=row[3], verein=row[4], dbid=1, riege=row[8], ak=row[9])
            athlete.save()
            if settings_dict['wk_type'] == 'mannschaft':
                athlete_comp = Athlete_Comp(athlete_id=row[0], competition_id=row[5], score=row[6], score2=row[11], ranking=row[7])
            else:
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
        # Einzelwertungen importieren
        if settings_dict['wk_type'] == 'mannschaft':
            c.execute("SELECT e.Startnummer, e.DisziplinID, e.Punktzahl, m.WettkampfID, e.runde FROM ergebnisse as e INNER JOIN teilnehmer as t ON e.Startnummer = t.Startnummer INNER JOIN mannschaft as m ON t.MannschaftsId = m.StartnummerMannschaft")
        else:
            c.execute("SELECT e.Startnummer, e.DisziplinID, e.Punktzahl, t.WettkampfId, e.runde FROM ergebnisse as e INNER JOIN teilnehmer as t ON e.Startnummer = t.Startnummer")
        for row in c.fetchall():
            # Überprüfen, ob Athlet bereits existiert, um Fehler zu vermeiden
            if Athlete.objects.filter(sid=row[0]).exists():
                if row[4] is None:
                    row = (row[0], row[1], row[2], row[3], 0)
                grading = Grading(athlete_id=row[0], competition_id=row[3], discipline_id=row[1], score=row[2], kari1=0, awert=-1*row[2], ewert=0, dwert=0, day=row[4])
                grading.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Einzelwertungen aus Datenbank 1 ist ein Fehler aufgetreten."
        return render(
            request,
            "grading/database.html",
            context,
        )
    
    try:
        if settings_dict['wk_type'] == 'mannschaft':
            # Mannschaftswertungen importieren
            c.execute("SELECT mg.Startnummer, mg.DisziplinID, mg.Punktzahl, mg.Runde, m.WettkampfID FROM ergebnissemannschaft as mg INNER JOIN mannschaft as m ON mg.Startnummer = m.StartnummerMannschaft")
            for row in c.fetchall():
                # Überprüfen, ob Mannschaft bereits existiert, um Fehler zu vermeiden
                if Mannschaft.objects.filter(mid=row[0]).exists():
                    mannschaft_grading = Mannschaft_Grading(mannschaft_id=row[0], competition_id=row[4], discipline_id=row[1], score=row[2], day=row[3])
                    mannschaft_grading.save()
    except:
        context = read_settings_xml()
        context['error_message'] = "Beim Importieren der Mannschaftswertungen aus Datenbank 1 ist ein Fehler aufgetreten."
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
            c.execute("SELECT WettkampfID, Wettkampfname, 4aus6 FROM wettkämpfe")
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
                    competition = Competition(cid=row[0], name=row[1], vier_aus_sechs=row[2])
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
            if settings_dict['wk_type'] == 'mannschaft':
                # Mannschaften importieren
                c.execute("SELECT m.StartnummerMannschaft, v.VereinsName, m.MannschaftsNr, m.Abzug, m.Endpunktzahl, m.Rang, m.Tagespunktzahl1, m.Tagespunktzahl2, m.WettkampfId FROM mannschaft as m INNER JOIN vereine as v ON m.Verein=v.VereinsNummer ORDER BY m.StartnummerMannschaft")
                for row in c.fetchall():
                    # Überprüfen, ob Mannschaft bereits existiert                
                    if Mannschaft.objects.filter(mid=row[0]).exists():
                        context = read_settings_xml()
                        context['error_message'] = f"Mannschaft mit ID {row[0]} existiert bereits. Bitte überprüfen Sie die Datenbank 2 auf Duplikate oder Inkonsistenzen."
                        return render(
                            request,
                            "grading/database.html",
                            context,
                        )
                    else:
                        mannschaft = Mannschaft(mid=row[0], verein=row[1], mannschaftsnr=row[2], dbid=2)
                        mannschaft.save()
                        if row[3] is None:
                            row = (row[0], row[1], row[2], 0, row[4], row[5], row[6], row[7], row[8])
                        mannschaft_comp = Mannschaft_Comp(mannschaft_id=row[0], competition_id=row[8], abzug=row[3], score=row[4], ranking=row[5], score_day1=row[6], score_day2=row[7])
                        mannschaft_comp.save()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der Mannschaften aus Datenbank 2 ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            )

        try:
            # Athleten und Athleten-Wettbewerbe-Zuordnung importieren
            if settings_dict['wk_type'] == 'mannschaft':
                c.execute("SELECT t.Startnummer, t.Vorname, t.Name, t.Jahrgang, v.VereinsName, m.WettkampfID, t.Gesamtpunktzahl, t.Rang, t.Riege, t.MannschaftsId, t.ak, t.Gesamtpunktzahl2 FROM teilnehmer as t INNER JOIN mannschaft as m ON t.MannschaftsId=m.StartnummerMannschaft INNER JOIN vereine as v ON m.Verein=v.VereinsNummer ORDER BY t.Startnummer")
            else:
                c.execute("SELECT t.Startnummer, t.Vorname, t.Name, t.Jahrgang, v.VereinsName, t.WettkampfId, t.Gesamtpunktzahl, t.Rang, t.Riege, t.ak FROM teilnehmer as t INNER JOIN vereine as v ON t.Verein=v.VereinsNummer ORDER BY t.Startnummer")
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
                    if settings_dict['wk_type'] == 'mannschaft':
                        athlete = Athlete(sid=row[0], vorname=row[1], nachname=row[2], geburtsjahr=row[3], verein=row[4], dbid=2, riege=row[8], mannschaft_id=row[9], ak=row[10])
                    else: 
                        athlete = Athlete(sid=row[0], vorname=row[1], nachname=row[2], geburtsjahr=row[3], verein=row[4], dbid=2, riege=row[8], ak=row[9])
                    athlete.save()
                    if settings_dict['wk_type'] == 'mannschaft':
                        athlete_comp = Athlete_Comp(athlete_id=row[0], competition_id=row[5], score=row[6], score2=row[11], ranking=row[7])
                    else:
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
            # Einzelwertungen importieren
            if settings_dict['wk_type'] == 'mannschaft':
                c.execute("SELECT e.Startnummer, e.DisziplinID, e.Punktzahl, m.WettkampfID, e.runde FROM ergebnisse as e INNER JOIN teilnehmer as t ON e.Startnummer = t.Startnummer INNER JOIN mannschaft as m ON t.MannschaftsId = m.StartnummerMannschaft")
            else:
                c.execute("SELECT e.Startnummer, e.DisziplinID, e.Punktzahl, t.WettkampfID, e.runde FROM ergebnisse as e INNER JOIN teilnehmer as t ON e.Startnummer = t.Startnummer")
            for row in c.fetchall():
                # Überprüfen, ob Athlet bereits existiert, um Fehler zu vermeiden
                if Athlete.objects.filter(sid=row[0]).exists():
                    if row[4] is None:
                        row = (row[0], row[1], row[2], row[3], 0)
                    grading = Grading(athlete_id=row[0], competition_id=row[3], discipline_id=row[1], score=row[2], kari1=0, awert=-1*row[2], runde=row[4])
                    grading.save()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der EinzelWertungen aus Datenbank 2 ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            )
        
        try:
            if settings_dict['wk_type'] == 'mannschaft':
                # Mannschaftswertungen importieren
                c.execute("SELECT mg.Startnummer, mg.DisziplinID, mg.Punktzahl, mg.Runde, m.WettkampfID FROM ergebnissemannschaft as mg INNER JOIN mannschaft as m ON mg.Startnummer = m.StartnummerMannschaft")
                for row in c.fetchall():
                    # Überprüfen, ob Mannschaft bereits existiert, um Fehler zu vermeiden
                    if Mannschaft.objects.filter(mid=row[0]).exists():
                        mannschaft_grading = Mannschaft_Grading(mannschaft_id=row[0], competition_id=row[4], discipline_id=row[1], score=row[2], day=row[3])
                        mannschaft_grading.save()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Importieren der Mannschaftswertungen aus Datenbank 2 ist ein Fehler aufgetreten."
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

## Die Funktion database_clean_duplicates bereinigt die Ergebnisse-Tabelle in Didis Datenbank
# von Duplikaten, die dort ungewünschter Weise hineingeschrieben werden ##
@login_required
def database_clean_duplicates(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    settings_dict = read_settings_xml()
    if settings_dict['db2_host'] is None:
        length = 2
    else:
        length = 3

    for i in range(1,length):
        try:
            # Datenbankverbindung herstellen
            if i==1:
                db = MySQLdb.connect(host=settings_dict['db1_host'], port=int(settings_dict['db1_port']), user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'])
            else:
                db = MySQLdb.connect(host=settings_dict['db2_host'], port=int(settings_dict['db2_port']), user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'])
            c = db.cursor()
        except:
            context = settings_dict
            context['error_message'] = "Fehler beim Verbinden mit Datenbank "+ str(i) + ". Bitte überprüfen Sie die Einstellungen."
            return render(
                request,
                "grading/database.html",
                context,
            )
        try:
            # Einzel-Ergebnisse laden
            c.execute("SELECT DISTINCT Startnummer, DisziplinID, Leistung, Punktzahl, Runde FROM ergebnisse")
            results = c.fetchall()
            c.execute("DELETE FROM ergebnisse")
            db.commit()
            for row in results:
                c.execute("INSERT INTO ergebnisse(Startnummer,DisziplinID,Leistung,Punktzahl,Runde) VALUES(%s,%s,%s,%s,%s)",(row[0],row[1],row[2],row[3],row[4]))
            db.commit()
            if settings_dict['wk_type'] == 'einzel':
                c.close()
        except:
            context = settings_dict
            context['error_message'] = "Beim Löschen der Einzelergebnis-Duplikate aus Datenbank " + str(i) + " ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            )
        if settings_dict['wk_type'] == 'mannschaft':
            try:
                # Mannschafts-Ergebnisse laden
                c.execute("SELECT DISTINCT Startnummer, DisziplinID, Punktzahl, Runde FROM ergebnissemannschaft")
                results = c.fetchall()
                c.execute("DELETE FROM ergebnissemannschaft")
                db.commit()
                for row in results:
                    c.execute("INSERT INTO ergebnissemannschaft(Startnummer,DisziplinID,Punktzahl,Runde) VALUES(%s,%s,%s,%s)",(row[0],row[1],row[2],row[3]))
                db.commit()
                c.close()
            except:
                context = read_settings_xml()
                context['error_message'] = "Beim Löschen der Mannschaftsergebnis-Duplikate aus Datenbank " + str(i) + " ist ein Fehler aufgetreten."
                return render(
                    request,
                    "grading/database.html",
                    context,
                )
    context = settings_dict
    context['success_message'] = "Löschen der Duplikate erfolgreich."
    return render(
        request,
        "grading/database.html",
        context,
    )

@login_required
def database_reset_grading(request):
    user = request.user
    if not (user.is_superuser or user.is_staff):
        return HttpResponseRedirect(reverse("grading:database"))
    settings_dict = read_settings_xml()
    if settings_dict['db2_host'] is None:
        length = 2
    else:
        length = 3

    for i in range(1,length):
        try:
            # Datenbankverbindung herstellen
            if i==1:
                db = MySQLdb.connect(host=settings_dict['db1_host'], port=int(settings_dict['db1_port']), user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'])
            else:
                db = MySQLdb.connect(host=settings_dict['db2_host'], port=int(settings_dict['db2_port']), user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'])
            c = db.cursor()
        except:
            context = read_settings_xml()
            context['error_message'] = "Fehler beim Verbinden mit Datenbank "+ str(i) + ". Bitte überprüfen Sie die Einstellungen."
            return render(
                request,
                "grading/database.html",
                context,
            )
        try:
            # Ergebnisse aus Django-Datenbank laden, die in Datenbank i stehen sollten
            grading = Grading.objects.filter(athlete__dbid=i)
            # Check, ob Ergebnisse in Didis Datenbank vorhanden sind und updaten, wenn nicht vorhanden oder 0
            for g in grading:
                c.execute("SELECT Punktzahl FROM ergebnisse WHERE Startnummer=%s AND DisziplinID=%s AND Runde=%s", (g.athlete_id, g.discipline_id, g.day))
                result = c.fetchone()
                if result is None or result[0] == 0:
                    if result is not None:
                        c.execute("DELETE FROM ergebnisse WHERE Startnummer=%s AND DisziplinID=%s AND Runde=%s", (g.athlete_id, g.discipline_id, g.day))
                    c.execute("INSERT INTO ergebnisse(Startnummer,DisziplinID,Leistung,Punktzahl,Runde) VALUES(%s,%s,%s,%s,%s)",(g.athlete_id, g.discipline_id, g.score, g.score, g.day))
            db.commit()
            c.close()
        except:
            context = read_settings_xml()
            context['error_message'] = "Beim Übertragen der Ergebnisse in Datenbank " + str(i) + " ist ein Fehler aufgetreten."
            return render(
                request,
                "grading/database.html",
                context,
            )
    context = read_settings_xml()
    context['success_message'] = "Übertragen der Ergebnisse erfolgreich."
    return render(
        request,
        "grading/database.html",
        context,
    )

@login_required
def team_deduction(request):

    user = request.user
    if not (user.is_superuser or user.is_staff):
        riegen_list= Athlete_Comp.objects.filter(athlete__mannschaft__mid=request.POST["mid"]).order_by("athlete_id","competition_id").select_related("athlete", "competition")
        if riegen_list is not None:
            for entry in riegen_list:
                    # alle Disziplinen des Wettkampfs
                    entry.disciplines = Comp_Dis.objects.filter(competition_id=entry.competition.cid).order_by("discipline_id").select_related("discipline")
                    # bereits vorhandene Wertungen
                    entry.grading = []
                    for d in entry.disciplines:
                        d.score = None
                        d.allowed_to_grade = d.allowed_to_grade(request.user.id)
                        if int(settings_dict['runde']) > 0:
                            grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did, day=int(settings_dict['runde'])).first()
                        else:
                            grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did).first()
                        if grading is not None and grading.score > 0:
                            d.score = grading.score
        competitions = Competition.objects.all().order_by("cid")
        allowed_mids = [mannschaft.mid for mannschaft in Mannschaft.objects.order_by("mid").all() if mannschaft.allowed_to_grade(request.user.id)]
        riegen = Mannschaft.objects.filter(mid__in=allowed_mids).values_list('mid', flat=True).distinct().order_by('mid')
        selected_riege_data = Mannschaft_Comp.objects.filter(mannschaft_id=request.POST.get('mid')).select_related("mannschaft", "competition").first()
        if not selected_riege_data.mannschaft.allowed_to_grade(request.user.id):
            selected_riege_data = None
        return render(
            request,
            "grading/riegen.html",
            {
                "riegen_list": riegen_list,
                "competitions": competitions,
                "riegen": riegen,
                "selected_riege": request.POST["mid"],
                "settings_dict": settings_dict,
                "selected_riege_data": selected_riege_data,
                "error_message": "Sie haben keine Berechtigung, diese Wertung zu ändern.",
            },
        )
    settings_dict = read_settings_xml()

    # Mannschaftswertung aktualisieren, falls es sich um einen Mannschaftswettkampf handelt
    try:
        if settings_dict['wk_type'] == 'mannschaft': 
            try:
                mannschaft_comp = Mannschaft_Comp.objects.get(competition_id=request.POST["cid"], mannschaft_id=request.POST["mid"])
                print(request.POST["abzug"])
                mannschaft_comp.abzug = float(request.POST["abzug"])
                print(mannschaft_comp.abzug)
                mannschaft_comp.score = mannschaft_comp.score_day1 + mannschaft_comp.score_day2 - mannschaft_comp.abzug
                if mannschaft_comp.score < 0:
                    mannschaft_comp.score = 0
            except Mannschaft_Comp.DoesNotExist:
                    mannschaft_comp = Mannschaft_Comp(competition_id=request.POST["cid"], mannschaft_id=request.POST["mid"], score_day1=0, score_day2=0, abzug=int(request.POST["abzug"]), score=0)
            
            mannschaft_comp.save()

            # Ranking aktualisieren
            mannschaft_comps = Mannschaft_Comp.objects.filter(competition_id=request.POST["cid"],mannschaft__dbid=mannschaft_comp.mannschaft.dbid).order_by('-score')
            ranking = 1
            i = 1
            for mc in mannschaft_comps:
                if i == 1:
                    mc.ranking = ranking
                    previous_score = mc.score
                else:
                    if previous_score != mc.score:
                        if mc.score is not None:
                            ranking = i
                        else:
                            ranking = None
                        previous_score = mc.score
                    mc.ranking = ranking
                mc.save()
                i += 1

            # Didis Datenbank aktualisieren
            try:
                # Datenbankverbindung basierend auf dbid herstellen
                if mannschaft_comp.mannschaft.dbid == 1:
                    db = MySQLdb.connect(host=settings_dict['db1_host'], user=settings_dict['db1_user'], passwd=settings_dict['db1_password'], db=settings_dict['db1_name'], port=int(settings_dict['db1_port']))
                elif mannschaft_comp.mannschaft.dbid == 2:
                    db = MySQLdb.connect(host=settings_dict['db2_host'], user=settings_dict['db2_user'], passwd=settings_dict['db2_password'], db=settings_dict['db2_name'], port=int(settings_dict['db2_port']))        
                cursor = db.cursor()

                # Update Mannschaftswertung in Didis Datenbank
                # Update Gesamtwertung
                cursor.execute("UPDATE mannschaft SET Abzug=%s, Endpunktzahl=%s WHERE StartnummerMannschaft=%s", (mannschaft_comp.abzug,mannschaft_comp.score, request.POST["mid"]))
                
                # Update Ranking aller Mannschaften im gleichen Wettkampf
                mannschaft_comps = Mannschaft_Comp.objects.filter(competition_id=request.POST["cid"],mannschaft__dbid=mannschaft_comp.mannschaft.dbid)
                for mc in mannschaft_comps:
                    cursor.execute("UPDATE mannschaft SET Rang=%s WHERE StartnummerMannschaft=%s", (mc.ranking, mc.mannschaft_id))
                db.commit()
                cursor.close()
            except MySQLdb.Error as e:
                riegen_list= Athlete_Comp.objects.filter(athlete__mannschaft__mid=request.POST["mid"]).order_by("athlete_id","competition_id").select_related("athlete", "competition")
                if riegen_list is not None:
                    for entry in riegen_list:
                            # alle Disziplinen des Wettkampfs
                            entry.disciplines = Comp_Dis.objects.filter(competition_id=entry.competition.cid).order_by("discipline_id").select_related("discipline")
                            # bereits vorhandene Wertungen
                            entry.grading = []
                            for d in entry.disciplines:
                                d.score = None
                                d.allowed_to_grade = d.allowed_to_grade(request.user.id)
                                if int(settings_dict['runde']) > 0:
                                    grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did, day=int(settings_dict['runde'])).first()
                                else:
                                    grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did).first()
                                if grading is not None and grading.score > 0:
                                    d.score = grading.score
                competitions = Competition.objects.all().order_by("cid")
                allowed_mids = [mannschaft.mid for mannschaft in Mannschaft.objects.order_by("mid").all() if mannschaft.allowed_to_grade(request.user.id)]
                riegen = Mannschaft.objects.filter(mid__in=allowed_mids).values_list('mid', flat=True).distinct().order_by('mid')
                selected_riege_data = Mannschaft_Comp.objects.filter(mannschaft_id=request.POST["mid"]).select_related("mannschaft", "competition").first()
                if not selected_riege_data.mannschaft.allowed_to_grade(request.user.id):
                    selected_riege_data = None
                return render(
                    request,
                    "grading/riegen.html",
                    {
                        "riegen_list": riegen_list,
                        "competitions": competitions,
                        "riegen": riegen,
                        "selected_riege": request.POST["mid"],
                        "settings_dict": settings_dict,
                        "selected_riege_data": selected_riege_data,
                        "error_message": f"Fehler beim Speichern des Abzugs in Didis Datenbank: {e}",
                    },
                )

            logs = Logs(user=request.user, ip=get_client_ip(request), competition_id=request.POST["cid"], log_text="Einmaliger Abzug bei Mannschaft "+str(request.POST["mid"])+" geändert.", log_date=timezone.now())
            logs.save()
    except (KeyError, ValueError):
        riegen_list= Athlete_Comp.objects.filter(athlete__mannschaft__mid=request.POST["mid"]).order_by("athlete_id","competition_id").select_related("athlete", "competition")
        if riegen_list is not None:
            for entry in riegen_list:
                    # alle Disziplinen des Wettkampfs
                    entry.disciplines = Comp_Dis.objects.filter(competition_id=entry.competition.cid).order_by("discipline_id").select_related("discipline")
                    # bereits vorhandene Wertungen
                    entry.grading = []
                    for d in entry.disciplines:
                        d.score = None
                        d.allowed_to_grade = d.allowed_to_grade(request.user.id)
                        if int(settings_dict['runde']) > 0:
                            grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did, day=int(settings_dict['runde'])).first()
                        else:
                            grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did).first()
                        if grading is not None and grading.score > 0:
                            d.score = grading.score
        competitions = Competition.objects.all().order_by("cid")
        allowed_mids = [mannschaft.mid for mannschaft in Mannschaft.objects.order_by("mid").all() if mannschaft.allowed_to_grade(request.user.id)]
        riegen = Mannschaft.objects.filter(mid__in=allowed_mids).values_list('mid', flat=True).distinct().order_by('mid')
        selected_riege_data = Mannschaft_Comp.objects.filter(mannschaft_id=request.POST["mid"]).select_related("mannschaft", "competition").first()
        if not selected_riege_data.mannschaft.allowed_to_grade(request.user.id):
            selected_riege_data = None

        return render(
            request,
            "grading/riegen.html",
            {
                "riegen_list": riegen_list,
                "competitions": competitions,
                "riegen": riegen,
                "selected_riege": request.POST["mid"],
                "settings_dict": settings_dict,
                "selected_riege_data": selected_riege_data,
                "error_message": "Fehlende oder ungültige Eingabe.",
            },
        )
    
    riegen_list= Athlete_Comp.objects.filter(athlete__mannschaft__mid=request.POST["mid"]).order_by("athlete_id","competition_id").select_related("athlete", "competition")
    if riegen_list is not None:
        for entry in riegen_list:
                # alle Disziplinen des Wettkampfs
                entry.disciplines = Comp_Dis.objects.filter(competition_id=entry.competition.cid).order_by("discipline_id").select_related("discipline")
                # bereits vorhandene Wertungen
                entry.grading = []
                for d in entry.disciplines:
                    d.score = None
                    d.allowed_to_grade = d.allowed_to_grade(request.user.id)
                    if int(settings_dict['runde']) > 0:
                        grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did, day=int(settings_dict['runde'])).first()
                    else:
                        grading = Grading.objects.filter(athlete_id=entry.athlete.sid, competition_id=entry.competition.cid, discipline_id=d.discipline.did).first()
                    if grading is not None and grading.score > 0:
                        d.score = grading.score
    competitions = Competition.objects.all().order_by("cid")
    allowed_mids = [mannschaft.mid for mannschaft in Mannschaft.objects.order_by("mid").all() if mannschaft.allowed_to_grade(request.user.id)]
    riegen = Mannschaft.objects.filter(mid__in=allowed_mids).values_list('mid', flat=True).distinct().order_by('mid')
    selected_riege_data = Mannschaft_Comp.objects.filter(mannschaft_id=request.POST["mid"]).select_related("mannschaft", "competition").first()
    if not selected_riege_data.mannschaft.allowed_to_grade(request.user.id):
        selected_riege_data = None
    return render(
            request,
            "grading/riegen.html",
            {
                "riegen_list": riegen_list,
                "competitions": competitions,
                "riegen": riegen,
                "selected_riege": request.POST["mid"],
                "settings_dict": settings_dict,
                "selected_riege_data": selected_riege_data,
                "success_message": "Abzug gespeichert.",
            },
        )  