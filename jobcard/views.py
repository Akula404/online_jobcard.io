from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from .forms import TempSubmissionForm, JobCardForm, JobCardPrepopulateForm
from .models import TempSubmission, ShiftSubmission, JobCard, LINE_CHOICES
from datetime import timedelta
import csv
from .models import ActiveShift

# -----------------------------
# CSV EXPORT
# -----------------------------
def export_jobcards_csv(request):
    start_date = request.GET.get('start_date', timezone.localdate())
    end_date = request.GET.get('end_date', timezone.localdate())
    line = request.GET.get('line')
    shift = request.GET.get('shift')

    jobcards = JobCard.objects.filter(date__range=[start_date, end_date])
    if line:
        jobcards = jobcards.filter(line=line)
    if shift:
        jobcards = jobcards.filter(shift=shift)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="jobcards_{start_date}_to_{end_date}.csv"'

    writer = csv.writer(response)
    header = [
        'Date', 'Line', 'Shift', 'WO Number', 'Product Code', 'Product Name', 'Target Quantity',
        'Hour1','Hour2','Hour3','Hour4','Hour5','Hour6','Hour7','Hour8','Hour9','Hour10','Hour11',
        'Total Output',
        'Jar','Cap','Front Label','Back Label','Carton','Sleeve','Sticker','Tube','Packets','Roll On Ball','Jar Pump',
        'Operators','Supervisors'
    ]
    writer.writerow(header)

    for jc in jobcards:
        row = [
            jc.date, jc.line, jc.shift, jc.wo_number, jc.product_code, jc.product_name, jc.target_quantity,
            jc.hour1, jc.hour2, jc.hour3, jc.hour4, jc.hour5, jc.hour6, jc.hour7, jc.hour8, jc.hour9, jc.hour10, jc.hour11,
            jc.total_output(),
            jc.jar, jc.cap, jc.front_label, jc.back_label, jc.carton, jc.sleeve, jc.sticker, jc.tube, jc.packets, jc.roll_on_ball, jc.jar_pump,
            jc.operator_names, jc.supervisor_names
        ]
        writer.writerow(row)

    return response

# -----------------------------
# TEMP SUBMISSION (LIVE OPERATOR ENTRY)
# -----------------------------
def temp_submission(request):
    today = timezone.localdate()
    user = request.user if request.user.is_authenticated else None

    # ✅ ALWAYS follow supervisor-selected shift
    active = ActiveShift.objects.first()
    if active:
        shift = active.shift
        target_date = active.date
    else:
        shift = "Day"
        target_date = today

    lines = [l[0] for l in LINE_CHOICES]
    forms_data = []

    # ---------------- AJAX SAVE ----------------
    if request.method == "POST" and request.headers.get("x-requested-with") == "XMLHttpRequest":
        line = request.POST.get("line")

        obj, _ = TempSubmission.objects.get_or_create(
            operator=user,
            date=target_date,
            shift=shift,
            line=line
        )

        updated_fields = []

        for i in range(1, 12):
            field = f"hour{i}"
            new_val = request.POST.get(field)
            old_val = getattr(obj, field)

            if new_val in [None, ""]:
                continue

            try:
                new_val = float(new_val)
            except:
                continue

            if old_val not in [None, 0, 0.0]:
                return JsonResponse({"error": f"{field.upper()} already submitted and locked."}, status=403)

            if new_val == 0:
                continue

            setattr(obj, field, new_val)
            updated_fields.append(i)

        obj.save()
        return JsonResponse({"success": True, "updated": updated_fields})

    # ---------------- PAGE LOAD ----------------
    for line in lines:
        obj, _ = TempSubmission.objects.get_or_create(
            operator=user,
            date=target_date,
            shift=shift,
            line=line
        )

        form = TempSubmissionForm(instance=obj)
        forms_data.append((line, form, obj))

    return render(request, "temp_submission_form.html", {
        "forms_data": forms_data,
        "shift": shift
    })

