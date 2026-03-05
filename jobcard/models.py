from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# -----------------------------
# CHOICES
# -----------------------------
LINE_CHOICES = [
    ('FL001', 'FL 001'),
    ('FL006', 'FL 006'),
    ('FL007', 'FL 007'),
    ('FL008', 'FL 008'),
    ('FL009', 'FL 009'),
    ('FL010', 'FL 010'),
    ('FL013', 'FL 013'),
    ('FL015', 'FL 015'),
    ('COPACK', 'CO-PACKING'),
]

SHIFT_CHOICES = [
    ('Day', 'Day Shift'),
    ('Night', 'Night Shift'),
]

# =====================================================
# FINAL JOBCARD (Permanent Record)
# =====================================================
class JobCard(models.Model):
    date = models.DateField(default=timezone.localdate, db_index=True)
    line = models.CharField(max_length=10, choices=LINE_CHOICES, db_index=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, db_index=True)

    wo_number = models.CharField(max_length=50)
    product_code = models.CharField(max_length=50)
    product_name = models.CharField(max_length=100)
    target_quantity = models.PositiveIntegerField(default=0)

    # ✅ LOCK FIELD (prevents duplicate submissions)
    is_submitted = models.BooleanField(default=False)

    # Hourly Output
    hour1 = models.PositiveIntegerField(default=0)
    hour2 = models.PositiveIntegerField(default=0)
    hour3 = models.PositiveIntegerField(default=0)
    hour4 = models.PositiveIntegerField(default=0)
    hour5 = models.PositiveIntegerField(default=0)
    hour6 = models.PositiveIntegerField(default=0)
    hour7 = models.PositiveIntegerField(default=0)
    hour8 = models.PositiveIntegerField(default=0)
    hour9 = models.PositiveIntegerField(default=0)
    hour10 = models.PositiveIntegerField(default=0)
    hour11 = models.PositiveIntegerField(default=0)

    # Rejects
    jar = models.PositiveIntegerField(default=0)
    cap = models.PositiveIntegerField(default=0)
    front_label = models.PositiveIntegerField(default=0)
    back_label = models.PositiveIntegerField(default=0)
    carton = models.PositiveIntegerField(default=0)
    sleeve = models.PositiveIntegerField(default=0)
    sticker = models.PositiveIntegerField(default=0)
    tube = models.PositiveIntegerField(default=0)
    packets = models.PositiveIntegerField(default=0)
    roll_on_ball = models.PositiveIntegerField(default=0)
    jar_pump = models.PositiveIntegerField(default=0)

    # Personnel
    operator_names = models.TextField()
    supervisor_names = models.TextField()
    line_captain_signature = models.CharField(max_length=100)
    supervisor_signature = models.CharField(max_length=100)

    # ---------- CALCULATED ----------
    def total_output(self):
        return sum([
            self.hour1, self.hour2, self.hour3, self.hour4, self.hour5,
            self.hour6, self.hour7, self.hour8, self.hour9, self.hour10,
            self.hour11
        ])

    def efficiency(self):
        if self.target_quantity == 0:
            return 0
        return round((self.total_output() / self.target_quantity) * 100, 1)

    # ---------- META ----------
    class Meta:
        ordering = ["-date", "line"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "line", "shift", "wo_number"],
                name="unique_jobcard_per_workorder"
            )
        ]
        indexes = [
            models.Index(fields=["date", "line", "shift"]),
        ]

    def __str__(self):
        return f"{self.date} | {self.product_name} | {self.line} | {self.shift}"


# =====================================================
# LIVE OPERATOR ENTRY (REALTIME TABLE)
# =====================================================
class TempSubmission(models.Model):
    operator = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField(default=timezone.localdate, db_index=True)
    line = models.CharField(max_length=10, choices=LINE_CHOICES, db_index=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, db_index=True)

    # Hourly
    hour1 = models.PositiveIntegerField(default=0)
    hour2 = models.PositiveIntegerField(default=0)
    hour3 = models.PositiveIntegerField(default=0)
    hour4 = models.PositiveIntegerField(default=0)
    hour5 = models.PositiveIntegerField(default=0)
    hour6 = models.PositiveIntegerField(default=0)
    hour7 = models.PositiveIntegerField(default=0)
    hour8 = models.PositiveIntegerField(default=0)
    hour9 = models.PositiveIntegerField(default=0)
    hour10 = models.PositiveIntegerField(default=0)
    hour11 = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    # ---------- CALCULATED ----------
    def total_output(self):
        return sum([
            self.hour1, self.hour2, self.hour3, self.hour4, self.hour5,
            self.hour6, self.hour7, self.hour8, self.hour9, self.hour10,
            self.hour11
        ])

    # ---------- META ----------
    class Meta:
        ordering = ["line", "shift"]

        constraints = [
            models.UniqueConstraint(
                fields=["operator", "date", "line", "shift"],
                name="unique_operator_submission"
            )
        ]

        indexes = [
            models.Index(fields=["date", "shift", "line"]),
        ]

    def __str__(self):
        name = self.operator.username if self.operator else "Anonymous"
        return f"{name} | {self.date} | {self.shift} | {self.line}"


# =====================================================
# SHIFT FINAL SNAPSHOT (Audit + History Table)
# =====================================================
class ShiftSubmission(models.Model):
    date = models.DateField(db_index=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, db_index=True)
    line = models.CharField(max_length=10, choices=LINE_CHOICES, db_index=True)

    aggregated_data = models.JSONField(default=list)
    supervisor_approved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

        constraints = [
            models.UniqueConstraint(
                fields=["date", "shift", "line"],
                name="unique_shift_submission"
            )
        ]

    def __str__(self):
        return f"{self.date} - {self.shift} - {self.line}"


# =====================================================
# HOUR LOCK SYSTEM
# =====================================================
class HourEntry(models.Model):
    hour = models.IntegerField()
    value = models.FloatField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # lock only if value exists AND is not zero
        if self.value not in [None, 0, 0.0]:
            self.is_locked = True
        super().save(*args, **kwargs)


class ActiveShift(models.Model):
    shift = models.CharField(max_length=10)
    date = models.DateField()

    def __str__(self):
        return f"{self.shift} — {self.date}"