from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


## Athlete: 
# sid - Sportler-ID (integer, unique),
#  vorname - String
#  nachname - String
#  geburtsjahr - Integer
#  verein - String,
#  dbid - Integert (optional, für die Zuordnung zwischen zwei Datenbanken in Didis Software)
# riege - Integer (optional, für die Zuordnung der Athleten zu Riegen
# mannschaft - ForeignKey zu Mannschaft (optional, alternative Möglichkeit zur Zuordnung der Athleten zu Mannschaften)
# ak - Boolean (optional, für die Kennzeichnung von Athleten, die außer Konkurenz an einem Wettkampf teilnehmen)
class Athlete(models.Model):
    sid = models.IntegerField(primary_key=True)
    vorname = models.CharField(max_length=100)
    nachname = models.CharField(max_length=100)
    geburtsjahr = models.IntegerField()
    verein = models.CharField(max_length=100)
    dbid = models.IntegerField(null=True, blank=True)
    riege = models.IntegerField(null=True, blank=True) # optionales Feld für die Riege des Athleten
    mannschaft = models.ForeignKey('Mannschaft', on_delete=models.SET_NULL, null=True, blank=True) # alternative Möglichkeit zur Zuordnung der Athleten zu Mannschaften
    ak = models.BooleanField(default=False) # optionales Feld für die Kennzeichnung von Athleten, die außer Konkurenz an einem Wettkampf teilnehmen

    def __str__(self):
        return f"{self.vorname} {self.nachname} ({self.geburtsjahr}), {self.verein}"
    
    def allowed_to_grade(self, user_id):
        user = User.objects.get(id=user_id)
        if user.is_superuser or user.is_staff:
            return True
        competitions = Athlete_Comp.objects.filter(athlete__sid=self.sid).values_list('competition', flat=True)
        for comp_id in competitions:
            comp_dis_list = Comp_Dis.objects.filter(competition__cid=comp_id)
            for comp_dis in comp_dis_list:
                if Permission.objects.filter(user__username=user.username, comp_dis=comp_dis).exists():
                    return True
        return False

## Discipline:
# did - Disziplin-ID (integer, unique),
# bezeichnung - String (z.B. "Sprung", "Boden", etc.)
# einheit - String (z.B. "Punkte", "Sekunden", etc.)
# gewichtung - Float (noch nicht implementiert!) 
class Discipline(models.Model):
    did = models.IntegerField(primary_key=True)
    bezeichnung = models.CharField(max_length=100)
    einheit = models.CharField(max_length=20)
    gewichtung = models.FloatField()

    def __str__(self):
        return f"{self.bezeichnung} ({self.einheit}), Gewichtung: {self.gewichtung}"

## Competition:
# cid - Wettkampf-ID (integer, unique),
# name - String (z.B. "Landesmeisterschaft 2024", "Vereinswettkampf 2024", etc.)
# vier_aus_sechs - Boolean (Einstellung, ob die 4 aus 6 Regel angewendet werden soll, d.h. ob bei der Bewertung nur die 4 besten Geräte-Wertungen gezählt werden sollen)    
class Competition(models.Model):
    cid = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    vier_aus_sechs = models.BooleanField(default=False) # Einstellung, ob die 4 aus 6 Regel angewendet werden soll

    def __str__(self):
        return f"{self.name}"
    
    def allowed_to_grade(self, user_id):
        user = User.objects.get(id=user_id)
        if user.is_superuser or user.is_staff:
            return True
        comp_dis_list = Comp_Dis.objects.filter(competition__cid=self.cid)
        for comp_dis in comp_dis_list:
            if Permission.objects.filter(user__username=user.username, comp_dis=comp_dis).exists():
                return True
        return False

## Comp_Dis: Verknüpfungstabelle zwischen Competition und Discipline, da ein Wettkampf mehrere Disziplinen haben kann und eine Disziplin in mehreren Wettkämpfen vorkommen kann    
class Comp_Dis(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE)
    max_score = models.FloatField()

    def __str__(self):
        return f"{self.competition} - {self.discipline}"
    
    def allowed_to_grade(self, user_id):
        user = User.objects.get(id=user_id)
        if user.is_superuser or user.is_staff:
            return True
        elif Permission.objects.filter(user__username=user.username, comp_dis=self).exists():
                    return True
        return False

## Athlete_Comp: Verknüpfungstabelle zwischen Athlete und Competition, da ein Athlet an mehreren Wettkämpfen teilnehmen kann und ein Wettkampf mehrere Athleten haben kann. 
# Hier werden auch die Gesamtpunktzahl und die Platzierung des Athleten in diesem Wettkampf gespeichert.    
class Athlete_Comp(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    score = models.FloatField(null=True, blank=True)
    score2 = models.FloatField(null=True, blank=True) # Punktzahl des Athleten am zweiten Wettkampftag (falls es einen zweiten Wettkampftag gibt)
    ranking = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.athlete} in {self.competition}"

