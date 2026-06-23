from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from apps.engineering_params.models import RateSuggestion
from apps.engineering_params import services

@login_required
def suggestions_list(request):
    if request.method == 'POST' and 'refresh' in request.POST:
        services.generate_suggestions()
    pending = RateSuggestion.objects.filter(status='pending').order_by('-created_at')
    accepted = RateSuggestion.objects.filter(status='accepted').order_by('-resolved_at')[:10]
    dismissed = RateSuggestion.objects.filter(status='dismissed').order_by('-resolved_at')[:5]
    return render(request, 'engineering_params/suggestions_list.html', {
        'pending': pending, 'accepted': accepted, 'dismissed': dismissed
    })

@login_required
@require_POST
def suggestion_apply(request, pk):
    s = get_object_or_404(RateSuggestion, pk=pk, status='pending')
    services.apply_suggestion(s.pk, request.user)
    return redirect('engineering_params:suggestions')

@login_required
@require_POST
def suggestion_dismiss(request, pk):
    s = get_object_or_404(RateSuggestion, pk=pk, status='pending')
    services.dismiss_suggestion(s.pk, request.user)
    return redirect('engineering_params:suggestions')