# -----------------------------
# SUPERVISOR DASHBOARD
# -----------------------------
def supervisor_dashboard(request):
    today = timezone.localdate()

    # PRIORITY 1 → manual selection from dropdown
    selected_shift = request.GET.get("shift")

    if selected_shift:
        shift = selected_shift
        target_date = today if shift == "Day" else today - timedelta(days=1)

    else:
        # PRIORITY 2 → system active shift
        active = ActiveShift.objects.first()
        if active:
            shift = active.shift
            target_date = active.date
        else:
            shift = "Day"
            target_date = today

    submissions = TempSubmission.objects.filter(
        date=target_date,
        shift=shift
    ).order_by('line', 'operator')

    lines = [l[0] for l in LINE_CHOICES]
    global_locked_hours = []

    for h in range(1, 12):
        filled_lines = submissions.exclude(**{f"hour{h}__isnull": True}).exclude(**{f"hour{h}": 0}).values("line").distinct().count()
        if filled_lines >= len(lines):
            global_locked_hours.append(h)

    # =========================
    # AJAX REALTIME ENDPOINT
    # =========================
    if request.GET.get("ajax") == "1":

        dashboard_data = {}

        for sub in submissions:
            key = f"{sub.line}_{sub.shift}"

            if key not in dashboard_data:
                dashboard_data[key] = {
                    "hour_totals": [0]*11,
                    "total": 0
                }

            hours = [
                sub.hour1, sub.hour2, sub.hour3, sub.hour4, sub.hour5,
                sub.hour6, sub.hour7, sub.hour8, sub.hour9, sub.hour10, sub.hour11
            ]

            for i in range(11):
                dashboard_data[key]["hour_totals"][i] += hours[i] or 0

            dashboard_data[key]["total"] += sub.total_output()

        return JsonResponse({
            "global_locked_hours": global_locked_hours,
            "dashboard_data": dashboard_data
        })

    # =========================
    # NORMAL PAGE LOAD
    # =========================
    dashboard_data = {}

    for sub in submissions:
        key = f"{sub.line}_{sub.shift}"
        if key not in dashboard_data:
            dashboard_data[key] = {"submissions": [], "hour_totals": [0]*11, "total": 0}

        dashboard_data[key]["submissions"].append(sub)

        hours = [
            sub.hour1, sub.hour2, sub.hour3, sub.hour4, sub.hour5,
            sub.hour6, sub.hour7, sub.hour8, sub.hour9, sub.hour10, sub.hour11
        ]

        for i in range(11):
            dashboard_data[key]["hour_totals"][i] += hours[i] or 0

        dashboard_data[key]["total"] += sub.total_output()

    return render(request, "supervisor_dashboard.html", {
        "dashboard_data": dashboard_data,
        "today": today,
        "hour_range": range(1, 12),
        "shift": shift
    })

    # =========================
    # AJAX REALTIME ENDPOINT
    # =========================
    if request.GET.get("ajax") == "1":

        dashboard_data = {}

        for sub in submissions:
            key = f"{sub.line}_{sub.shift}"

            if key not in dashboard_data:
                dashboard_data[key] = {
                    "hour_totals": [0]*11,
                    "total": 0
                }

            hours = [
                sub.hour1, sub.hour2, sub.hour3, sub.hour4, sub.hour5,
                sub.hour6, sub.hour7, sub.hour8, sub.hour9, sub.hour10, sub.hour11
            ]

            for i in range(11):
                dashboard_data[key]["hour_totals"][i] += hours[i] or 0

            dashboard_data[key]["total"] += sub.total_output()

        return JsonResponse({
            "global_locked_hours": global_locked_hours,
            "dashboard_data": dashboard_data
        })

    # =========================
    # NORMAL PAGE LOAD
    # =========================
    dashboard_data = {}

    for sub in submissions:
        key = f"{sub.line}_{sub.shift}"
        if key not in dashboard_data:
            dashboard_data[key] = {"submissions": [], "hour_totals": [0]*11, "total": 0}

        dashboard_data[key]["submissions"].append(sub)

        hours = [
            sub.hour1, sub.hour2, sub.hour3, sub.hour4, sub.hour5,
            sub.hour6, sub.hour7, sub.hour8, sub.hour9, sub.hour10, sub.hour11
        ]

        for i in range(11):
            dashboard_data[key]["hour_totals"][i] += hours[i] or 0

        dashboard_data[key]["total"] += sub.total_output()

    return render(request, "supervisor_dashboard.html", {
        "dashboard_data": dashboard_data,
        "today": today,
        "hour_range": range(1, 12),
        "shift": shift
    })

# -----------------------------
# RESET SHIFT
# -----------------------------
def reset_shift(request):
    if request.method == "POST":
        shift = request.POST.get("shift")
        today = timezone.localdate()

        target_date = today if shift == "Day" else today - timedelta(days=1)

        # save active shift
        ActiveShift.objects.all().delete()
        ActiveShift.objects.create(
            shift=shift,
            date=target_date
        )

        # clear old temp data for that shift
        TempSubmission.objects.filter(shift=shift, date=target_date).delete()

        messages.success(request, f"{shift} shift started successfully.")

    return redirect("jobcard:supervisor_dashboard")

# -----------------------------
# FINALIZE SHIFT
# -----------------------------
def finalize_shift(request, line, shift):
    today = timezone.localdate()
    submissions = TempSubmission.objects.filter(date=today if shift=="Day" else today - timedelta(days=1), line=line, shift=shift)

    aggregated_data = [{
        "operator": s.operator.username if s.operator else "Anonymous",
        "hours": [
            s.hour1,s.hour2,s.hour3,s.hour4,s.hour5,s.hour6,s.hour7,s.hour8,s.hour9,s.hour10,s.hour11
        ],
        "total": s.total_output()
    } for s in submissions]

    shift_submission, created = ShiftSubmission.objects.get_or_create(
        date=today if shift=="Day" else today - timedelta(days=1),
        line=line,
        shift=shift,
        defaults={"aggregated_data": aggregated_data}
    )

    if not created:
        shift_submission.aggregated_data = aggregated_data
        shift_submission.save()

    return redirect("jobcard:supervisor_dashboard")