## Grading: Hier werden die Bewertungen der Athleten in den einzelnen Disziplinen und Wettkämpfen gespeichert.
class Grading(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    kari1 = models.FloatField()
    kari2 = models.FloatField(null=True, blank=True)
    kari3 = models.FloatField(null=True, blank=True)
    kari4 = models.FloatField(null=True, blank=True)
    kari5 = models.FloatField(null=True, blank=True)
    awert = models.FloatField(null=True, blank=True)
    ewert = models.FloatField()
    dwert = models.FloatField()
    score = models.FloatField()
    day = models.IntegerField(default=0) # Tag der Bewertung, z.B. 1 für den ersten Wettkampftag, 2 für den zweiten Wettkampftag (falls es einen zweiten Wettkampftag gibt)

    def __str__(self):
        return f"{self.athlete} - {self.discipline}: {self.score} in {self.competition}"

## Permission: Hier werden die Berechtigungen der Benutzer gespeichert, um bestimmte Disziplinen in bestimmten Wettkämpfen bewerten zu dürfen. 
# Ein Benutzer kann Berechtigungen für mehrere Comp_Dis Einträge haben, und ein Comp_Dis Eintrag kann Berechtigungen für mehrere Benutzer haben.    
class Permission(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    comp_dis = models.ForeignKey(Comp_Dis, on_delete=models.CASCADE)

    def __str__(self):
        return f"Permission for {self.user} on {self.comp_dis}"

## Logs: Hier werden die Logs gespeichert, um nachvollziehen zu können, wer wann welche Aktionen in der Software durchgeführt hat.    
class Logs(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    ip = models.GenericIPAddressField(null=True, blank=True)
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, null=True, blank=True)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, null=True, blank=True)
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, null=True, blank=True)
    log_text = models.CharField(max_length=500)
    log_date = models.DateTimeField('date logged', default=timezone.now)
   
    def __str__(self):
        return f"{self.log_date} - {self.user}: {self.log_text}"
    
## Mannschaft: Hier werden die Mannschaften gespeichert, falls die Funktion der Mannschaftswertung gewünscht ist.
class Mannschaft(models.Model):
    mid = models.IntegerField(primary_key=True)
    verein = models.CharField(max_length=100)
    mannschaftsnr = models.IntegerField()
    dbid = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.verein} - Mannschaft {self.mannschaftsnr}"
    
    def allowed_to_grade(self, user_id):
        user = User.objects.get(id=user_id)
        if user.is_superuser or user.is_staff:
            return True
        competitions = Mannschaft_Comp.objects.filter(mannschaft__mid=self.mid).values_list('competition', flat=True)
        for comp_id in competitions:
            comp_dis_list = Comp_Dis.objects.filter(competition__cid=comp_id)
            for comp_dis in comp_dis_list:
                if Permission.objects.filter(user__username=user.username, comp_dis=comp_dis).exists():
                    return True
        return False

## Mannschaft_Comp: Verknüpfungstabelle zwischen Mannschaft und Competition, da eine Mannschaft an mehreren Wettkämpfen teilnehmen kann und ein Wettkampf mehrere Mannschaften haben kann.
# Hier werden auch die Gesamtpunktzahl und die Platzierung der Mannschaft in diesem Wettkampf gespeichert, sowie eventuelle Abzüge für die Mannschaftswertung und die Punktzahlen der Mannschaft an den einzelnen Wettkampftagen, falls es einen zweiten Wettkampftag gibt.   
class Mannschaft_Comp(models.Model):
    mannschaft = models.ForeignKey(Mannschaft, on_delete=models.CASCADE)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    abzug = models.FloatField(default=0) # Abzüge für die Mannschaftswertung
    score_day1 = models.FloatField(null=True, blank=True) # Punktzahl der Mannschaft am ersten Wettkampftag
    score_day2 = models.FloatField(null=True, blank=True) # Punktzahl der Mannschaft am zweiten Wettkampftag (falls es einen zweiten Wettkampftag gibt)
    score = models.FloatField(null=True, blank=True)
    ranking = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.mannschaft} in {self.competition}"

## Mannschaft_Grading: Hier werden die Bewertungen der Mannschaften in den einzelnen Disziplinen und Wettkämpfen gespeichert, falls die Funktion der Mannschaftswertung gewünscht ist.    
class Mannschaft_Grading(models.Model):
    mannschaft = models.ForeignKey(Mannschaft, on_delete=models.CASCADE)
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    score = models.FloatField()
    day = models.IntegerField(default=0) # Tag der Bewertung, z.B. 1 für den ersten Wettkampftag, 2 für den zweiten Wettkampftag (falls es einen zweiten Wettkampftag gibt)

    def __str__(self):
        return f"{self.mannschaft} - {self.discipline}: {self.score} in {self.competition}"