# -----------------------------
# JOBCARD OPERATOR ENTRY
# -----------------------------
def jobcard_operator_entry(request):
    today = timezone.localdate()
    line = request.POST.get("line") or request.GET.get("line")
    shift = request.POST.get("shift") or request.GET.get("shift", "Day")

    if not line or not shift:
        messages.warning(request, "Please select a Line and Shift first.")
        form = JobCardForm()
        return render(request, "jobcard_form.html", {"form": form, "shift": shift, "line": line})

    jobcard_date = today if shift.lower() == "day" else today - timedelta(days=1)
    jobcard, created = JobCard.objects.get_or_create(date=jobcard_date, line=line, shift=shift)

    # ✅ Load TempSubmission hours
    temp_data = TempSubmission.objects.filter(date=jobcard_date, line=line, shift__iexact=shift).first()
    if temp_data:
        for i in range(1, 12):
            setattr(jobcard, f"hour{i}", getattr(temp_data, f"hour{i}", 0))

    if request.method == "POST":
        form = JobCardForm(request.POST, instance=jobcard)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.is_submitted = True
            obj.save()
            messages.success(request, "✅ JobCard submitted successfully!")
            return redirect("jobcard:jobcard_success")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = JobCardForm(instance=jobcard)

    return render(request, "jobcard_form.html", {"form": form, "shift": shift, "line": line})

# -----------------------------
# JOBCARD SUCCESS
# -----------------------------
def jobcard_success(request):
    return render(request, "success.html")

# -----------------------------
# JOBCARD PREPOPULATE
# -----------------------------
def jobcard_prepopulate(request):
    today = timezone.localdate()
    if request.method == "POST":
        form = JobCardPrepopulateForm(request.POST)
        if form.is_valid():
            line = form.cleaned_data['line']
            shift = form.cleaned_data['shift']
            jobcard, created = JobCard.objects.get_or_create(
                date=today if shift=="Day" else today - timedelta(days=1),
                line=line,
                shift=shift,
                defaults={
                    "wo_number": form.cleaned_data['wo_number'],
                    "product_code": form.cleaned_data['product_code'],
                    "product_name": form.cleaned_data['product_name'],
                    "target_quantity": form.cleaned_data['target_quantity'],
                    "operator_names": form.cleaned_data.get("operator_names", ""),
                    "supervisor_names": form.cleaned_data.get("supervisor_names", ""),
                }
            )
            if not created:
                jobcard.wo_number = form.cleaned_data['wo_number']
                jobcard.product_code = form.cleaned_data['product_code']
                jobcard.product_name = form.cleaned_data['product_name']
                jobcard.target_quantity = form.cleaned_data['target_quantity']
                jobcard.operator_names = form.cleaned_data.get("operator_names", "")
                jobcard.supervisor_names = form.cleaned_data.get("supervisor_names", "")
                jobcard.save()
                messages.success(request, f"JobCard for {line} ({shift}) updated.")
            else:
                messages.success(request, f"JobCard for {line} ({shift}) created.")
            return redirect('jobcard:jobcard_prepopulate')
    else:
        form = JobCardPrepopulateForm()
    return render(request, "jobcard_prepopulate.html", {"form": form})

# -----------------------------
# GET JOBCARD AJAX (OPERATOR PANEL)
# -----------------------------
def get_jobcard(request):
    line = request.GET.get("line")
    now = timezone.localtime()

    # ✅ ALWAYS trust ActiveShift (single source of truth)
    active = ActiveShift.objects.first()

    if not active:
        return JsonResponse({"error": "No active shift set. Please wait for supervisor to start a shift."})

    shift = active.shift.strip()
    target_date = active.date

    print("DEBUG →", line, shift, target_date, "| TIME:", now)

    try:
        job = JobCard.objects.get(
            line=line,
            shift=shift,
            date=target_date
        )

        temp = TempSubmission.objects.filter(
            date=target_date,
            line=line,
            shift__iexact=shift
        ).first()

        # hourly values
        hours = []
        for i in range(1, 12):
            if temp and getattr(temp, f"hour{i}", None) is not None:
                hours.append(getattr(temp, f"hour{i}"))
            else:
                hours.append(getattr(job, f"hour{i}", 0))

        return JsonResponse({
            "wo_number": job.wo_number,
            "product_code": job.product_code,
            "product_name": job.product_name,
            "target_quantity": job.target_quantity,
            "operator_names": job.operator_names,
            "supervisor_names": job.supervisor_names,
            "hours": hours,
            "submitted": bool(job.is_submitted)
        })

    except JobCard.DoesNotExist:
        return JsonResponse({"error": "No JobCard found for this line & shift"})
